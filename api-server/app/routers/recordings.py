from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from .. import crud, schemas, database
import boto3
import os
import io
from dotenv import load_dotenv
from datetime import datetime, timedelta
import subprocess
import tempfile
from pathlib import Path
import logging
import requests
import time
import urllib.parse
from app.models import User, Device

from ..utils.video import process_video_for_streaming, get_video_info
from ..utils.s3 import get_s3_client, generate_presigned_url, download_from_s3, get_s3_hls_file_url
from app.services.auth import auth_service
from app.services.video_processor import check_task_exists

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/recordings",
    tags=["recordings"],
    responses={404: {"description": "Not found"}},
)

RECORDINGS_DIR = "/recordings"
HLS_DIR = os.path.join(RECORDINGS_DIR, "hls")

# Add a background task processor for HLS conversion - KEEPING THIS FOR BACKWARDS COMPATIBILITY
async def process_recording_background(recording_id: int, db: Session):
    """
    DEPRECATED: Use services.video_processor.submit_processing_job instead
    
    Background task to process a video recording for HLS streaming.
    
    Args:
        recording_id: ID of the recording to process
        db: Database session
    """
    logger.warning(f"DEPRECATED: Using old background processing for recording {recording_id}. Use submit_processing_job instead.")
    
    try:
        # Get recording from database
        db_recording = crud.get_recording(db, recording_id=recording_id)
        if db_recording is None:
            logger.error(f"Recording {recording_id} not found in background task")
            return
            
        # Ensure HLS directory exists
        os.makedirs(HLS_DIR, exist_ok=True)
        hls_output_dir = os.path.join(HLS_DIR, str(recording_id))
        
        # Process based on environment
        if db_recording.environment == "local":
            # Handle local file
            file_path = db_recording.local_mp4_path
            if not file_path.startswith('/recordings/'):
                file_path = os.path.join(RECORDINGS_DIR, os.path.basename(file_path))
            
            if not os.path.exists(file_path):
                logger.error(f"Recording file not found at: {file_path}")
                update_transcoding_status(db, db_recording, "failed", f"File not found at {file_path}")
                return
                
            # Process video for HLS streaming
            logger.info(f"Processing local video for streaming: {file_path}")
            try:
                playlist_path, video_info = process_video_for_streaming(file_path, hls_output_dir)
                logger.info(f"HLS playlist created at: {playlist_path}")
            except Exception as e:
                logger.error(f"Failed to process video for streaming: {str(e)}")
                update_transcoding_status(db, db_recording, "failed", str(e))
                return
                
        else:
            # Handle AWS S3 file
            if not db_recording.s3_mp4_path:
                logger.error(f"Recording does not have an S3 path: {recording_id}")
                update_transcoding_status(db, db_recording, "failed", "Recording does not have an S3 path")
                return
                
            s3_path = db_recording.s3_mp4_path
            if s3_path.startswith("s3://"):
                s3_path = s3_path[5:]
                
            # Download from S3
            with tempfile.NamedTemporaryFile(suffix='.mp4') as temp_file:
                logger.info(f"Downloading from S3: {s3_path}")
                
                try:
                    if not download_from_s3(s3_path, temp_file.name):
                        logger.error("Failed to download file from S3")
                        update_transcoding_status(db, db_recording, "failed", "Error downloading from S3")
                        return
                except Exception as e:
                    logger.error(f"S3 download error: {str(e)}")
                    update_transcoding_status(db, db_recording, "failed", f"S3 download error: {str(e)}")
                    return
                    
                # Process video for HLS streaming
                logger.info(f"Processing S3 video for streaming: {temp_file.name}")
                try:
                    playlist_path, video_info = process_video_for_streaming(temp_file.name, hls_output_dir)
                    logger.info(f"HLS playlist created at: {playlist_path}")
                except Exception as e:
                    logger.error(f"Failed to process S3 video: {str(e)}")
                    update_transcoding_status(db, db_recording, "failed", f"Failed to process video: {str(e)}")
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
            db.refresh(db_recording)
            logger.info(f"Successfully processed recording {recording_id} for HLS streaming")
        except Exception as e:
            logger.error(f"Database error updating metadata: {str(e)}")
            db.rollback()
            update_transcoding_status(db, db_recording, "failed", f"Database error: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error in background processing task: {str(e)}")
        try:
            # Try to update status to failed
            db_recording = db.query(models.Recording).filter(models.Recording.id == recording_id).first()
            if db_recording:
                update_transcoding_status(db, db_recording, "failed", f"Unexpected error: {str(e)}")
        except:
            logger.error("Could not update failure status in database")

def update_transcoding_status(db: Session, recording, status: str, error_message: str = None):
    """Helper function to update transcoding status"""
    try:
        metadata = recording.recording_metadata or {}
        metadata.update({
            "transcoding_status": status,
            "transcoding_completed_at": datetime.now().isoformat()
        })
        
        if error_message:
            metadata["transcoding_error"] = error_message
            
        recording.recording_metadata = metadata
        db.commit()
        db.refresh(recording)
        logger.info(f"Updated transcoding status to {status} for recording {recording.id}")
    except Exception as e:
        logger.error(f"Failed to update transcoding status: {str(e)}")
        db.rollback()

@router.get("/", response_model=schemas.RecordingList)
def read_recordings(
    skip: int = 0, 
    limit: int = 100, 
    stream_name: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    recordings = crud.get_recordings(db, user_id=current_user.id, skip=skip, limit=limit, stream_name=stream_name)
    return {"recordings": recordings, "count": len(recordings)}

@router.get("/{recording_id}", response_model=schemas.Recording)
def read_recording(
    recording_id: int, 
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    db_recording = crud.get_recording(db, recording_id=recording_id, user_id=current_user.id)
    if db_recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return db_recording

@router.post("/", response_model=schemas.Recording)
def create_recording(
    recording: schemas.RecordingCreate,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_admin_user)
):
    """Create a new recording. Admin only."""
    # Set the user_id to the current user's ID
    recording.user_id = current_user.id
    print("Creating recording")
    return crud.create_recording(db=db, recording=recording)

@router.put("/{recording_id}", response_model=schemas.Recording)
def update_recording(
    recording_id: int, 
    recording: schemas.RecordingCreate,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    # Ensure the recording belongs to the current user
    db_recording = crud.get_recording(db, recording_id=recording_id, user_id=current_user.id)
    if db_recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Update the recording
    return crud.update_recording(db, recording_id=recording_id, recording=recording, user_id=current_user.id)

@router.delete("/{recording_id}")
def delete_recording(
    recording_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_admin_user)
):
    """Delete a recording. Admin only."""
    db_recording = crud.get_recording(db, recording_id=recording_id, user_id=current_user.id)
    if db_recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Delete the recording file if it exists
    if db_recording.local_mp4_path and os.path.exists(db_recording.local_mp4_path):
        os.remove(db_recording.local_mp4_path)
    
    # Delete the recording from the database
    db.delete(db_recording)
    db.commit()
    
    return {"message": "Recording deleted successfully"}

@router.get("/stream/{recording_id}")
async def stream_recording(
    recording_id: int, 
    request: Request, 
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
) -> Dict[str, Any]:
    """
    Stream a recording using HLS. Assumes HLS files are already available.
    
    Args:
        recording_id: ID of the recording
        request: FastAPI request object
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Dict with stream URL for the recording
    """
    try:
        # Get recording metadata from database
        db_recording = crud.get_recording(db, recording_id)
        if db_recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")
            
        # Check if user has access to this recording
        if db_recording.user_id != current_user.id:
            # Check if user has access through device association
            stream_name = db_recording.stream_name
            user_devices = db.query(Device).filter(
                Device.users.any(id=current_user.id),
                Device.is_active == True,
                Device.stream_key == stream_name
            ).first()
                
            if not user_devices:
                logger.error(f"User {current_user.id} does not have access to recording {recording_id}")
                raise HTTPException(status_code=403, detail="You do not have permission to access this recording")
                
        # Generate a JWT token for the playlist
        token = auth_service.create_temporary_token(
            data={"user_id": current_user.id, "exp": int(time.time()) + 36000},
            expires_delta=None  # We handle expiry in the data
        )
        encoded_token = urllib.parse.quote(token, safe='')
        
        # Get the base URL from the request
        base_url = str(request.base_url)
        base_url = base_url.rstrip('/')
        
        # Generate the stream URL with authentication token
        stream_url = f"{base_url}/recordings/hls/{recording_id}/playlist.m3u8?token={encoded_token}"
        
        # Check for AWS environment with S3 HLS path
        if db_recording.environment == "aws" and db_recording.s3_hls_path:
            logger.info(f"Using S3 HLS path for recording {recording_id}: {db_recording.s3_hls_path}")
            
            return {
                "stream_url": stream_url,
                "title": f"{db_recording.stream_name} - Recording {recording_id}",
                "format": "hls",
                "status": "ready",
                "hls_path": db_recording.s3_hls_path,
                "environment": "aws"
            }
            
        # Check for local environment with local HLS path
        if db_recording.environment == "local" and db_recording.local_hls_path:
            # Verify that the HLS playlist exists
            playlist_path = os.path.join(db_recording.local_hls_path, "playlist.m3u8")
            if os.path.exists(playlist_path):
                logger.info(f"Using local HLS path for recording {recording_id}: {db_recording.local_hls_path}")
                
                return {
                    "stream_url": stream_url,
                    "title": f"{db_recording.stream_name} - Recording {recording_id}",
                    "format": "hls",
                    "status": "ready",
                    "hls_path": db_recording.local_hls_path,
                    "environment": "local"
                }
            else:
                logger.warning(f"Local HLS playlist not found at {playlist_path}")
                
        # If no HLS files are available, return an error
        logger.error(f"No HLS files available for recording {recording_id}")
        raise HTTPException(
            status_code=404, 
            detail="HLS files not available for this recording. The recording may still be processing or failed to convert."
        )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming recording {recording_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hls/{recording_id}/{file_name}")
async def get_hls_file(
    recording_id: str, 
    file_name: str,
    token: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """
    Serve HLS playlist and segment files.
    Uses a signed token for authentication instead of requiring user authentication for each request.
    This allows for better caching and compatibility with video players.
    
    In AWS mode, serves files directly from S3 using pre-signed URLs.
    In local mode, serves files from the local filesystem.
    
    Args:
        recording_id: ID of the recording
        file_name: Name of the HLS file to serve
        token: Optional signed token for authentication
        db: Database session
    
    Returns:
        FileResponse containing the requested HLS file or RedirectResponse to S3 URL
    """
    try:
        # For playlist requests, verify the token
        if file_name == "playlist.m3u8":
            if not token:
                logger.error(f"No token provided for playlist request: recording {recording_id}")
                raise HTTPException(status_code=401, detail="Authentication required")
                
            try:
                # Log the received token
                logger.info(f"Received token: {token}")
                
                # URL decode the token
                decoded_token = urllib.parse.unquote(token)
                logger.info(f"Decoded token: {decoded_token}")

                # Log the temp token secret being used
                secret_preview = auth_service.temp_token_secret[:10] + "..." if auth_service.temp_token_secret else None
                logger.info(f"Using temp token secret (preview): {secret_preview}")

                # Verify token and get user_id
                payload = auth_service.verify_temporary_token(decoded_token)
                logger.info(f"Token payload: {payload}")
                
                user_id = payload.get("user_id")
                if not user_id:
                    logger.error(f"No user_id in token payload for recording {recording_id}")
                    raise ValueError("No user_id in token")
                    
                logger.info(f"Token verified successfully for user {user_id}, recording {recording_id}")
                
            except Exception as e:
                logger.error(f"Token verification failed for recording {recording_id}. Error: {str(e)}", exc_info=True)
                raise HTTPException(status_code=401, detail="Invalid authentication token")
                
            # Get recording from database
            db_recording = crud.get_recording(db, recording_id=int(recording_id))
            if db_recording is None:
                logger.error(f"Recording {recording_id} not found")
                raise HTTPException(status_code=404, detail="Recording not found")
                
            # Check if user has access to this recording
            if db_recording.user_id != user_id:
                # Check if user has access through device association
                stream_name = db_recording.stream_name
                user_devices = db.query(Device).filter(
                    Device.users.any(id=user_id),
                    Device.is_active == True,
                    Device.stream_key == stream_name
                ).first()
                
                if not user_devices and db_recording.recording_metadata and "stream_id" in db_recording.recording_metadata:
                    stream_id = db_recording.recording_metadata["stream_id"]
                    user_devices = db.query(Device).filter(
                        Device.users.any(id=user_id),
                        Device.is_active == True,
                        Device.stream_key == stream_id
                    ).first()
                    
                if not user_devices:
                    logger.error(f"User {user_id} does not have access to recording {recording_id}")
                    raise HTTPException(status_code=403, detail="You do not have permission to access this recording")
                    
            # Check if HLS files are available
            if db_recording.environment == "aws" and not db_recording.s3_hls_path:
                logger.error(f"Recording {recording_id} has no S3 HLS path")
                raise HTTPException(status_code=404, detail="HLS files not available")
            elif db_recording.environment == "local" and not db_recording.local_hls_path:
                logger.error(f"Recording {recording_id} has no local HLS path")
                raise HTTPException(status_code=404, detail="HLS files not available")
        else:
            # For segment requests (.ts files), we don't verify the token
            # This is safe because:
            # 1. Segment names are hard to guess
            # 2. Segments are meaningless without the playlist
            # 3. This allows for better caching
            
            # Get recording from database (still need it for S3 paths)
            db_recording = crud.get_recording(db, recording_id=int(recording_id))
            if db_recording is None:
                logger.error(f"Recording {recording_id} not found")
                raise HTTPException(status_code=404, detail="Recording not found")
        
        # Check if we're in AWS mode and have an S3 path for HLS files
        is_aws_mode = db_recording.environment == "aws"
        has_s3_hls_path = db_recording.s3_hls_path is not None
        
        if is_aws_mode and has_s3_hls_path:
            # Serve from S3
            from fastapi.responses import RedirectResponse
            
            hls_s3_path = db_recording.s3_hls_path
            logger.info(f"Serving HLS file from S3: {hls_s3_path}/{file_name}")
            
            # Generate a pre-signed URL for the HLS file
            s3_url = get_s3_hls_file_url(hls_s3_path, file_name)
            if not s3_url:
                logger.error(f"Failed to generate S3 URL for HLS file: {file_name}")
                raise HTTPException(status_code=500, detail="Failed to generate S3 URL")
            
            # Set appropriate content type
            content_type = "application/vnd.apple.mpegurl" if file_name.endswith('.m3u8') else "video/mp2t"
            
            # Create redirect response
            response = RedirectResponse(url=s3_url)
            response.headers["Content-Type"] = content_type
            
            # Add caching headers based on file type
            if file_name.endswith('.ts'):
                # Cache segments for 1 year (they are immutable)
                response.headers["Cache-Control"] = "public, max-age=31536000"
            else:
                # Don't cache playlists
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                
            return response
        else:
            # Serve from local filesystem using the local_hls_path from the database
            if not db_recording.local_hls_path:
                logger.error(f"No local HLS path available for recording {recording_id}")
                raise HTTPException(status_code=404, detail="Local HLS path not available")
                
            file_path = os.path.join(db_recording.local_hls_path, file_name)
            logger.info(f"Serving local HLS file: {file_path}")
            
            if not os.path.exists(file_path):
                logger.error(f"HLS file not found: {file_path}")
                raise HTTPException(status_code=404, detail="HLS file not found")
                
            # Set content type based on file extension
            content_type = "application/vnd.apple.mpegurl" if file_name.endswith('.m3u8') else "video/mp2t"
            
            # Ensure the file path is within the recording's HLS directory (security check)
            abs_hls_dir = os.path.abspath(db_recording.local_hls_path)
            abs_file_path = os.path.abspath(file_path)
            if not abs_file_path.startswith(abs_hls_dir):
                logger.error(f"Invalid file path: {file_path}")
                raise HTTPException(status_code=400, detail="Invalid file path")
            
            response = FileResponse(
                path=file_path,
                media_type=content_type,
                filename=file_name
            )
            
            # Add caching headers for better performance
            if file_name.endswith('.ts'):
                # Cache segments for 1 year (they are immutable)
                response.headers["Cache-Control"] = "public, max-age=31536000"
            else:
                # Don't cache playlists
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                
            return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving HLS file {file_name} for recording {recording_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while serving HLS file")

@router.get("/{recording_id}/info")
async def get_recording_info(
    recording_id: str,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
) -> Dict[str, Any]:
    """
    Get information about a recording.
    
    Args:
        recording_id: ID of the recording
    
    Returns:
        Dictionary containing recording information
    """
    try:
        # Get recording from database
        db_recording = crud.get_recording(db, recording_id=int(recording_id), user_id=current_user.id)
        if db_recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")
            
        recording_dir = os.path.join(RECORDINGS_DIR, f"drone_stream_{recording_id}")
        mp4_file = os.path.join(recording_dir, f"{recording_id}.mp4")
        
        if not os.path.exists(mp4_file):
            raise HTTPException(status_code=404, detail="Recording not found")
            
        video_info = get_video_info(mp4_file)
        if not video_info:
            raise HTTPException(status_code=500, detail="Could not get video information")
            
        return {
            "id": recording_id,
            "file_path": mp4_file,
            "video_info": video_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recording info for {recording_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def convert_to_streaming_formats(input_path, video_id):
    """
    Convert video to MP4 (if needed) and create adaptive bitrate versions
    """
    output_dir = f"/tmp/processed/{video_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Determine if input is already MP4
    is_mp4 = input_path.lower().endswith('.mp4')
    
    # Base MP4 conversion (skip if already MP4)
    base_mp4 = f"{output_dir}/base.mp4"
    if not is_mp4:
        subprocess.run([
            "ffmpeg", "-i", input_path, 
            "-c:v", "libx264", "-c:a", "aac",
            "-movflags", "+faststart",  # Optimize for web streaming
            base_mp4
        ])
    else:
        # If already MP4, just copy the file
        import shutil
        shutil.copy(input_path, base_mp4)
    
    # Create multiple bitrate versions
    bitrates = ["1500k", "800k", "400k"]
    output_files = []
    
    for bitrate in bitrates:
        output_file = f"{output_dir}/output_{bitrate}.mp4"
        subprocess.run([
            "ffmpeg", "-i", base_mp4,
            "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", f"{int(bitrate[:-1]) * 2}k",
            "-c:v", "libx264", "-preset", "medium", "-c:a", "aac",
            output_file
        ])
        output_files.append(output_file)
    
    # Create HLS playlist
    subprocess.run([
        "ffmpeg", "-i", base_mp4,
        "-codec", "copy",
        "-start_number", "0",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-f", "hls",
        f"{output_dir}/playlist.m3u8"
    ])
    
    return output_dir 

@router.get("/debug-player/{recording_id}")
async def get_debug_video_player(recording_id: int, db: Session = Depends(database.get_db)):
    """Simple debug player for administrators and testing"""
    db_recording = crud.get_recording(db, recording_id=recording_id)
    if db_recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Determine if HLS is available
    has_hls = False
    if db_recording.recording_metadata and "processed" in db_recording.recording_metadata:
        has_hls = db_recording.recording_metadata.get("processed", False)
    
    # Get file format
    file_format = "mp4"  # Default to mp4
    if db_recording.recording_metadata and "file_format" in db_recording.recording_metadata:
        file_format = db_recording.recording_metadata["file_format"]
    elif db_recording.local_mp4_path:
        file_format = os.path.splitext(db_recording.local_mp4_path)[1].lstrip('.')
    
    # Create the HLS or direct playback code separately to avoid backslash issues in f-strings
    if has_hls:
        player_code = """
        if (Hls.isSupported()) {
            var hls = new Hls();
            hls.loadSource(videoSrc);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, function() {
                // video.play();
            });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = videoSrc;
            video.addEventListener('loadedmetadata', function() {
                // video.play();
            });
        }
        """
    else:
        player_code = "// Direct MP4 playback\nvideo.src = videoSrc;"
    
    # Now build the HTML content without problematic f-string expressions
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debug Player - Recording {recording_id}</title>
        <style>
            body {{ font-family: monospace; margin: 0; padding: 20px; background: #f0f0f0; }}
            h1 {{ color: #333; }}
            video {{ max-width: 100%; border: 1px solid #ccc; }}
            .info {{ margin-top: 20px; background: #fff; padding: 15px; border-radius: 4px; }}
            .debug {{ margin-top: 20px; background: #333; color: #0f0; padding: 15px; border-radius: 4px; font-family: monospace; }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    </head>
    <body>
        <h1>Debug Player: {db_recording.stream_name}</h1>
        <video id="video" controls></video>
        
        <div class="info">
            <p><strong>Recording ID:</strong> {recording_id}</p>
            <p><strong>Format:</strong> {file_format.upper()}</p>
            <p><strong>Size:</strong> {db_recording.file_size / (1024 * 1024):.2f} MB</p>
            <p><strong>Created:</strong> {db_recording.created_at}</p>
            <p><strong>Environment:</strong> {db_recording.environment}</p>
        </div>
        
        <div class="debug">
            <p>HLS Available: {has_hls}</p>
            <p>Stream URL: {'/recordings/hls/' + str(recording_id) + '/playlist.m3u8' if has_hls else '/recordings/stream/' + str(recording_id)}</p>
            <p>Metadata: {db_recording.recording_metadata}</p>
        </div>
        
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                var video = document.getElementById('video');
                var videoSrc = '{'/recordings/hls/' + str(recording_id) + '/playlist.m3u8' if has_hls else '/recordings/stream/' + str(recording_id)}';
                
                {player_code}
                
                // Add debug event listeners
                video.addEventListener('error', function(e) {{
                    console.error('Video error:', e);
                    document.querySelector('.debug').innerHTML += '<p style="color:red">Error: ' + e.target.error.code + '</p>';
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    return Response(
        content=html_content,
        media_type="text/html"
    )

@router.get("/{recording_id}/playback-info")
async def get_recording_playback_info(
    recording_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Get playback information for a recording"""
    db_recording = crud.get_recording(db, recording_id=recording_id, user_id=current_user.id)
    if db_recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Determine available formats
    has_hls = False
    if db_recording.recording_metadata and "processed" in db_recording.recording_metadata:
        has_hls = db_recording.recording_metadata.get("processed", False)
    
    # Get file format
    file_format = "mp4"  # Default to mp4
    if db_recording.recording_metadata and "file_format" in db_recording.recording_metadata:
        file_format = db_recording.recording_metadata["file_format"]
    elif db_recording.local_mp4_path:
        file_format = os.path.splitext(db_recording.local_mp4_path)[1].lstrip('.')
    
    # Build response with all available playback options
    response = {
        "recording_id": recording_id,
        "stream_name": db_recording.stream_name,
        "duration": db_recording.recording_metadata.get("duration") if db_recording.recording_metadata else None,
        "file_size": db_recording.file_size,
        "created_at": db_recording.created_at,
        "playback_options": {
            "direct": {
                "url": f"/recordings/stream/{recording_id}",
                "format": file_format,
                "mime_type": "video/mp4" if file_format == "mp4" else "video/x-flv"
            }
        }
    }
    
    # Add HLS if available
    if has_hls:
        response["playback_options"]["hls"] = {
            "url": f"/recordings/hls/{recording_id}/playlist.m3u8",
            "format": "hls",
            "mime_type": "application/vnd.apple.mpegurl"
        }
    
    return response 

@router.get("/streams")
async def get_streams(
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Get a list of unique stream IDs for the current user"""
    recordings = crud.get_recordings(db, user_id=current_user.id)
    
    # Extract unique stream IDs from recording metadata
    streams = {}
    for recording in recordings:
        stream_id = None
        if recording.recording_metadata and "stream_id" in recording.recording_metadata:
            stream_id = recording.recording_metadata["stream_id"]
        else:
            # Fallback to stream name if no stream_id
            stream_id = recording.stream_name
        
        if stream_id not in streams:
            streams[stream_id] = {
                "stream_id": stream_id,
                "stream_name": recording.stream_name,
                "recording_count": 1,
                "first_recording": recording.created_at,
                "latest_recording": recording.created_at,
                "total_size": recording.file_size
            }
        else:
            streams[stream_id]["recording_count"] += 1
            streams[stream_id]["total_size"] += recording.file_size
            
            # Update timestamps
            if recording.created_at < streams[stream_id]["first_recording"]:
                streams[stream_id]["first_recording"] = recording.created_at
            if recording.created_at > streams[stream_id]["latest_recording"]:
                streams[stream_id]["latest_recording"] = recording.created_at
    
    return {"streams": list(streams.values())}

@router.get("/streams/{stream_id}/recordings")
async def get_stream_recordings(
    stream_id: str,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Get all recordings for a specific stream ID for the current user"""
    recordings = crud.get_recordings(db, user_id=current_user.id)
    
    # Filter recordings by stream ID
    stream_recordings = []
    for recording in recordings:
        if (recording.recording_metadata and 
            "stream_id" in recording.recording_metadata and 
            recording.recording_metadata["stream_id"] == stream_id):
            stream_recordings.append(recording)
        elif stream_id == recording.stream_name:
            # Fallback to stream name if no stream_id
            stream_recordings.append(recording)
    
    return {"recordings": [schemas.Recording.from_orm(r) for r in stream_recordings]}

@router.post("/rtmp/{stream_key}", response_model=schemas.Recording)
def create_recording_from_rtmp(
    stream_key: str,
    recording: dict,
    db: Session = Depends(database.get_db)
):
    """
    Special endpoint for RTMP server to create recordings without authentication.
    This endpoint should only be accessible from the RTMP server.
    """
    try:
        logger.info(f"Received RTMP recording request for stream key: {stream_key}")
        logger.info(f"Recording data: {recording}")
        
        # Find device by stream key
        device = db.query(Device).filter(
            Device.stream_key == stream_key,
            Device.is_active == True
        ).first()
        
        if not device:
            logger.error(f"No active device found for stream key: {stream_key}")
            raise HTTPException(status_code=404, detail="Invalid stream key")
        
        # Get the first user associated with this device
        if not device.users:
            logger.error(f"Device {device.id} has no associated users")
            raise HTTPException(status_code=400, detail="Device has no associated users")
            
        user_id = device.users[0].id
        logger.info(f"Found device: {device.id} for user: {user_id}")
        
        # Add user_id to the recording dictionary
        recording["user_id"] = user_id
        
        # Convert the dict to a RecordingCreate schema
        try:
            recording_schema = schemas.RecordingCreate(**recording)
            logger.info(f"Successfully created recording schema: {recording_schema}")
        except Exception as e:
            logger.error(f"Error creating recording schema: {str(e)}")
            raise HTTPException(status_code=422, detail=str(e))
        
        # Create the recording
        try:
            db_recording = crud.create_recording(db=db, recording=recording_schema)
            logger.info(f"Successfully created recording in database with ID: {db_recording.id}")
            return db_recording
        except Exception as e:
            logger.error(f"Error creating recording in database: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_recording_from_rtmp: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 

@router.get("/{recording_id}/status")
async def get_recording_status(
    recording_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
) -> Dict[str, Any]:
    """
    Get the transcoding status of a recording.
    
    Args:
        recording_id: ID of the recording
        
    Returns:
        Status information about the recording
    """
    try:
        # Get recording from database
        db_recording = crud.get_recording(db, recording_id=recording_id)
        if db_recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")
            
        # Check permissions
        if db_recording.user_id != current_user.id:
            # Check if user has access through device association
            stream_name = db_recording.stream_name
            user_devices = db.query(Device).filter(
                Device.users.any(id=current_user.id),
                Device.is_active == True,
                Device.stream_key == stream_name
            ).first()
            
            if not user_devices:
                # Try with stream_id from metadata
                if db_recording.recording_metadata and "stream_id" in db_recording.recording_metadata:
                    stream_id = db_recording.recording_metadata["stream_id"]
                    user_devices = db.query(Device).filter(
                        Device.users.any(id=current_user.id),
                        Device.is_active == True,
                        Device.stream_key == stream_id
                    ).first()
                    
                if not user_devices:
                    raise HTTPException(status_code=403, detail="You do not have permission to access this recording")
        
        # Check if metadata exists
        if not db_recording.recording_metadata:
            return {
                "id": recording_id,
                "status": "unknown",
                "message": "No processing metadata available"
            }
            
        # Check processing status
        if "transcoding_status" in db_recording.recording_metadata:
            status = db_recording.recording_metadata["transcoding_status"]
            
            # Build response
            response = {
                "id": recording_id,
                "status": status,
                "started_at": db_recording.recording_metadata.get("transcoding_started_at"),
                "completed_at": db_recording.recording_metadata.get("transcoding_completed_at")
            }
            
            # Add error message if present
            if status == "failed" and "transcoding_error" in db_recording.recording_metadata:
                response["error"] = db_recording.recording_metadata["transcoding_error"]
                
            # Add HLS info if complete
            if status == "completed":
                # Use the appropriate HLS path based on environment
                if db_recording.environment == "local":
                    response["hls_path"] = db_recording.local_hls_path
                else:
                    response["hls_path"] = db_recording.s3_hls_path
                response["video_info"] = db_recording.recording_metadata.get("video_info", {})
                
            return response
            
        # Check for legacy "processed" flag
        elif "processed" in db_recording.recording_metadata and db_recording.recording_metadata["processed"]:
            # Use the appropriate HLS path based on environment
            hls_path = None
            if db_recording.environment == "local":
                hls_path = db_recording.local_hls_path
            else:
                hls_path = db_recording.s3_hls_path
                
            return {
                "id": recording_id,
                "status": "completed",
                "hls_path": hls_path,
                "processed_at": db_recording.recording_metadata.get("processed_at"),
                "video_info": db_recording.recording_metadata.get("video_info", {})
            }
            
        # Default response if no status info
        return {
            "id": recording_id,
            "status": "unknown",
            "message": "No processing status available"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recording status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 

@router.get("/{recording_id}/processing-status")
async def get_recording_processing_status(
    recording_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
) -> Dict[str, Any]:
    """
    Get the current processing status of a recording without creating a new job.
    This is useful for the frontend to poll for status updates.
    
    Args:
        recording_id: ID of the recording to check
        
    Returns:
        Current status information
    """
    try:
        # Get recording from database
        db_recording = crud.get_recording(db, recording_id=recording_id)
        if db_recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")
            
        # Check if the recording belongs to the current user
        if db_recording.user_id != current_user.id:
            # Check if user has access through device association
            stream_name = db_recording.stream_name
            user_devices = db.query(Device).filter(
                Device.users.any(id=current_user.id),
                Device.is_active == True,
                Device.stream_key == stream_name
            ).first()
            
            if not user_devices and db_recording.recording_metadata and "stream_id" in db_recording.recording_metadata:
                stream_id = db_recording.recording_metadata["stream_id"]
                user_devices = db.query(Device).filter(
                    Device.users.any(id=current_user.id),
                    Device.is_active == True,
                    Device.stream_key == stream_id
                ).first()
                
            if not user_devices:
                raise HTTPException(status_code=403, detail="You do not have permission to access this recording")
        
        # Check if there's a ready HLS version
        hls_path = None
        hls_exists = False
        
        if db_recording.environment == "local" and db_recording.local_hls_path:
            hls_path = db_recording.local_hls_path
            hls_exists = os.path.exists(os.path.join(hls_path, "playlist.m3u8"))
        elif db_recording.environment == "aws" and db_recording.s3_hls_path:
            hls_path = db_recording.s3_hls_path
            hls_exists = True  # Assume S3 files exist if path is set
            
        if hls_exists:
            # Check if transcoding is completed
            if (db_recording.recording_metadata and 
                (db_recording.recording_metadata.get("transcoding_status") == "completed" or
                 db_recording.recording_metadata.get("processed", False) == True)):
                
                return {
                    "recording_id": recording_id,
                    "status": "ready",
                    "hls_path": hls_path,
                    "completed_at": db_recording.recording_metadata.get("transcoding_completed_at") if db_recording.recording_metadata else None,
                    "video_info": db_recording.recording_metadata.get("video_info", {}) if db_recording.recording_metadata else {}
                }
                
        # Check for processing task
        try:
            existing_task = await check_task_exists(recording_id)
            
            if existing_task:
                # Translate processing task status to our status format
                status_map = {
                    "processing": "processing",
                    "completed": "completed",
                    "failed": "failed"
                }
                
                client_status = status_map.get(existing_task["status"], "unknown")
                
                response = {
                    "recording_id": recording_id,
                    "status": client_status,
                    "task_id": existing_task["task_id"]
                }
                
                # Add error message if failed
                if client_status == "failed" and "error" in existing_task:
                    response["error"] = existing_task["error"]
                    
                return response
        except Exception as e:
            logger.error(f"Error checking task status: {str(e)}")
        
        # If we reach here, check the database metadata 
        if db_recording.recording_metadata and "transcoding_status" in db_recording.recording_metadata:
            status = db_recording.recording_metadata["transcoding_status"]
            
            response = {
                "recording_id": recording_id,
                "status": status,
                "started_at": db_recording.recording_metadata.get("transcoding_started_at"),
                "completed_at": db_recording.recording_metadata.get("transcoding_completed_at")
            }
            
            # Add error message if failed
            if status == "failed" and "transcoding_error" in db_recording.recording_metadata:
                response["error"] = db_recording.recording_metadata["transcoding_error"]
                response["can_retry"] = True
                
            return response
            
        # If we reach here, the recording hasn't been processed yet
        return {
            "recording_id": recording_id,
            "status": "not_processed",
            "message": "This recording has not been processed yet"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recording processing status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 