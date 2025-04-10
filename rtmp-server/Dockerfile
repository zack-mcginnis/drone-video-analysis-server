FROM debian:bullseye-slim as builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    libpcre3-dev \
    libssl-dev \
    zlib1g-dev \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Download and extract NGINX
ENV NGINX_VERSION=1.24.0
RUN wget http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz && \
    tar zxf nginx-${NGINX_VERSION}.tar.gz && \
    rm nginx-${NGINX_VERSION}.tar.gz

# Clone RTMP module
RUN git clone https://github.com/arut/nginx-rtmp-module.git

# Build NGINX with RTMP and auth_request modules
WORKDIR /nginx-${NGINX_VERSION}
RUN ./configure \
    --prefix=/usr/local/nginx \
    --with-http_ssl_module \
    --with-http_auth_request_module \
    --add-module=../nginx-rtmp-module \
    --with-debug && \
    make && \
    make install

# Start fresh with a new stage
FROM debian:bullseye-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    curl \
    unzip \
    python3 \
    ffmpeg \
    libpcre3 \
    libssl1.1 \
    zlib1g \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install AWS CLI
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf aws awscliv2.zip

# Copy NGINX from builder stage
COPY --from=builder /usr/local/nginx /usr/local/nginx

# Create necessary directories
RUN mkdir -p /recordings && \
    mkdir -p /var/log/nginx && \
    chmod -R 777 /recordings && \
    chmod -R 777 /var/log/nginx

# Add NGINX to PATH
ENV PATH="/usr/local/nginx/sbin:${PATH}"

# Copy configuration files
COPY nginx.conf /usr/local/nginx/conf/nginx.conf
COPY start.sh /start.sh
COPY record_done.sh /usr/local/bin/record_done.sh
COPY record_done_wrapper.sh /usr/local/bin/record_done_wrapper.sh
COPY nginx_exec_wrapper.sh /usr/local/bin/nginx_exec_wrapper.sh

# Make scripts executable
RUN chmod +x /start.sh && \
    chmod +x /usr/local/bin/record_done.sh && \
    chmod +x /usr/local/bin/record_done_wrapper.sh && \
    chmod +x /usr/local/bin/nginx_exec_wrapper.sh

# The environment variables are now passed at runtime via docker-compose.yml
# or the docker run command, so we don't need to set defaults here

EXPOSE 1935
EXPOSE 80
EXPOSE 8080

CMD ["/start.sh"] 