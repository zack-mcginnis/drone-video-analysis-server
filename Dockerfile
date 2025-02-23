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

# Download and compile NGINX with RTMP module
WORKDIR /tmp
RUN wget https://nginx.org/download/nginx-1.24.0.tar.gz && \
    tar zxf nginx-1.24.0.tar.gz && \
    git clone https://github.com/arut/nginx-rtmp-module.git && \
    cd nginx-1.24.0 && \
    ./configure --with-http_ssl_module --with-http_stub_status_module --add-module=../nginx-rtmp-module && \
    make && \
    make install

# Create necessary directories
RUN mkdir -p /var/log/nginx && \
    mkdir -p /tmp/hls

# Copy NGINX configuration
COPY nginx.conf /usr/local/nginx/conf/nginx.conf

# Copy processing script
COPY process_stream.py /usr/local/bin/process_stream.py

# Install Python requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# Forward ports
EXPOSE 1935
EXPOSE 8080

# Create startup script
RUN echo '#!/bin/bash\n\
echo "Starting NGINX..."\n\
/usr/local/nginx/sbin/nginx -g "daemon off;" &\n\
NGINX_PID=$!\n\
\n\
# Trap SIGTERM and forward it to NGINX\n\
trap "kill -TERM $NGINX_PID" SIGTERM\n\
\n\
# Wait for NGINX to exit\n\
wait $NGINX_PID' > /start.sh && \
    chmod +x /start.sh

# Start using the startup script
CMD ["/start.sh"] 