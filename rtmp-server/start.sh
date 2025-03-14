#!/bin/sh
set -e

# Create HLS directory if it doesn't exist
mkdir -p /tmp/hls

# Start nginx
nginx -g "daemon off;" 