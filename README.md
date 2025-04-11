# DJI Drone Video Streaming and Analysis Platform

This project creates a scalable system for streaming, recording, and analyzing video from DJI drones. It consists of several microservices that work together to provide a robust video processing and analysis platform. The purpose of this project is to provide a private and secure system for storing and accessing your video data while removing the dependency on a 3rd party (DJI, Youtube) to access your data.

## Project Components

### 1. RTMP Server

The RTMP (Real-Time Messaging Protocol) server is responsible for receiving video data from the drone and converting it to a web-friendly format. It uses Nginx with the RTMP module to:

- Receive video streams via RTMP protocol
- Convert the video to HLS (HTTP Live Streaming) format
- Serve the HLS stream to web clients
- Enable cross-origin resource sharing (CORS) for web access
- Record video streams to local storage or S3
- Integrate with the API server for metadata management

The server runs in a Docker container and exposes:
- Port 1935 for RTMP input
- Port 8080 for HLS output

### 2. API Server

A FastAPI-based microservice that provides:
- RESTful API endpoints for video management
- Authentication and authorization via Auth0
- Video metadata storage in PostgreSQL
- Integration with storage services (local/S3)
- Real-time video analysis capabilities
- WebSocket support for live updates

### 3. Mock Video Source

A development tool that simulates a drone by:
- Connecting to the RTMP server
- Continuously streaming a sample video in a loop
- Using FFmpeg to encode the video in a format compatible with the RTMP server
- Testing the complete pipeline in development environments

### 4. PostgreSQL Database

Stores:
- Video metadata
- User information
- Analysis results
- System configuration

## Building and Running the Project

### Prerequisites

- Docker and Docker Compose
- Node.js and Yarn
- Git
- AWS CLI (for production deployment)

### Setup and Run

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd drone-video-analysis-server
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start the services**
   ```bash
   docker-compose up -d
   ```
   This will start:
   - RTMP server
   - API server
   - PostgreSQL database
   - Mock video source (optional)

### Stopping the Project

```bash
docker-compose down
```

## Development Notes

- The RTMP server accepts streams at `rtmp://localhost:1935/live/<stream-key>`
- The HLS stream is available at `http://localhost:8080/hls/<stream-key>.m3u8`
- API documentation is available at `http://localhost:8000/docs`
- WebSocket endpoint is at `ws://localhost:8000/ws`

## Production Deployment

The project can be deployed to AWS using the provided deployment script:

```bash
./deploy-to-aws.sh
```

See `AWS-DEPLOYMENT.md` for detailed deployment instructions.

## Data Storage

The platform supports multiple storage configurations:

### Local Development Environment
- Video metadata in PostgreSQL
- Video files in local `/recordings` directory
- Analysis results in PostgreSQL

### AWS Production Environment
- Video metadata in RDS PostgreSQL
- Video files in S3
- Analysis results in RDS PostgreSQL
- CloudWatch for logging and monitoring

## Security Features

- Auth0 integration for authentication
- Secure WebSocket connections
- Environment-based configuration
- AWS IAM role-based access control
- Encrypted data storage

## Monitoring and Logging

- Structured logging across all services
- CloudWatch integration in production
- Health check endpoints
- Performance metrics collection

## Troubleshooting

- Check service logs: `docker-compose logs <service-name>`
- Verify RTMP server status: `docker-compose ps`
- Check API server health: `http://localhost:8000/health`
- Review CloudWatch logs in production 