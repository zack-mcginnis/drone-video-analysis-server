# NGINX RTMP Server with Video Processing

This project implements an NGINX RTMP server that can receive video streams from DJI drones and perform real-time video processing. The server is containerized using Docker and can be deployed locally or to AWS EC2.

## Features

- NGINX RTMP server for receiving video streams
- Real-time video processing capabilities
- HLS stream output for web playback
- Docker containerization
- AWS EC2 deployment ready

## Prerequisites

- Docker and Docker Compose
- AWS account (for EC2 deployment)
- DJI drone with RTMP streaming capability

## Local Development

1. Clone this repository:

```bash
git clone https://github.com/yourusername/dji-rtmp-server.git
cd dji-rtmp-server
```

2. Build and start the server:

```bash
docker-compose up --build
```

3. The server will be available at:
- RTMP input: `rtmp://localhost:1935/live/stream`
- HLS playback: `http://localhost:8080/hls/stream.m3u8`
- Video streaming:
  - WebSocket: `ws://localhost:8080/ws/stream`
  - HTTP Stream: `http://localhost:8080/stream`
- HTTP API endpoints:
  - Server status: `http://localhost:8080/`
  - Stream info: `http://localhost:8080/api/stream-info`
  - Health check: `http://localhost:8080/api/health`
  - NGINX status: `http://localhost:8080/status`

## AWS EC2 Deployment

1. Launch an EC2 instance:
   - Log into AWS Console
   - Navigate to EC2 Dashboard
   - Click "Launch Instance"
   - Choose Amazon Linux 2 AMI
   - Select instance type (recommended: t2.medium or better)
   - Configure security group to allow inbound traffic:
     - TCP port 22 (SSH)
     - TCP port 1935 (RTMP)
     - TCP port 8080 (HTTP)
   - Launch instance and save the key pair

2. Copy files to EC2:
```bash
scp -i your-key.pem -r ./* ec2-user@your-ec2-instance:/home/ec2-user/rtmp-server
```

3. SSH into the instance:
```bash
ssh -i your-key.pem ec2-user@your-ec2-instance
```

4. Run the deployment script:
```bash
cd rtmp-server
chmod +x deploy.sh
./deploy.sh
```

5. The server will be available at:
- RTMP input: `rtmp://your-ec2-instance:1935/live/stream`
- HLS playback: `http://your-ec2-instance:8080/hls/stream.m3u8`

## Configuration

- NGINX configuration: `nginx.conf`
- Video processing logic: `process_stream.py`
- Docker configuration: `Dockerfile` and `docker-compose.yml`

## Customization

You can modify the video processing logic by editing `process_stream.py`. The current implementation adds a timestamp to the video stream, but you can add your own processing functions.

## Troubleshooting

1. If the Docker container fails to start:
   - Check Docker logs: `docker-compose logs`
   - Ensure ports 1935 and 8080 are not in use

2. If the stream doesn't work:
   - Verify the RTMP URL is correct
   - Check NGINX logs inside the container
   - Ensure the security group rules are properly configured (for EC2)

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]

## Testing with Mock Video

To test the server with mock video data, use the provided `send_stream.sh` script:

1. Make the script executable:
```bash
chmod +x send_stream.sh
```

2. Run the script:
```bash
# Stream with default settings (downloads and uses sample video)
./send_stream.sh

# Stream a specific video file
./send_stream.sh -i path/to/video.mp4

# Stream to a specific RTMP URL
./send_stream.sh -u rtmp://your-server:1935/live/stream

# Stream specific file to specific URL
./send_stream.sh -i path/to/video.mp4 -u rtmp://your-server:1935/live/stream
```

3. Monitor the logs:
```bash
# View NGINX access logs
docker-compose logs -f rtmp-server

# View specific log files inside the container
docker exec rtmp-server tail -f /var/log/nginx/rtmp_access.log
docker exec rtmp-server tail -f /var/log/nginx/stream_events.log
```

The script will:
- Download a sample video if no input file is specified
- Verify the video file and display its properties
- Stream the video in a continuous loop
- Show detailed FFmpeg output for debugging

You can stop the stream at any time with Ctrl+C.

Note: The script requires FFmpeg to be installed on your system. On Ubuntu/Debian, you can install it with:
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

## Monitoring Stream Status

The server provides several ways to monitor the stream status:

1. Stream Processing Logs:
```bash
# View frame processing logs
docker exec rtmp-server tail -f /var/log/nginx/stream_processing.log
```

2. RTMP Event Logs:
```bash
# View RTMP access logs
docker exec rtmp-server tail -f /var/log/nginx/rtmp_access.log

# View stream events (start/stop/play)
docker exec rtmp-server tail -f /var/log/nginx/stream_events.log
```

3. API Endpoints:
```bash
# Get current stream info
curl http://localhost:8080/api/stream-info
```

The logs will show:
- When frames are being received and at what FPS
- When the stream starts and stops
- When clients connect and disconnect
- Any errors or interruptions in the stream
