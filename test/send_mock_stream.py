import subprocess
import time
import sys
import os

def stream_to_rtmp(input_file, rtmp_url):
    """
    Stream a video file to RTMP server using FFmpeg
    """
    ffmpeg_command = [
        'ffmpeg',
        '-re',  # Read input at native frame rate
        '-i', input_file,  # Input file
        '-c:v', 'libx264',  # Video codec
        '-preset', 'veryfast',  # Encoding preset
        '-c:a', 'aac',  # Audio codec
        '-f', 'flv',  # Force FLV format
        rtmp_url  # RTMP URL
    ]

    try:
        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"Streaming {input_file} to {rtmp_url}")
        print("Stream will run until completion")
        process.wait()
    except Exception as e:
        print(f"Error: {e}")
        if process:
            process.terminate()
            process.wait()

if __name__ == "__main__":
    # Get RTMP URL from environment variable or use default
    rtmp_url = os.getenv('RTMP_URL', 'rtmp://rtmp-server:1935/live/stream')
    input_file = "sample_videos/sample.mp4"

    # Allow command line arguments to override defaults
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        rtmp_url = sys.argv[2]

    # Ensure the input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found")
        sys.exit(1)

    # Start streaming
    stream_to_rtmp(input_file, rtmp_url) 