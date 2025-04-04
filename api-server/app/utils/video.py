import ffmpeg
import os
import tempfile
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

def ensure_directory(directory: str) -> None:
    """Ensure a directory exists and is writable."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    if not os.access(directory, os.W_OK):
        raise PermissionError(f"Directory is not writable: {directory}")

def create_hls_playlist(input_file: str, output_dir: str, segment_duration: int = 6) -> str:
    """
    Create an HLS playlist from an input video file.
    
    Args:
        input_file: Path to the input video file
        output_dir: Directory to store the HLS files
        segment_duration: Duration of each segment in seconds
        
    Returns:
        Path to the HLS playlist file
    """
    try:
        ensure_directory(output_dir)
        
        # First verify the input file exists and is readable
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")
        if not os.access(input_file, os.R_OK):
            raise PermissionError(f"Input file is not readable: {input_file}")

        # Get video info first to verify the file is valid
        probe = ffmpeg.probe(input_file)
        video_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if not video_info:
            raise ValueError(f"No video stream found in file: {input_file}")

        logger.info(f"Processing video file: {input_file}")
        logger.info(f"Video info: {video_info}")
        
        playlist_path = os.path.join(output_dir, "playlist.m3u8")
        segment_pattern = os.path.join(output_dir, "segment_%03d.ts")

        # Start with a simple single-quality HLS conversion
        command = [
            "ffmpeg",
            "-y",  # Overwrite output files
            "-i", input_file,
            "-c:v", "libx264",     # Video codec
            "-preset", "fast",      # Encoding preset
            "-crf", "23",          # Quality level
            "-c:a", "aac",         # Audio codec
            "-b:a", "128k",        # Audio bitrate
            "-ac", "2",            # Audio channels
            "-f", "hls",
            "-hls_time", str(segment_duration),
            "-hls_list_size", "0", # Keep all segments
            "-hls_segment_filename", segment_pattern,
            playlist_path
        ]
        
        logger.info(f"Running ffmpeg command: {' '.join(command)}")
        
        # Run ffmpeg with output capture
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"ffmpeg conversion failed with output:\n{result.stderr}")
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")
            
        if not os.path.exists(playlist_path):
            raise FileNotFoundError(f"HLS playlist was not created at: {playlist_path}")
            
        logger.info(f"Successfully created HLS playlist at: {playlist_path}")
        return playlist_path
        
    except Exception as e:
        logger.error(f"Error creating HLS playlist: {str(e)}")
        raise

def get_video_info(file_path: str) -> dict:
    """
    Get information about a video file.
    
    Args:
        file_path: Path to the video file
        
    Returns:
        Dictionary with video information
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")
            
        probe = ffmpeg.probe(file_path)
        video_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        
        if video_info:
            info = {
                'width': int(video_info.get('width', 0)),
                'height': int(video_info.get('height', 0)),
                'duration': float(probe.get('format', {}).get('duration', 0)),
                'bitrate': int(probe.get('format', {}).get('bit_rate', 0)),
                'format': probe.get('format', {}).get('format_name', ''),
                'codec': video_info.get('codec_name', ''),
                'size': os.path.getsize(file_path)
            }
            logger.info(f"Retrieved video info: {info}")
            return info
        return {}
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return {}

def convert_flv_to_mp4(input_file: str, output_file: str) -> bool:
    """
    Convert an FLV file to MP4.
    
    Args:
        input_file: Path to the input FLV file
        output_file: Path to the output MP4 file
        
    Returns:
        True if conversion was successful, False otherwise
    """
    try:
        (
            ffmpeg
            .input(input_file)
            .output(output_file, codec='copy')
            .run(quiet=True, overwrite_output=True)
        )
        return True
    except Exception as e:
        logger.error(f"Error converting FLV to MP4: {str(e)}")
        return False

def process_video_for_streaming(input_file: str, output_dir: str) -> Tuple[str, dict]:
    """
    Process a video file for streaming by converting to HLS format.
    
    Args:
        input_file: Path to the input video file
        output_dir: Directory to store the processed files
        
    Returns:
        Tuple of (playlist_path, video_info)
    """
    try:
        # First check if HLS version already exists
        playlist_path = os.path.join(output_dir, "playlist.m3u8")
        if os.path.exists(playlist_path):
            logger.info(f"HLS playlist already exists at: {playlist_path}")
            return playlist_path, get_video_info(input_file)
            
        # Ensure input file exists and is readable
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")
        if not os.access(input_file, os.R_OK):
            raise PermissionError(f"Input file is not readable: {input_file}")
            
        # Get video information
        logger.info(f"Getting video info for: {input_file}")
        video_info = get_video_info(input_file)
        if not video_info:
            raise ValueError(f"Could not get video information from: {input_file}")
            
        # Create HLS playlist
        logger.info(f"Creating HLS playlist in: {output_dir}")
        playlist_path = create_hls_playlist(input_file, output_dir)
        
        return playlist_path, video_info
    except Exception as e:
        logger.error(f"Error processing video for streaming: {str(e)}")
        raise 