#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

# Check if required environment variables are set
if [ -z "$API_PUBLIC_IP" ] || [ -z "$API_SSH_KEY_PATH" ] || [ -z "$SSH_USER" ]; then
    echo "Error: Required environment variables are not set."
    echo "Please make sure API_PUBLIC_IP, API_SSH_KEY_PATH, and SSH_USER are set in the .env file."
    exit 1
fi

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# SSH into the instance and start monitoring logs
ssh -i "$API_SSH_KEY_PATH" "$SSH_USER@$API_PUBLIC_IP" '
    # Function to print logs with container name
    print_logs() {
        container=$1
        label=$2
        docker logs --tail 50 --follow "$container" 2>&1 | while read line; do
            echo "[$label] $line"
        done &
    }

    # Start monitoring each container
    print_logs "api-server-container" "API"
    print_logs "redis-container" "REDIS"
    print_logs "celery-worker-container" "CELERY"

    # Wait for any process to exit
    wait
' | while read -r line; do
    timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    if [[ $line == \[API\]* ]]; then
        echo -e "${GREEN}[$timestamp]${line}${NC}"
    elif [[ $line == \[REDIS\]* ]]; then
        echo -e "${BLUE}[$timestamp]${line}${NC}"
    elif [[ $line == \[CELERY\]* ]]; then
        echo -e "${RED}[$timestamp]${line}${NC}"
    fi
done 