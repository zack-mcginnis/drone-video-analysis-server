import cv2
import numpy as np
from subprocess import Popen, PIPE

def process_frame(frame):
    # Add your custom processing here
    # This is just a simple example that adds a timestamp
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
    # FFmpeg command to read from RTMP stream
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', 'rtmp://localhost/live/stream',
        '-f', 'rawvideo',
        '-pix_fmt', 'bgr24',
        '-'
    ]

    # Start FFmpeg process
    process = Popen(ffmpeg_cmd, stdout=PIPE, stderr=PIPE)

    try:
        while True:
            # Read raw video frame
            raw_frame = process.stdout.read(1920 * 1080 * 3)  # Adjust size based on your stream
            if not raw_frame:
                break

            # Convert to numpy array
            frame = np.frombuffer(raw_frame, dtype=np.uint8)
            frame = frame.reshape((1080, 1920, 3))

            # Process frame
            processed_frame = process_frame(frame)

            # Here you could stream the processed frame back or save it
            # For now, we'll just display it (remove in production)
            cv2.imshow('Processed Stream', processed_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        process.terminate()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main() 