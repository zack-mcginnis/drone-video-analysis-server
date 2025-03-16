import ffmpeg
import os
import tempfile
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

def create_hls_playlist(input_file: str, output_dir: str, segment_duration: int = 10) -> str:
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
        os.makedirs(output_dir, exist_ok=True)
        
        playlist_path = os.path.join(output_dir, "playlist.m3u8")
        segment_pattern = os.path.join(output_dir, "segment_%03d.ts")
        
        # Create HLS playlist
        (
            ffmpeg
            .input(input_file)
            .output(
                segment_pattern,
                format="hls",
                hls_time=segment_duration,
                hls_playlist_type="vod",
                hls_segment_filename=segment_pattern,
                hls_list_size=0,
                hls_flags="independent_segments"
            )
            .run(quiet=True, overwrite_output=True)
        )
        
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
        probe = ffmpeg.probe(file_path)
        video_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        
        if video_info:
            return {
                'width': int(video_info.get('width', 0)),
                'height': int(video_info.get('height', 0)),
                'duration': float(probe.get('format', {}).get('duration', 0)),
                'bitrate': int(probe.get('format', {}).get('bit_rate', 0)),
                'format': probe.get('format', {}).get('format_name', ''),
                'codec': video_info.get('codec_name', '')
            }
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