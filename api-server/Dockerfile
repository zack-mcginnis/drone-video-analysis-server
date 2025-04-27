FROM python:3.9-slim

WORKDIR /app

# Install dependencies including ffmpeg and nginx
RUN apt-get update && \
    apt-get install -y ffmpeg nginx && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app /app/app
COPY ./alembic /app/alembic
COPY ./alembic.ini /app/alembic.ini
COPY ./scripts /app/scripts

# Create the versions directory if it doesn't exist
RUN mkdir -p /app/alembic/versions && touch /app/alembic/versions/__init__.py

# Make the migration script executable
RUN chmod +x /app/scripts/run_migrations.py

# Remove default nginx config
RUN rm /etc/nginx/sites-enabled/default

# Create nginx configuration with proper header handling
RUN echo 'map $http_origin $cors_origin {\n\
    default "";\n\
    "http://localhost:3000" $http_origin;\n\
    "https://dronehub.stream" $http_origin;\n\
    "https://www.dronehub.stream" $http_origin;\n\
}\n\
\n\
server {\n\
    listen 80;\n\
    server_name _;\n\
    \n\
    # Trust the Lightsail Load Balancer\n\
    set_real_ip_from 10.0.0.0/8;\n\
    set_real_ip_from 172.16.0.0/12;\n\
    set_real_ip_from 192.168.0.0/16;\n\
    real_ip_header X-Forwarded-For;\n\
    \n\
    # Force HTTPS if the original request was HTTPS and not from localhost\n\
    if ($http_x_forwarded_proto = "http") {\n\
        set $redirect_https "1";\n\
    }\n\
    if ($http_origin = "http://localhost:3000") {\n\
        set $redirect_https "0";\n\
    }\n\
    if ($redirect_https = "1") {\n\
        return 301 https://$host$request_uri;\n\
    }\n\
    \n\
    location / {\n\
        proxy_pass http://localhost:8000;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;\n\
        proxy_set_header X-Forwarded-Host $host;\n\
        proxy_set_header X-Forwarded-Port $http_x_forwarded_port;\n\
        \n\
        # Remove any existing CORS headers from the backend response\n\
        proxy_hide_header Access-Control-Allow-Origin;\n\
        proxy_hide_header Access-Control-Allow-Methods;\n\
        proxy_hide_header Access-Control-Allow-Headers;\n\
        proxy_hide_header Access-Control-Allow-Credentials;\n\
        \n\
        # Add CORS headers if origin matches\n\
        add_header Access-Control-Allow-Origin $cors_origin always;\n\
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;\n\
        add_header Access-Control-Allow-Headers "Authorization, Origin, X-Requested-With, Content-Type, Accept, Range" always;\n\
        add_header Access-Control-Allow-Credentials "true" always;\n\
        \n\
        # Handle OPTIONS method for CORS preflight requests\n\
        if ($request_method = "OPTIONS") {\n\
            add_header Access-Control-Allow-Origin $cors_origin always;\n\
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;\n\
            add_header Access-Control-Allow-Headers "Authorization, Origin, X-Requested-With, Content-Type, Accept, Range" always;\n\
            add_header Access-Control-Allow-Credentials "true" always;\n\
            add_header Content-Length 0;\n\
            add_header Content-Type text/plain;\n\
            return 204;\n\
        }\n\
    }\n\
}\n' > /etc/nginx/conf.d/api.conf

# Test nginx configuration
RUN nginx -t

# Expose ports
EXPOSE 80 8000

# Create startup script with proper nginx configuration and service management
RUN echo '#!/bin/bash\n\
# Ensure nginx is not running\n\
nginx -s stop 2>/dev/null || true\n\
\n\
# Start nginx\n\
nginx\n\
\n\
# Start uvicorn\n\
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4\n\
' > /app/start.sh && chmod +x /app/start.sh

# Command to run both nginx and uvicorn
CMD ["/app/start.sh"] 