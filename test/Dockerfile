FROM python:3.9-slim

# Install FFmpeg and other dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy test files
COPY requirements.txt .
COPY send_mock_stream.py .
COPY test_server.py .

# Create directory for sample videos
RUN mkdir -p sample_videos

# Download sample video
RUN wget -O sample_videos/sample.mp4 https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for the RTMP server
ENV RTMP_SERVER=rtmp-server

# Command to run tests
CMD ["python", "test_server.py"] 