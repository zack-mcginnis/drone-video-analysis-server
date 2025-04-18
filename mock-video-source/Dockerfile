FROM jrottenberg/ffmpeg:4.4-ubuntu

# Install curl for health check
RUN apt-get update && apt-get install -y curl

# Download a sample video file
RUN mkdir -p /videos && \
    curl -o /videos/sample.mp4 https://download.samplelib.com/mp4/sample-5s.mp4

COPY stream.sh /stream.sh
RUN chmod +x /stream.sh

COPY sample.mp4 /sample.mp4

# Make sure the script is properly formatted with Unix line endings
RUN sed -i 's/\r$//' /stream.sh

# Use ENTRYPOINT instead of CMD
ENTRYPOINT ["/stream.sh"] 