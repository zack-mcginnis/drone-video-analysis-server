import os
import sys
import cv2
import numpy as np
from subprocess import Popen, PIPE
import time
import logging
import threading
import select

# Configure logging to write to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

def monitor_ffmpeg_output(process):
    """Monitor FFmpeg stderr for connection and streaming info"""
    while True:
        if process.stderr is None:
            break
            
        if select.select([process.stderr], [], [], 1.0)[0]:
            line = process.stderr.readline().decode()
            if line:
                if "Connection" in line or "Stream" in line:
                    logging.info(f"FFmpeg: {line.strip()}")
                elif "Error" in line or "error" in line:
                    logging.error(f"FFmpeg: {line.strip()}")

def process_frame(frame):
    # Add timestamp to frame
    timestamp = cv2.putText(
        frame,
        f"Time: {cv2.getTickCount() / cv2.getTickFrequency():.2f}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )
    return timestamp

def main():
    try:
        logging.info(f"Starting process_stream.py (PID: {os.getpid()})")
        
        last_frame_time = time.time()
        frames_received = 0
        total_frames = 0
        
        # FFmpeg command to read from RTMP stream
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', 'rtmp://localhost/live/stream',
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-loglevel', 'info',
            '-stats',
            '-'
        ]
        
        logging.info(f"Starting FFmpeg with command: {' '.join(ffmpeg_cmd)}")
        
        # Start FFmpeg process
        process = Popen(ffmpeg_cmd, stdout=PIPE, stderr=PIPE, bufsize=10**8)
        logging.info(f"FFmpeg process started with PID: {process.pid}")
        
        # Start FFmpeg output monitoring
        monitor_thread = threading.Thread(target=monitor_ffmpeg_output, args=(process,))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        while True:
            # Check if FFmpeg process is still running
            if process.poll() is not None:
                stderr = process.stderr.read().decode()
                logging.error(f"FFmpeg process exited with code {process.poll()}: {stderr}")
                break
                
            # Read raw video frame
            raw_frame = process.stdout.read(1920 * 1080 * 3)
            if not raw_frame:
                if time.time() - last_frame_time > 5:
                    logging.warning("No frames received for 5 seconds")
                continue

            # Update frame statistics
            frames_received += 1
            total_frames += 1
            
            if time.time() - last_frame_time >= 1:
                fps = frames_received / (time.time() - last_frame_time)
                logging.info(f"Receiving frames: {fps:.2f} fps (Total: {total_frames})")
                frames_received = 0
                last_frame_time = time.time()

            # Process frame
            try:
                frame = np.frombuffer(raw_frame, dtype=np.uint8)
                frame = frame.reshape((1080, 1920, 3))
                process_frame(frame)
            except Exception as e:
                logging.error(f"Error processing frame: {e}")
                continue

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'process' in locals():
            process.terminate()
            try:
                process.wait(timeout=5)
            except:
                process.kill()

if __name__ == "__main__":
    main() 