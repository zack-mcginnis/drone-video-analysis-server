import os
import logging
import tempfile
from datetime import datetime
import threading
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Recording
from app.utils.video import process_video_for_streaming
from app.utils.s3 import download_from_s3
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Store active processing tasks
active_tasks = {}

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

def process_recording(recording_id: int):
    """
    Process a video recording for HLS streaming.
    This is a standalone function that handles the conversion without Celery.
    
    Args:
        recording_id: ID of the recording to process
    """
    logger.info(f"Starting processing for recording {recording_id}")
    
    # Track the task status
    active_tasks[recording_id] = {"status": "processing", "started_at": datetime.now().isoformat()}
    
    db = get_db_session()
    try:
        # Get recording from database
        db_recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if db_recording is None:
            logger.error(f"Recording {recording_id} not found in processing task")
            active_tasks[recording_id] = {"status": "failed", "error": f"Recording {recording_id} not found"}
            return
        
        # Check if this recording already has HLS files in S3 (when rtmp-server has already processed them)
        if (db_recording.environment == "aws" and 
            db_recording.recording_metadata and 
            "hls_s3_path" in db_recording.recording_metadata and
            db_recording.recording_metadata["hls_s3_path"]):
            
            logger.info(f"Recording {recording_id} already has HLS files in S3, skipping processing")
            
            # Update metadata to show it's already processed
            metadata = db_recording.recording_metadata or {}
            metadata.update({
                "processed": True,
                "transcoding_status": "completed",
                "transcoding_completed_at": datetime.now().isoformat(),
                "s3_hls_processed": True
            })
            
            # Set the s3_hls_path field from metadata
            hls_s3_path = db_recording.recording_metadata["hls_s3_path"]
            db_recording.s3_hls_path = hls_s3_path
            logger.info(f"Set s3_hls_path to: {hls_s3_path}")
            
            # Update the recording in the database
            db_recording.recording_metadata = metadata
            db.commit()
            
            # Update task status
            active_tasks[recording_id] = {"status": "completed", "s3_hls_processed": True}
            return
        
        # If not already processed by rtmp-server, continue with normal processing
        # Ensure HLS directory exists
        HLS_DIR = "/recordings/hls"
        os.makedirs(HLS_DIR, exist_ok=True)
        hls_output_dir = os.path.join(HLS_DIR, str(recording_id))
        
        # Process based on environment
        if db_recording.environment == "local":
            # Handle local file
            file_path = db_recording.local_mp4_path
            if not file_path.startswith('/recordings/'):
                file_path = os.path.join("/recordings", os.path.basename(file_path))
            
            if not os.path.exists(file_path):
                error_msg = f"File not found at {file_path}"
                logger.error(error_msg)
                update_transcoding_status(db, recording_id, "failed", error_msg)
                active_tasks[recording_id] = {"status": "failed", "error": error_msg}
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
                active_tasks[recording_id] = {"status": "failed", "error": error_msg}
                return
                
        else:
            # Handle AWS S3 file
            if not db_recording.s3_mp4_path:
                error_msg = f"Recording does not have an S3 path: {recording_id}"
                logger.error(error_msg)
                update_transcoding_status(db, recording_id, "failed", error_msg)
                active_tasks[recording_id] = {"status": "failed", "error": error_msg}
                return
                
            s3_path = db_recording.s3_mp4_path
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
                        active_tasks[recording_id] = {"status": "failed", "error": error_msg}
                        return
                except Exception as e:
                    error_msg = f"S3 download error: {str(e)}"
                    logger.error(error_msg)
                    update_transcoding_status(db, recording_id, "failed", error_msg)
                    active_tasks[recording_id] = {"status": "failed", "error": error_msg}
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
                    active_tasks[recording_id] = {"status": "failed", "error": error_msg}
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
            # Log the current metadata for debugging
            logger.info(f"Current metadata before update: {db_recording.recording_metadata}")
            
            # Update metadata field
            db_recording.recording_metadata = metadata
            
            # Set the appropriate HLS path field based on environment
            if db_recording.environment == "local":
                db_recording.local_hls_path = hls_output_dir
                logger.info(f"Set local_hls_path to: {hls_output_dir}")
            else:
                # For AWS environment, we would set s3_hls_path if we had uploaded to S3
                # This would be set by the rtmp-server or another upload process
                logger.info(f"AWS environment - s3_hls_path should be set by upload process")
            
            db.commit()
            
            logger.info(f"Successfully processed recording {recording_id} for HLS streaming")
            
            # Update task status
            active_tasks[recording_id] = {
                "status": "completed", 
                "hls_path": hls_output_dir,
                "video_info": video_info
            }
        except Exception as e:
            error_msg = f"Database error updating metadata: {str(e)}"
            logger.error(error_msg)
            db.rollback()
            update_transcoding_status(db, recording_id, "failed", error_msg)
            active_tasks[recording_id] = {"status": "failed", "error": error_msg}
            return
            
    except Exception as e:
        error_msg = f"Unexpected error in processing task: {str(e)}"
        logger.error(error_msg)
        try:
            # Try to update status to failed
            update_transcoding_status(db, recording_id, "failed", error_msg)
            active_tasks[recording_id] = {"status": "failed", "error": error_msg}
        except:
            logger.error("Could not update failure status in database")
        return
    finally:
        db.close()

async def submit_processing_job(recording_id: int) -> str:
    """
    Submit a video processing job to run in a background thread.
    
    Args:
        recording_id: ID of the recording to process
        
    Returns:
        Task ID of the submitted job
    """
    try:
        # Check if there's already a task running for this recording
        if recording_id in active_tasks:
            logger.info(f"Task already exists for recording {recording_id}: {active_tasks[recording_id]}")
            return f"task-{recording_id}"
            
        # Start a new background thread for processing
        thread = threading.Thread(target=process_recording, args=(recording_id,))
        thread.daemon = True
        thread.start()
        
        # Create task ID and add to active tasks
        task_id = f"task-{recording_id}"
        active_tasks[recording_id] = {"status": "processing", "started_at": datetime.now().isoformat()}
        
        logger.info(f"Submitted processing job for recording {recording_id}, task ID: {task_id}")
        return task_id
    except Exception as e:
        logger.error(f"Failed to submit processing job: {str(e)}")
        
        # Update recording status directly
        try:
            db = get_db_session()
            update_transcoding_status(db, recording_id, "failed", f"Error starting processing: {str(e)}")
            db.close()
        except Exception as db_error:
            logger.error(f"Failed to update recording status: {str(db_error)}")
        
        # Add failed task to active tasks
        task_id = f"failed-{recording_id}"
        active_tasks[recording_id] = {"status": "failed", "error": str(e)}
        return task_id

async def check_task_exists(recording_id: int) -> Optional[Dict[str, Any]]:
    """
    Check if a processing task already exists for a recording.
    
    Args:
        recording_id: ID of the recording to check
        
    Returns:
        Optional[dict]: Task information if exists, None otherwise
    """
    if recording_id in active_tasks:
        task_info = active_tasks[recording_id].copy()
        task_info["task_id"] = f"task-{recording_id}"
        return task_info
    
    return None 