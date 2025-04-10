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
from app.models import User

from ..utils.video import process_video_for_streaming, get_video_info
from ..utils.s3 import get_s3_client, generate_presigned_url, download_from_s3
from app.services.auth import auth_service

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/recordings",
    tags=["recordings"],
    responses={404: {"description": "Not found"}},
)

RECORDINGS_DIR = "/recordings"
HLS_DIR = os.path.join(RECORDINGS_DIR, "hls")

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
    current_user: User = Depends(auth_service.get_current_user)
):
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
    current_user: User = Depends(auth_service.get_current_user)
):
    success = crud.delete_recording(db, recording_id=recording_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {"detail": "Recording deleted successfully"}

@router.get("/stream/{recording_id}")
async def stream_recording(
    recording_id: int, 
    request: Request, 
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
) -> Dict[str, Any]:
    """
    Stream a recording using HLS.
    
    Args:
        recording_id: ID of the recording to stream
        request: FastAPI request object
        db: Database session
    
    Returns:
        Dictionary containing stream URL and video information
    """
    try:
        # Get recording from database
        db_recording = crud.get_recording(db, recording_id=recording_id, user_id=current_user.id)
        if db_recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")

        # Ensure HLS directory exists
        os.makedirs(HLS_DIR, exist_ok=True)
        hls_output_dir = os.path.join(HLS_DIR, str(recording_id))

        # Check if we already have an HLS version
        if (db_recording.recording_metadata and 
            "hls_path" in db_recording.recording_metadata and 
            os.path.exists(os.path.join(db_recording.recording_metadata["hls_path"], "playlist.m3u8"))):
            
            logger.info(f"Using existing HLS version for recording {recording_id}")
            video_info = db_recording.recording_metadata.get("video_info", {})
            playlist_path = os.path.join(db_recording.recording_metadata["hls_path"], "playlist.m3u8")
        else:
            # Get the video file based on environment
            if db_recording.environment == "local":
                # Handle local file
                file_path = db_recording.file_path
                if not file_path.startswith('/recordings/'):
                    file_path = os.path.join(RECORDINGS_DIR, os.path.basename(file_path))

                if not os.path.exists(file_path):
                    logger.error(f"Recording file not found at: {file_path}")
                    raise HTTPException(status_code=404, detail="Recording file not found")

                # Process video for HLS streaming
                logger.info(f"Processing local video for streaming: {file_path}")
                playlist_path, video_info = process_video_for_streaming(file_path, hls_output_dir)

            else:
                # Handle AWS S3 file
                if not db_recording.s3_path:
                    raise HTTPException(status_code=400, detail="Recording does not have an S3 path")

                s3_path = db_recording.s3_path
                if s3_path.startswith("s3://"):
                    s3_path = s3_path[5:]

                # Download from S3 using pre-signed URL
                with tempfile.NamedTemporaryFile(suffix='.mp4') as temp_file:
                    logger.info(f"Downloading from S3: {s3_path}")
                    
                    if not download_from_s3(s3_path, temp_file.name):
                        logger.error("Failed to download file from S3")
                        raise HTTPException(status_code=500, detail="Error downloading recording from S3")

                    # Process video for HLS streaming
                    logger.info(f"Processing S3 video for streaming: {temp_file.name}")
                    playlist_path, video_info = process_video_for_streaming(temp_file.name, hls_output_dir)

            # Update recording metadata with HLS information
            metadata = db_recording.recording_metadata or {}
            metadata.update({
                "hls_path": hls_output_dir,
                "processed": True,
                "processed_at": datetime.now().isoformat(),
                "video_info": video_info
            })
            crud.update_recording_metadata(db, recording_id, metadata)

        # Construct the HLS URLs
        base_url = str(request.base_url).rstrip('/')
        stream_url = f"{base_url}/recordings/hls/{recording_id}/playlist.m3u8"
        
        return {
            "stream_url": stream_url,
            "format": "hls",
            "mime_type": "application/vnd.apple.mpegurl",
            "video_info": video_info
        }
        
    except Exception as e:
        logger.error(f"Error streaming recording {recording_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hls/{recording_id}/{file_name}")
async def get_hls_file(recording_id: str, file_name: str):
    """
    Serve HLS playlist and segment files.
    
    Args:
        recording_id: ID of the recording
        file_name: Name of the HLS file to serve
    
    Returns:
        FileResponse containing the requested HLS file
    """
    try:
        file_path = os.path.join(HLS_DIR, recording_id, file_name)
        
        if not os.path.exists(file_path):
            logger.error(f"HLS file not found: {file_path}")
            raise HTTPException(status_code=404, detail="HLS file not found")
            
        # Set content type based on file extension
        content_type = "application/vnd.apple.mpegurl" if file_name.endswith('.m3u8') else "video/mp2t"
        
        return FileResponse(
            path=file_path,
            media_type=content_type,
            filename=file_name
        )
        
    except Exception as e:
        logger.error(f"Error serving HLS file {file_name} for recording {recording_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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

def store_recording(video_data, video_id):
    """
    Store video with appropriate lifecycle configuration
    """
    s3_client = boto3.client('s3')
    
    # Store in Standard tier initially
    s3_client.put_object(
        Bucket='your-drone-video-storage',
        Key=f'videos/{video_id}.mp4',
        Body=video_data,
        StorageClass='STANDARD'
    )
    
    # Set lifecycle policy (this would be done once during bucket setup)
    # After 30 days, move to STANDARD_IA
    # After 90 days, move to GLACIER if not accessed

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

@router.post("/", response_model=schemas.Recording)
def create_recording(
    recording: schemas.RecordingCreate,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(auth_service.get_current_user)
):
    """Process a recording to create HLS streaming format"""
    db_recording = crud.get_recording(db, recording_id=recording.id, user_id=current_user.id)
    if db_recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Get the file path
    if db_recording.environment == "local":
        # Ensure file_path is relative to /recordings directory
        file_path = db_recording.file_path
        if not file_path.startswith('/recordings/'):
            file_path = os.path.join('/recordings', os.path.basename(file_path))
            
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Recording file not found")
        
        # Process the file
        try:
            output_dir = convert_to_streaming_formats(file_path, recording.id)
            
            # Update recording metadata
            metadata = db_recording.recording_metadata or {}
            metadata["processed"] = True
            metadata["hls_path"] = output_dir
            metadata["processed_at"] = datetime.now().isoformat()
            
            # Update the recording in the database
            db_recording = crud.update_recording_metadata(db, recording.id, metadata)
            
            return {"status": "success", "message": "Recording processed successfully", "output_dir": output_dir}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing recording: {str(e)}")
    else:
        # For AWS recordings, we would need to download from S3 first, process, then upload back
        # This is more complex and would require temporary storage
        raise HTTPException(status_code=400, detail="Processing AWS recordings is not supported yet")

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
    elif db_recording.file_path:
        file_format = os.path.splitext(db_recording.file_path)[1].lstrip('.')
    
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
    elif db_recording.file_path:
        file_format = os.path.splitext(db_recording.file_path)[1].lstrip('.')
    
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
    recording: schemas.RecordingCreate,
    db: Session = Depends(database.get_db)
):
    """
    Special endpoint for RTMP server to create recordings without authentication.
    This endpoint should only be accessible from the RTMP server.
    """
    try:
        # Find user by stream key
        user = db.query(User).filter(
            User.stream_keys.contains([stream_key])
        ).first()
        
        if not user:
            logger.error(f"No user found for stream key: {stream_key}")
            raise HTTPException(status_code=404, detail="Invalid stream key")
        
        # Set the user_id in the recording
        recording.user_id = user.id
        
        logger.info(f"Creating recording for user {user.id} with stream key {stream_key}")
        return crud.create_recording(db=db, recording=recording)
    except Exception as e:
        logger.error(f"Error creating recording from RTMP: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 