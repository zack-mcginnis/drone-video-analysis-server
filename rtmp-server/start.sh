#!/bin/bash
set -e

# Create log directory if it doesn't exist
mkdir -p /var/log/nginx
touch /var/log/nginx/recording.log
chmod 666 /var/log/nginx/recording.log

# Set up log redirection to Docker logs
rm -f /var/log/nginx/docker.pipe
mkfifo /var/log/nginx/docker.pipe
cat /var/log/nginx/docker.pipe > /proc/1/fd/1 &
tail -f /var/log/nginx/recording.log > /var/log/nginx/docker.pipe &

# Log environment variables (with partial masking for sensitive values)
echo "Starting RTMP server with environment variables:" >> /var/log/nginx/recording.log
echo "ENVIRONMENT=${ENVIRONMENT:-local}" >> /var/log/nginx/recording.log
echo "USE_LIGHTSAIL_BUCKET=${USE_LIGHTSAIL_BUCKET:-false}" >> /var/log/nginx/recording.log
echo "AWS_REGION=${AWS_REGION:-us-east-1}" >> /var/log/nginx/recording.log
echo "S3_BUCKET=${S3_BUCKET:-not set}" >> /var/log/nginx/recording.log
echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:0:4}...${AWS_ACCESS_KEY_ID:+is set}" >> /var/log/nginx/recording.log
echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:0:4}...${AWS_SECRET_ACCESS_KEY:+is set}" >> /var/log/nginx/recording.log
echo "API_SERVER_URL=${API_SERVER_URL:-not set}" >> /var/log/nginx/recording.log

# Export environment variables
export ENVIRONMENT=${ENVIRONMENT:-local}
export USE_LIGHTSAIL_BUCKET=${USE_LIGHTSAIL_BUCKET:-false}
export AWS_REGION=${AWS_REGION:-us-east-1}
export S3_BUCKET=${S3_BUCKET}
export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
export API_SERVER_URL=${API_SERVER_URL:-http://api-server:8000}

# Write variables to file
cat > /tmp/aws_env_vars.sh << EOF
ENVIRONMENT=${ENVIRONMENT:-local}
USE_LIGHTSAIL_BUCKET=${USE_LIGHTSAIL_BUCKET:-false}
AWS_REGION=${AWS_REGION:-us-east-1}
S3_BUCKET=${S3_BUCKET}
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
API_SERVER_URL=${API_SERVER_URL:-http://api-server:8000}
EOF

chmod 644 /tmp/aws_env_vars.sh

# Create directories with proper permissions
mkdir -p /recordings
chmod 777 /recordings

# Create stream mappings file
MAPPING_FILE="/recordings/stream_mappings.txt"
touch "$MAPPING_FILE"
chmod 666 "$MAPPING_FILE"

# Check if we're running locally (not in AWS)
if ! curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/ > /dev/null; then
    echo "Running locally, cleaning recordings directory..."
    find /recordings -type f -not -name "stream_mappings.txt" -delete
    find /recordings -type d -not -path "/recordings" -empty -delete
    echo "Recordings directory cleaned."
else
    echo "Running in AWS environment, skipping recordings cleanup."
fi

# Start nginx with correct path
exec /usr/local/nginx/sbin/nginx -g "daemon off;" -c /usr/local/nginx/conf/nginx.conf 