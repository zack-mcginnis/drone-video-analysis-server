#!/bin/bash
set -e

# Create HLS directory with proper permissions
mkdir -p /tmp/hls
chmod 777 /tmp/hls

# Create recordings directory if it doesn't exist
mkdir -p /recordings
chmod 777 /recordings

# Create a directory for nginx to store temporary files
mkdir -p /var/lib/nginx/tmp
chmod 777 /var/lib/nginx/tmp

# Create stream mappings file if it doesn't exist
MAPPING_FILE="/recordings/stream_mappings.txt"
touch "$MAPPING_FILE"
chmod 666 "$MAPPING_FILE"

# Check if we're running locally (not in AWS)
if ! curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/ > /dev/null; then
    echo "Running locally, cleaning recordings directory..."
    
    # Remove all files in the recordings directory except the mapping file
    find /recordings -type f -not -name "stream_mappings.txt" -delete
    find /recordings -type d -not -path "/recordings" -empty -delete
    
    echo "Recordings directory cleaned."
else
    echo "Running in AWS environment, skipping recordings cleanup."
fi

# Create log directory if it doesn't exist
mkdir -p /var/log/nginx
touch /var/log/nginx/recording.log
chmod 666 /var/log/nginx/recording.log

# Debug: List all directories to verify permissions
echo "Directory permissions:" >> /var/log/nginx/recording.log
ls -la / | grep recordings >> /var/log/nginx/recording.log
ls -la / | grep tmp >> /var/log/nginx/recording.log

# Start nginx
nginx -g "daemon off;" 