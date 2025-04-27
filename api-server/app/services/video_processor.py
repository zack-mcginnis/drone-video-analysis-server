import os
import logging
import tempfile
import time
from datetime import datetime
from celery import Celery
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Recording
from app.utils.video import process_video_for_streaming
from app.utils.s3 import download_from_s3
from celery.signals import worker_process_init
from app.utils.redis_utils import get_redis_connection_params, check_redis_connection
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

# Get Redis connection parameters
redis_params = get_redis_connection_params()
redis_url = redis_params['url']

# Configure Celery broker and backend options
broker_options = {
    'socket_timeout': redis_params['socket_timeout'],
    'socket_connect_timeout': redis_params['socket_connect_timeout'],
    'retry_on_timeout': redis_params['retry_on_timeout'],
    'max_retries': redis_params['max_retries']
}

# Backend options (same as broker options)
backend_options = broker_options.copy()

# Initialize Celery app with robust connection settings
celery_app = Celery('video_processor', 
                  broker=redis_url, 
                  backend=redis_url,
                  broker_transport_options=broker_options,
                  result_backend_transport_options=backend_options)

# Configure Celery task routes
celery_app.conf.task_routes = {
    'app.services.video_processor.process_recording_task': {'queue': 'video_processing'}
}

# Configure Celery concurrency
celery_app.conf.worker_concurrency = int(os.getenv('CELERY_CONCURRENCY', '2'))

# Configure task time limits to prevent stuck tasks
celery_app.conf.task_time_limit = 3600  # 1 hour max
celery_app.conf.task_soft_time_limit = 3000  # Soft limit of 50 minutes

# Configure broker connection retry
celery_app.conf.broker_connection_retry = True
celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.broker_connection_max_retries = 10

# Configure visibility timeout (how long tasks can remain hidden from other workers)
celery_app.conf.broker_transport_options = {
    'visibility_timeout': 43200,  # 12 hours
}

# Handle Redis connection at worker startup
@worker_process_init.connect
def init_worker_process(sender=None, conf=None, **kwargs):
    logger.info("Initializing Celery worker process...")
    # Verify Redis connection at worker startup
    if not check_redis_connection(redis_params['host'], redis_params['port']):
        logger.warning("Redis connection check failed at worker startup. Proceeding anyway...")

def get_db_session():
    """Get a new database session"""
    return SessionLocal()

def update_transcoding_status(db: Session, recording_id: int, status: str, error_message: str = None):
    """Helper function to update transcoding status"""
    try:
        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if not recording:
            logger.error(f"Recording {recording_id} not found")
            return
            
        metadata = recording.recording_metadata or {}
        metadata.update({
            "transcoding_status": status,
            "transcoding_completed_at": datetime.now().isoformat()
        })
        
        if error_message:
            metadata["transcoding_error"] = error_message
            
        recording.recording_metadata = metadata
        db.commit()
        logger.info(f"Updated transcoding status to {status} for recording {recording_id}")
    except Exception as e:
        logger.error(f"Failed to update transcoding status: {str(e)}")
        db.rollback()

def get_active_task_for_recording(recording_id: int) -> Optional[str]:
    """
    Check if there's an active Celery task for a recording.
    
    Args:
        recording_id: ID of the recording to check
        
    Returns:
        Optional[str]: Task ID if found, None if not
    """
    try:
        # Get active tasks from the celery app
        i = celery_app.control.inspect()
        
        # Check all active tasks
        active_tasks = i.active()
        if active_tasks:
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    if (task['name'] == 'app.services.video_processor.process_recording_task' and 
                        task['args'] and len(task['args']) > 0 and 
                        int(task['args'][0]) == recording_id):
                        logger.info(f"Found active task {task['id']} for recording {recording_id}")
                        return task['id']
        
        # Check reserved/scheduled tasks too
        reserved_tasks = i.reserved()
        if reserved_tasks:
            for worker, tasks in reserved_tasks.items():
                for task in tasks:
                    if (task['name'] == 'app.services.video_processor.process_recording_task' and 
                        task['args'] and len(task['args']) > 0 and 
                        int(task['args'][0]) == recording_id):
                        logger.info(f"Found reserved task {task['id']} for recording {recording_id}")
                        return task['id']
                        
        # No active task found
        return None
    except Exception as e:
        logger.error(f"Error checking for active tasks: {str(e)}")
        return None

def get_task_status(task_id: str) -> dict:
    """
    Get the status of a Celery task.
    
    Args:
        task_id: ID of the task to check
        
    Returns:
        dict: Task status information
    """
    try:
        # Try to get task result
        result = celery_app.AsyncResult(task_id)
        
        # Build response
        status_info = {
            "task_id": task_id,
            "status": result.status,
        }
        
        # Add error info if failed
        if result.failed():
            status_info["error"] = str(result.result)
            
        return status_info
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return {"task_id": task_id, "status": "unknown", "error": str(e)}

async def check_task_exists(recording_id: int) -> Optional[dict]:
    """
    Check if a processing task already exists for a recording.
    
    Args:
        recording_id: ID of the recording to check
        
    Returns:
        Optional[dict]: Task information if exists, None otherwise
    """
    # First check active tasks
    task_id = get_active_task_for_recording(recording_id)
    
    if task_id:
        # Get task status
        status = get_task_status(task_id)
        return status
    
    return None

@celery_app.task(bind=True, name="app.services.video_processor.process_recording_task",
                 retry_backoff=True, retry_backoff_max=600, retry_jitter=True, 
                 autoretry_for=(Exception,), max_retries=3)
def process_recording_task(self, recording_id: int):
    """
    Celery task to process a video recording for HLS streaming.
    
    Args:
        recording_id: ID of the recording to process
    """
    logger.info(f"Starting Celery processing for recording {recording_id}")
    
    db = get_db_session()
    try:
        # Get recording from database
        db_recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if db_recording is None:
            logger.error(f"Recording {recording_id} not found in Celery task")
            self.update_state(state="FAILURE", meta={"error": f"Recording {recording_id} not found"})
            return
            
        # Ensure HLS directory exists
        HLS_DIR = "/recordings/hls"
        os.makedirs(HLS_DIR, exist_ok=True)
        hls_output_dir = os.path.join(HLS_DIR, str(recording_id))
        
        # Update task state to show we're processing
        self.update_state(state="PROGRESS", meta={"status": "processing", "recording_id": recording_id})
        
        # Process based on environment
        if db_recording.environment == "local":
            # Handle local file
            file_path = db_recording.file_path
            if not file_path.startswith('/recordings/'):
                file_path = os.path.join("/recordings", os.path.basename(file_path))
            
            if not os.path.exists(file_path):
                error_msg = f"File not found at {file_path}"
                logger.error(error_msg)
                update_transcoding_status(db, recording_id, "failed", error_msg)
                self.update_state(state="FAILURE", meta={"error": error_msg})
                return
                
            # Process video for HLS streaming
            logger.info(f"Processing local video for streaming: {file_path}")
            try:
                playlist_path, video_info = process_video_for_streaming(file_path, hls_output_dir)
                logger.info(f"HLS playlist created at: {playlist_path}")
            except Exception as e:
                error_msg = f"Failed to process video for streaming: {str(e)}"
                logger.error(error_msg)
                update_transcoding_status(db, recording_id, "failed", error_msg)
                self.update_state(state="FAILURE", meta={"error": error_msg})
                return
                
        else:
            # Handle AWS S3 file
            if not db_recording.s3_path:
                error_msg = f"Recording does not have an S3 path: {recording_id}"
                logger.error(error_msg)
                update_transcoding_status(db, recording_id, "failed", error_msg)
                self.update_state(state="FAILURE", meta={"error": error_msg})
                return
                
            s3_path = db_recording.s3_path
            if s3_path.startswith("s3://"):
                s3_path = s3_path[5:]
                
            # Download from S3
            with tempfile.NamedTemporaryFile(suffix='.mp4') as temp_file:
                logger.info(f"Downloading from S3: {s3_path}")
                
                try:
                    if not download_from_s3(s3_path, temp_file.name):
                        error_msg = "Failed to download file from S3"
                        logger.error(error_msg)
                        update_transcoding_status(db, recording_id, "failed", error_msg)
                        self.update_state(state="FAILURE", meta={"error": error_msg})
                        return
                except Exception as e:
                    error_msg = f"S3 download error: {str(e)}"
                    logger.error(error_msg)
                    update_transcoding_status(db, recording_id, "failed", error_msg)
                    self.update_state(state="FAILURE", meta={"error": error_msg})
                    return
                    
                # Process video for HLS streaming
                logger.info(f"Processing S3 video for streaming: {temp_file.name}")
                try:
                    playlist_path, video_info = process_video_for_streaming(temp_file.name, hls_output_dir)
                    logger.info(f"HLS playlist created at: {playlist_path}")
                except Exception as e:
                    error_msg = f"Failed to process S3 video: {str(e)}"
                    logger.error(error_msg)
                    update_transcoding_status(db, recording_id, "failed", error_msg)
                    self.update_state(state="FAILURE", meta={"error": error_msg})
                    return
        
        # Update recording metadata with HLS information
        metadata = db_recording.recording_metadata or {}
        metadata.update({
            "hls_path": hls_output_dir,
            "processed": True,
            "transcoding_status": "completed",
            "transcoding_completed_at": datetime.now().isoformat(),
            "video_info": video_info
        })
        
        # Update the recording in the database
        try:
            db_recording.recording_metadata = metadata
            db.commit()
            logger.info(f"Successfully processed recording {recording_id} for HLS streaming")
            
            # Return success result with video info
            return {
                "recording_id": recording_id, 
                "status": "completed",
                "hls_path": hls_output_dir,
                "video_info": video_info
            }
        except Exception as e:
            error_msg = f"Database error updating metadata: {str(e)}"
            logger.error(error_msg)
            db.rollback()
            update_transcoding_status(db, recording_id, "failed", error_msg)
            self.update_state(state="FAILURE", meta={"error": error_msg})
            return
            
    except Exception as e:
        error_msg = f"Unexpected error in Celery processing task: {str(e)}"
        logger.error(error_msg)
        try:
            # Try to update status to failed
            update_transcoding_status(db, recording_id, "failed", error_msg)
            self.update_state(state="FAILURE", meta={"error": error_msg})
        except:
            logger.error("Could not update failure status in database")
        return
    finally:
        db.close()

async def submit_processing_job(recording_id: int) -> str:
    """
    Submit a video processing job to the Celery queue.
    
    Args:
        recording_id: ID of the recording to process
        
    Returns:
        Task ID of the submitted job
    """
    try:
        # First check if a task already exists
        logger.info("Submitting job")
        existing_task = await check_task_exists(recording_id)
        if existing_task:
            logger.info(f"Task already exists for recording {recording_id}: {existing_task}")
            return existing_task["task_id"]
            
        # Submit new task to Celery
        task = process_recording_task.delay(recording_id)
        logger.info(f"Submitted processing job for recording {recording_id}, task ID: {task.id}")
        return task.id
    except Exception as e:
        logger.error(f"Failed to submit processing job: {str(e)}")
        # Instead of raising the exception, update the recording status directly
        # and generate a dummy task ID
        try:
            db = get_db_session()
            update_transcoding_status(db, recording_id, "failed", f"Redis connection error: {str(e)}")
            db.close()
        except Exception as db_error:
            logger.error(f"Failed to update recording status: {str(db_error)}")
        
        # Return a dummy task ID with a prefix to indicate it's not a real task
        dummy_task_id = f"local-fallback-{recording_id}-{int(time.time())}"
        return dummy_task_id 