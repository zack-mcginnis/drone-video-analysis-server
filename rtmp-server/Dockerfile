FROM tiangolo/nginx-rtmp

# Install required packages
RUN apt-get update && \
    apt-get install -y curl unzip python3 ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install AWS CLI
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf aws awscliv2.zip

# Create directories with proper permissions
RUN mkdir -p /recordings && \
    mkdir -p /var/log/nginx && \
    chmod -R 777 /recordings && \
    chmod -R 777 /var/log/nginx

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
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