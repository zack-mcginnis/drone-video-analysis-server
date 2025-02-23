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

2. Build and start the development environment:

```bash
docker-compose -f docker-compose.dev.yml up --build
```

To run only the test container:
```bash
docker-compose -f docker-compose.dev.yml up test
```

3. The server will be available at:
- RTMP input: `rtmp://localhost:1935/live/stream`
- HLS playback: `http://localhost:8080/hls/stream.m3u8`

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
