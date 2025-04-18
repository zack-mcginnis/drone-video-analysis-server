#!/bin/bash
set -e

# Wait for RTMP server to be ready
echo "Waiting for RTMP server to be ready..."
until curl -s http://rtmp-server:8080/stat > /dev/null; do
    echo "RTMP server not ready yet. Waiting..."
    sleep 2
done

echo "RTMP server is ready. Starting video stream..."

# Loop the video stream to RTMP server
while true; do
    echo "Starting ffmpeg stream..."
    # Use exec to replace the shell process with ffmpeg
    ffmpeg -re -i /sample.mp4 -c:v libx264 -c:a aac -f flv rtmp://rtmp-server:1935/live/RTCzYugC || true
    echo "Stream ended. Restarting in 1 second..."
    sleep 1
done 