FROM ubuntu:22.04

# Install required packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpcre3 \
    libpcre3-dev \
    libssl-dev \
    zlib1g-dev \
    wget \
    git \
    ffmpeg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create log directory with proper permissions
RUN mkdir -p /var/log/nginx && \
    chown -R www-data:www-data /var/log/nginx && \
    chmod -R 755 /var/log/nginx

# Download and compile NGINX with RTMP module
WORKDIR /tmp
RUN wget https://nginx.org/download/nginx-1.24.0.tar.gz && \
    tar zxf nginx-1.24.0.tar.gz && \
    git clone https://github.com/arut/nginx-rtmp-module.git && \
    cd nginx-1.24.0 && \
    ./configure --with-http_ssl_module --with-http_stub_status_module --add-module=../nginx-rtmp-module && \
    make && \
    make install

# Create necessary directories and set permissions
RUN mkdir -p /tmp/hls && \
    chown -R www-data:www-data /tmp/hls && \
    chmod -R 755 /tmp/hls

# Copy NGINX configuration
COPY nginx.conf /usr/local/nginx/conf/nginx.conf

# Copy and set permissions for scripts
COPY process_stream.py /usr/local/bin/process_stream.py
COPY stream_server.py /usr/local/bin/stream_server.py
RUN chmod +x /usr/local/bin/process_stream.py /usr/local/bin/stream_server.py && \
    chown www-data:www-data /usr/local/bin/process_stream.py /usr/local/bin/stream_server.py

# Install Python requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Forward ports
EXPOSE 1935
EXPOSE 8080

# Create startup script
RUN echo '#!/bin/bash\n\
# Ensure log directory exists and has proper permissions\n\
mkdir -p /var/log/nginx\n\
chown -R www-data:www-data /var/log/nginx\n\
chmod -R 755 /var/log/nginx\n\
\n\
echo "Starting Stream Server..."\n\
# Use Python in unbuffered mode (-u) and ensure output is properly redirected\n\
PYTHONUNBUFFERED=1 python3 -u /usr/local/bin/stream_server.py 2>&1 | tee -a /var/log/nginx/stream_server.log &\n\
STREAM_PID=${PIPESTATUS[0]}\n\
\n\
echo "Starting NGINX..."\n\
/usr/local/nginx/sbin/nginx -g "daemon off;" &\n\
NGINX_PID=$!\n\
\n\
# Wait for both processes to start\n\
sleep 2\n\
\n\
# Check if processes are running\n\
if ! kill -0 $STREAM_PID 2>/dev/null; then\n\
    echo "Stream server failed to start. Check logs above."\n\
    exit 1\n\
fi\n\
\n\
if ! kill -0 $NGINX_PID 2>/dev/null; then\n\
    echo "NGINX failed to start. Check /var/log/nginx/error.log"\n\
    exit 1\n\
fi\n\
\n\
echo "All services started successfully"\n\
\n\
trap "kill -TERM $NGINX_PID $STREAM_PID" SIGTERM\n\
\n\
wait -n\n\
\n\
kill -TERM $NGINX_PID $STREAM_PID 2>/dev/null\n\
wait' > /start.sh && \
    chmod +x /start.sh

# Start using the startup script
CMD ["/start.sh"] 