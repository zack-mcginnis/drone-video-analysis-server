#!/bin/bash
# Script to handle completed recordings

# Get the full path of the recorded file
RECORDING_PATH="$1"
STREAM_NAME="$2"
BASENAME="$3"

# Extract stream key from stream name
STREAM_KEY=$(echo "$STREAM_NAME" | cut -d'/' -f2)

# Initial environment variable logging
echo "$(date): Script started with environment settings:" >> /var/log/nginx/recording.log
echo "  ENVIRONMENT=${ENVIRONMENT:-'local'}" >> /var/log/nginx/recording.log
echo "  STREAM_KEY=$STREAM_KEY" >> /var/log/nginx/recording.log

# Only log AWS-related variables if we're in AWS environment
if [ "${ENVIRONMENT:-local}" = "aws" ]; then
    echo "  USE_LIGHTSAIL_BUCKET=${USE_LIGHTSAIL_BUCKET:-'not set'}" >> /var/log/nginx/recording.log
    echo "  AWS_REGION=${AWS_REGION:-'not set'}" >> /var/log/nginx/recording.log
    echo "  S3_BUCKET=${S3_BUCKET:-'not set'}" >> /var/log/nginx/recording.log
    echo "  AWS_ACCESS_KEY_ID is $(if [ -n "$AWS_ACCESS_KEY_ID" ]; then echo "set"; else echo "not set"; fi)" >> /var/log/nginx/recording.log
    echo "  AWS_SECRET_ACCESS_KEY is $(if [ -n "$AWS_SECRET_ACCESS_KEY" ]; then echo "set"; else echo "not set"; fi)" >> /var/log/nginx/recording.log
fi

# Log the recording completion
echo "$(date): Recording completed: $RECORDING_PATH" >> /var/log/nginx/recording.log
echo "$(date): Stream name: $STREAM_NAME, Basename: $BASENAME" >> /var/log/nginx/recording.log

# Load environment variables if needed
if [ "${ENVIRONMENT:-local}" = "aws" ]; then
    if [ -z "$AWS_REGION" ] || [ -z "$S3_BUCKET" ] || [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "$(date): Some AWS environment variables are not set, attempting to load them" >> /var/log/nginx/recording.log
        
        # Check if we're running in Docker
        if [ -f "/.dockerenv" ]; then
            echo "$(date): Running in Docker environment" >> /var/log/nginx/recording.log
        else
            # Try to load from .env file if not in Docker
            if [ -f "/.env" ]; then
                echo "$(date): Loading variables from /.env file" >> /var/log/nginx/recording.log
                export $(cat /.env | grep -v '#' | awk '/=/ {print $1}')
            elif [ -f "/app/.env" ]; then
                echo "$(date): Loading variables from /app/.env file" >> /var/log/nginx/recording.log
                export $(cat /app/.env | grep -v '#' | awk '/=/ {print $1}')
            elif [ -f "$HOME/.env" ]; then
                echo "$(date): Loading variables from $HOME/.env file" >> /var/log/nginx/recording.log
                export $(cat $HOME/.env | grep -v '#' | awk '/=/ {print $1}')
            else
                echo "$(date): No .env file found" >> /var/log/nginx/recording.log
            fi
        fi
    fi
fi

# Generate or retrieve a unique stream ID
MAPPING_FILE="/recordings/stream_mappings.txt"
mkdir -p "$(dirname "$MAPPING_FILE")"
touch "$MAPPING_FILE"
chmod 666 "$MAPPING_FILE"

# Use flock to ensure atomic read/write of the mapping file
STREAM_ID=""
(
    flock -x 200
    
    # Look for existing mapping for this stream name
    EXISTING_ID=$(grep "^${STREAM_NAME}:" "$MAPPING_FILE" | cut -d':' -f2)
    
    if [ -n "$EXISTING_ID" ]; then
        # Use existing stream ID
        STREAM_ID="$EXISTING_ID"
        echo "$(date): Using existing stream ID: $STREAM_ID" >> /var/log/nginx/recording.log
    else
        # Create a new stream ID with timestamp to ensure uniqueness
        STREAM_ID="${STREAM_NAME}_$(date +"%Y%m%d_%H%M%S")"
        # Save the mapping
        echo "${STREAM_NAME}:${STREAM_ID}" >> "$MAPPING_FILE"
        echo "$(date): Created new stream ID: $STREAM_ID" >> /var/log/nginx/recording.log
    fi
) 200>"$MAPPING_FILE.lock"

# Double-check that we have a stream ID
if [ -z "$STREAM_ID" ]; then
    # Fallback if something went wrong with the mapping file
    STREAM_ID="${STREAM_NAME}_$(date +"%Y%m%d_%H%M%S")"
    echo "$(date): Using fallback stream ID: $STREAM_ID" >> /var/log/nginx/recording.log
fi

# Create stream directory immediately
STREAM_DIR="/recordings/$STREAM_ID"
if ! mkdir -p "$STREAM_DIR" 2>/dev/null; then
    echo "$(date): ERROR: Failed to create stream directory: $STREAM_DIR" >> /var/log/nginx/recording.log
    # Try to diagnose the issue
    ls -la /recordings >> /var/log/nginx/recording.log 2>&1
    id >> /var/log/nginx/recording.log 2>&1
    exit 1
fi

# Get the nginx user and group
NGINX_USER=$(nginx -T 2>/dev/null | grep 'user' | awk '{print $2}' | sed 's/;$//')
NGINX_USER=${NGINX_USER:-nginx}  # Default to 'nginx' if not found

# Set proper ownership and permissions
chown -R ${NGINX_USER}:${NGINX_USER} "$STREAM_DIR" 2>/dev/null || true
chmod -R 777 "$STREAM_DIR" 2>/dev/null || true

# Verify directory is writable
if [ ! -w "$STREAM_DIR" ]; then
    echo "$(date): ERROR: Stream directory is not writable: $STREAM_DIR" >> /var/log/nginx/recording.log
    ls -la "$STREAM_DIR" >> /var/log/nginx/recording.log 2>&1
    exit 1
fi

# Get file size
FILE_SIZE=$(stat -c%s "$RECORDING_PATH" 2>/dev/null)
if [ -z "$FILE_SIZE" ] || ! [[ "$FILE_SIZE" =~ ^[0-9]+$ ]]; then
    echo "$(date): WARNING - Could not determine file size, using default value" >> /var/log/nginx/recording.log
    FILE_SIZE=0
fi
echo "$(date): File size: $FILE_SIZE bytes" >> /var/log/nginx/recording.log

# Determine file format from the file extension
FILE_FORMAT=$(echo "$RECORDING_PATH" | awk -F. '{print $NF}')
echo "$(date): File format detected: $FILE_FORMAT" >> /var/log/nginx/recording.log

# Create a timestamped filename for the final destination
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
FINAL_PATH="$STREAM_DIR/${TIMESTAMP}.mp4"

# If the file is FLV, convert it to MP4
if [ "$FILE_FORMAT" = "flv" ]; then
    echo "$(date): Converting FLV to MP4: $RECORDING_PATH -> $FINAL_PATH" >> /var/log/nginx/recording.log

    # Use ffmpeg to convert FLV to MP4 directly to the stream directory
    if ! ffmpeg -i "$RECORDING_PATH" -c:v libx264 -c:a aac -movflags +faststart "$FINAL_PATH" -y >> /var/log/nginx/recording.log 2>&1; then
        echo "$(date): ERROR: Failed to convert FLV to MP4" >> /var/log/nginx/recording.log
        # Move the original file to the stream directory with a timestamp
        FINAL_PATH="$STREAM_DIR/${TIMESTAMP}.flv"
        if ! mv "$RECORDING_PATH" "$FINAL_PATH"; then
            echo "$(date): ERROR: Failed to move original FLV file" >> /var/log/nginx/recording.log
            exit 1
        fi
        RECORDING_PATH="$FINAL_PATH"
        echo "$(date): Moved original file to: $FINAL_PATH" >> /var/log/nginx/recording.log
    else
        echo "$(date): Conversion successful" >> /var/log/nginx/recording.log
        # Remove the original FLV file to save space
        rm "$RECORDING_PATH"
        echo "$(date): Removed original FLV file" >> /var/log/nginx/recording.log
        # Update recording path to the MP4 file
        RECORDING_PATH="$FINAL_PATH"
        FILE_FORMAT="mp4"
    fi
else
    # File is already MP4, just move it to the stream directory
    echo "$(date): Moving MP4 file to stream directory: $RECORDING_PATH -> $FINAL_PATH" >> /var/log/nginx/recording.log
    if ! mv "$RECORDING_PATH" "$FINAL_PATH"; then
        echo "$(date): ERROR: Failed to move MP4 file to stream directory" >> /var/log/nginx/recording.log
        exit 1
    fi
    RECORDING_PATH="$FINAL_PATH"
    echo "$(date): Moved MP4 file to: $FINAL_PATH" >> /var/log/nginx/recording.log
fi

# Function to send recording metadata to API server
send_recording_metadata() {
    local file_path="$1"
    local s3_path="$2"
    local environment="$3"
    local file_format="$4"
    
    # Create JSON payload with stream ID
    JSON_PAYLOAD=$(cat <<EOF
{
    "stream_name": "$STREAM_NAME",
    "file_path": "$file_path",
    "s3_path": "$s3_path",
    "file_size": $FILE_SIZE,
    "environment": "$environment",
    "recording_metadata": {
        "file_size": $FILE_SIZE,
        "file_format": "$file_format",
        "stream_id": "$STREAM_ID"
    }
}
EOF
)
    
    # Send to API server with stream key in URL
    API_SERVER_URL=${API_SERVER_URL:-"http://api-server:8000"}
    
    # Make API request with better error handling
    CURL_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD" \
        "$API_SERVER_URL/recordings/rtmp/$STREAM_KEY" 2>&1)
    
    # Extract HTTP status code and response body
    HTTP_STATUS=$(echo "$CURL_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$CURL_RESPONSE" | sed '$d')
    
    # Check if API call was successful
    if [ $? -eq 0 ] && [ "$HTTP_STATUS" -eq 200 ]; then
        echo "$(date): Metadata sent to API server successfully" >> /var/log/nginx/recording.log
        echo "$(date): API Response: $RESPONSE_BODY" >> /var/log/nginx/recording.log
    else
        echo "$(date): Failed to send metadata to API server" >> /var/log/nginx/recording.log
        echo "$(date): HTTP Status: $HTTP_STATUS" >> /var/log/nginx/recording.log
        echo "$(date): Response: $RESPONSE_BODY" >> /var/log/nginx/recording.log
    fi
}

# Check environment setting
if [ "${ENVIRONMENT:-local}" = "aws" ]; then
    # We're running in AWS, upload to S3
    
    # Get the AWS region and bucket name from environment variables
    AWS_REGION=${AWS_REGION:-"us-east-1"}
    S3_BUCKET=${S3_BUCKET}
    USE_LIGHTSAIL_BUCKET=${USE_LIGHTSAIL_BUCKET:-"true"}
    
    echo "$(date): AWS environment detected. Using AWS_REGION=${AWS_REGION}, S3_BUCKET=${S3_BUCKET}" >> /var/log/nginx/recording.log
    
    # Create a directory structure for the stream in S3 using the unique stream ID
    S3_PATH="s3://$S3_BUCKET/recordings/$STREAM_ID/"
    S3_FILE_PATH="${S3_PATH}$(basename $RECORDING_PATH)"
    
    echo "$(date): Uploading recording to $S3_FILE_PATH" >> /var/log/nginx/recording.log
    
    # Install AWS CLI if not already installed
    if ! command -v aws &> /dev/null; then
        echo "$(date): Installing AWS CLI..." >> /var/log/nginx/recording.log
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
        unzip -q /tmp/awscliv2.zip -d /tmp
        /tmp/aws/install
        rm -rf /tmp/aws /tmp/awscliv2.zip
    fi
    
    # Configure AWS credentials if they're provided as environment variables
    if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "$(date): Configuring AWS credentials from environment variables" >> /var/log/nginx/recording.log
        
        # Export the credentials directly
        export AWS_ACCESS_KEY_ID
        export AWS_SECRET_ACCESS_KEY
        export AWS_REGION
        export AWS_DEFAULT_REGION="$AWS_REGION"
    else
        echo "$(date): WARNING: AWS credentials not provided as environment variables" >> /var/log/nginx/recording.log
        
        # Check if AWS credentials are available via EC2 instance role
        AWS_CREDENTIAL_RESPONSE=$(curl -s -f -m 1 http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>&1)
        if [ $? -eq 0 ]; then
            echo "$(date): EC2 instance role detected: $AWS_CREDENTIAL_RESPONSE" >> /var/log/nginx/recording.log
        else
            echo "$(date): No EC2 instance role credentials available" >> /var/log/nginx/recording.log
        fi
    fi
    
    # Set AWS CLI command with all required parameters
    if [ "$USE_LIGHTSAIL_BUCKET" = "true" ]; then
        echo "$(date): Using Lightsail bucket endpoint" >> /var/log/nginx/recording.log
        S3_ENDPOINT="--endpoint-url https://s3.${AWS_REGION}.amazonaws.com"
    else
        S3_ENDPOINT=""
    fi
    
    # Export AWS credentials again to ensure they're available for this command
    export AWS_ACCESS_KEY_ID
    export AWS_SECRET_ACCESS_KEY
    export AWS_REGION
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    # Use AWS CLI directly with credentials from environment variables
    echo "$(date): Running S3 upload command..." >> /var/log/nginx/recording.log
    aws s3 cp "$RECORDING_PATH" "$S3_FILE_PATH" --region "$AWS_REGION" $S3_ENDPOINT >> /var/log/nginx/recording.log 2>&1
    UPLOAD_STATUS=$?
    
    # Check if upload was successful
    if [ $UPLOAD_STATUS -eq 0 ]; then
        echo "$(date): Upload successful" >> /var/log/nginx/recording.log
        # Send recording metadata to API server
        send_recording_metadata "$RECORDING_PATH" "$S3_FILE_PATH" "${ENVIRONMENT:-aws}" "$FILE_FORMAT"
    else
        echo "$(date): ERROR: Upload failed with status code $UPLOAD_STATUS" >> /var/log/nginx/recording.log
        
        # Try again with additional debugging and explicit credentials
        echo "$(date): Retrying upload..." >> /var/log/nginx/recording.log
        
        # Explicitly set credentials again
        export AWS_ACCESS_KEY_ID
        export AWS_SECRET_ACCESS_KEY
        export AWS_REGION
        export AWS_DEFAULT_REGION="$AWS_REGION"
        
        # Retry with debug output
        aws s3 cp "$RECORDING_PATH" "$S3_FILE_PATH" --region "$AWS_REGION" $S3_ENDPOINT >> /var/log/nginx/recording.log 2>&1
        RETRY_STATUS=$?
        
        if [ $RETRY_STATUS -eq 0 ]; then
            echo "$(date): Retry successful" >> /var/log/nginx/recording.log
            send_recording_metadata "$RECORDING_PATH" "$S3_FILE_PATH" "${ENVIRONMENT:-aws}" "$FILE_FORMAT"
        else
            echo "$(date): ERROR: Retry also failed with status code $RETRY_STATUS" >> /var/log/nginx/recording.log
        fi
    fi
    
    # Handle local file management based on upload success
    if [ $UPLOAD_STATUS -eq 0 ] || [ ${RETRY_STATUS:-1} -eq 0 ]; then
        # Remove the local file to save space since we're in AWS
        rm "$RECORDING_PATH"
        echo "$(date): Upload was successful - local file removed to save space" >> /var/log/nginx/recording.log
    else
        echo "$(date): ERROR: Upload failed - keeping local file for debugging" >> /var/log/nginx/recording.log
        
        # Send metadata to API server, but without S3 path
        send_recording_metadata "$RECORDING_PATH" "" "${ENVIRONMENT:-aws}" "$FILE_FORMAT"
        
        # Move the file to a failed uploads directory instead of deleting it
        FAILED_UPLOADS_DIR="/recordings/failed_uploads"
        mkdir -p "$FAILED_UPLOADS_DIR"
        mv "$RECORDING_PATH" "$FAILED_UPLOADS_DIR/$(basename $RECORDING_PATH)"
        echo "$(date): Moved failed upload to $FAILED_UPLOADS_DIR" >> /var/log/nginx/recording.log
    fi
else
    # We're running locally, file is already in the stream directory
    echo "$(date): Running in local environment, skipping AWS upload" >> /var/log/nginx/recording.log
    
    # Send metadata to API server with the path
    send_recording_metadata "$RECORDING_PATH" "" "local" "$FILE_FORMAT"
    
    # Verify the file is playable
    echo "$(date): Verifying file is playable..." >> /var/log/nginx/recording.log
    ffprobe -v error "$RECORDING_PATH" >> /var/log/nginx/recording.log 2>&1
    if [ $? -eq 0 ]; then
        echo "$(date): File verification successful" >> /var/log/nginx/recording.log
    else
        echo "$(date): WARNING: File may not be playable" >> /var/log/nginx/recording.log
    fi
fi

# Clean up any stray files in the root recordings directory
find /recordings -maxdepth 1 -type f -name "*.mp4" -o -name "*.flv" | while read file; do
    echo "$(date): Found stray file in root directory: $file" >> /var/log/nginx/recording.log
    
    # Determine which stream it belongs to (if possible)
    if [[ "$file" == *"$STREAM_NAME"* ]]; then
        # Move to the current stream directory
        mv "$file" "$STREAM_DIR/$(basename "$file")"
        echo "$(date): Moved stray file to $STREAM_DIR/$(basename "$file")" >> /var/log/nginx/recording.log
    else
        # Create a catch-all directory for unidentified files
        mkdir -p "/recordings/unidentified"
        mv "$file" "/recordings/unidentified/$(basename "$file")"
        echo "$(date): Moved unidentified file to /recordings/unidentified/$(basename "$file")" >> /var/log/nginx/recording.log
    fi
done 