# DJI Drone Video Streaming Project

This project creates a system for streaming video from a DJI drone to a web application. It consists of three main components that work together to capture, process, and display the video stream.

## Project Components

### 1. RTMP Server

The RTMP (Real-Time Messaging Protocol) server is responsible for receiving video data from the drone and converting it to a web-friendly format. It uses Nginx with the RTMP module to:

- Receive video streams via RTMP protocol
- Convert the video to HLS (HTTP Live Streaming) format
- Serve the HLS stream to web clients
- Enable cross-origin resource sharing (CORS) for web access

The server runs in a Docker container and exposes two ports:
- Port 1935 for RTMP input
- Port 8080 for HLS output

### 2. Mock Video Source

Since we may not always have access to a physical DJI drone for development and testing, this component simulates a drone by:

- Connecting to the RTMP server
- Continuously streaming a sample video in a loop
- Using FFmpeg to encode the video in a format compatible with the RTMP server

This component also runs in a Docker container and automatically connects to the RTMP server when started.

### 3. Web Application Client

The web client is a React-based progressive web application that:

- Connects to the RTMP server to receive the video stream
- Displays the video using HLS.js, a JavaScript library for HLS playback
- Provides a responsive user interface for viewing the drone footage
- Handles network interruptions and reconnections gracefully

The web client runs locally on the host machine (not in a Docker container).

## Building and Running the Project

### Prerequisites

- Docker and Docker Compose
- Node.js and Yarn
- Git

### Setup and Run

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd drone-video-stream
   ```

2. **Start the Docker containers**
   ```bash
   docker-compose up -d
   ```
   This will build and start both the RTMP server and mock video source containers.

3. **Start the web application**
   ```bash
   cd webapp-client
   cp .env.example .env  # Create your environment file
   yarn install
   yarn start
   ```
   This will install the necessary dependencies and start the React development server.

4. **Access the web application**
   Open your browser and navigate to http://localhost:3000

### Stopping the Project

1. **Stop the web application**
   Press `Ctrl+C` in the terminal where the React app is running.

2. **Stop the Docker containers**
   ```bash
   docker-compose down
   ```

## Development Notes

- The RTMP server is configured to accept any RTMP stream at `rtmp://localhost:1935/live/<stream-key>`
- The HLS stream is available at `http://localhost:8080/hls/<stream-key>.m3u8`
- The mock video source uses `drone_stream` as the stream key
- The web application is configured to connect to `http://localhost:8080/hls/drone_stream.m3u8` by default (set in the `.env` file)

## Using with a Real DJI Drone

To use this system with a real DJI drone:

1. Configure the drone to stream to `rtmp://your-server-ip:1935/live/drone_stream`
2. Ensure the drone and server are on the same network or the server is accessible from the drone's network
3. No need to run the mock video source container when using a real drone

## Troubleshooting

- If the video doesn't appear, check the browser console for errors
- Verify that the RTMP server is running with `docker-compose ps`
- Check the RTMP server logs with `docker-compose logs rtmp-server`
- Ensure the stream URL in the web app's `.env` file matches the actual stream path

## Environment Configuration

This project uses a single `.env` file at the root directory for all environment variables:

1. **Create your environment file**
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file** with your specific configuration values.

3. **For local development**, the default values should work out of the box.

4. **For AWS deployment**, you'll need to fill in the AWS-specific variables before running the deploy script. 

## Data Storage

This project maintains full control over video data without exposing anything to DJI servers by using the following storage strategy:

### Local Development Environment
- Video metadata is stored in a local PostgreSQL database
- Video files are saved in a local `/recordings` directory on your machine

### AWS Production Environment
- Video metadata is stored in a deployed PostgreSQL database in AWS
- Video files are stored in an AWS S3 bucket

This approach provides:
- Complete data sovereignty
- No dependency on third-party cloud services for video storage
- Flexible deployment options with consistent architecture
- Secure and private data management 