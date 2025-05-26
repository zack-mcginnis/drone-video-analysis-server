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

# Function to convert MP4 to HLS format asynchronously
convert_to_hls_async() {
    local input_file="$1"
    local output_dir="$2"
    local status_file="$3"
    local segment_duration=6  # Duration of each segment in seconds
    
    # Ensure output directory exists
    mkdir -p "$output_dir"
    
    # Path for the HLS playlist
    local playlist_path="$output_dir/playlist.m3u8"
    local segment_pattern="$output_dir/segment_%03d.ts"
    
    echo "$(date): [ASYNC] Starting MP4 to HLS conversion: $input_file -> $playlist_path" >> /var/log/nginx/recording.log
    
    # Write status to indicate conversion started
    echo "CONVERTING" > "$status_file"
    
    # Run ffmpeg to convert to HLS with optimized settings for streaming
    if ffmpeg -y -i "$input_file" \
        -c:v libx264 -preset fast -crf 23 \
        -c:a aac -b:a 128k -ac 2 \
        -f hls \
        -hls_time "$segment_duration" \
        -hls_list_size 0 \
        -hls_segment_filename "$segment_pattern" \
        -hls_flags delete_segments+append_list \
        "$playlist_path" >> /var/log/nginx/recording.log 2>&1; then
        
        echo "$(date): [ASYNC] HLS conversion successful" >> /var/log/nginx/recording.log
        echo "SUCCESS" > "$status_file"
        return 0
    else
        echo "$(date): [ASYNC] ERROR: Failed to convert MP4 to HLS" >> /var/log/nginx/recording.log
        echo "FAILED" > "$status_file"
        return 1
    fi
}

# Function to wait for HLS conversion to complete
wait_for_hls_conversion() {
    local status_file="$1"
    local max_wait_time=1800  # 30 minutes maximum wait time
    local wait_interval=5     # Check every 5 seconds
    local elapsed_time=0
    
    echo "$(date): Waiting for HLS conversion to complete..." >> /var/log/nginx/recording.log
    
    while [ $elapsed_time -lt $max_wait_time ]; do
        if [ -f "$status_file" ]; then
            local status=$(cat "$status_file")
            case "$status" in
                "SUCCESS")
                    echo "$(date): HLS conversion completed successfully" >> /var/log/nginx/recording.log
                    return 0
                    ;;
                "FAILED")
                    echo "$(date): HLS conversion failed" >> /var/log/nginx/recording.log
                    return 1
                    ;;
                "CONVERTING")
                    # Still converting, continue waiting
                    ;;
                *)
                    echo "$(date): Unknown HLS conversion status: $status" >> /var/log/nginx/recording.log
                    ;;
            esac
        fi
        
        sleep $wait_interval
        elapsed_time=$((elapsed_time + wait_interval))
        
        # Log progress every minute
        if [ $((elapsed_time % 60)) -eq 0 ]; then
            echo "$(date): Still waiting for HLS conversion... (${elapsed_time}s elapsed)" >> /var/log/nginx/recording.log
        fi
    done
    
    echo "$(date): HLS conversion timed out after ${max_wait_time} seconds" >> /var/log/nginx/recording.log
    return 1
}

# Function to send recording metadata to API server
send_recording_metadata() {
    local file_path="$1"
    local s3_mp4_path="$2"
    local environment="$3"
    local file_format="$4"
    local hls_local_path="$5"
    local hls_s3_path="$6"
    
    # Create JSON payload with stream ID and HLS info
    JSON_PAYLOAD=$(cat <<EOF
{
    "stream_name": "$STREAM_NAME",
    "local_mp4_path": "$file_path",
    "s3_mp4_path": "$s3_mp4_path",
    "local_hls_path": "$hls_local_path",
    "s3_hls_path": "$hls_s3_path",
    "file_size": $FILE_SIZE,
    "environment": "$environment",
    "recording_metadata": {
        "file_size": $FILE_SIZE,
        "file_format": "$file_format",
        "stream_id": "$STREAM_ID",
        "hls_local_path": "$hls_local_path",
        "hls_s3_path": "$hls_s3_path"
    }
}
EOF
)
    
    # Log the payload for debugging
    echo "$(date): Sending recording metadata to API server" >> /var/log/nginx/recording.log
    echo "$(date): Stream key: $STREAM_KEY" >> /var/log/nginx/recording.log
    echo "$(date): API Server URL: $API_SERVER_URL" >> /var/log/nginx/recording.log
    echo "$(date): JSON Payload: $JSON_PAYLOAD" >> /var/log/nginx/recording.log
    
    # Send to API server with stream key in URL
    API_SERVER_URL=${API_SERVER_URL:-"http://api-server:8000"}
    
    # Make API request with better error handling
    CURL_RESPONSE=$(curl -v -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD" \
        "$API_SERVER_URL/recordings/rtmp/$STREAM_KEY" 2>&1)
    
    # Extract HTTP status code and response body
    HTTP_STATUS=$(echo "$CURL_RESPONSE" | tail -n1)
    RESPONSE_BODY=$(echo "$CURL_RESPONSE" | sed '$d')
    
    # Log the full response for debugging
    echo "$(date): Full curl response: $CURL_RESPONSE" >> /var/log/nginx/recording.log
    
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

# Create HLS directory and status file for async conversion
HLS_DIR="$STREAM_DIR/hls"
HLS_STATUS_FILE="$STREAM_DIR/hls_conversion_status"

# Start asynchronous HLS conversion
echo "$(date): Starting asynchronous HLS conversion" >> /var/log/nginx/recording.log
convert_to_hls_async "$RECORDING_PATH" "$HLS_DIR" "$HLS_STATUS_FILE" &
HLS_CONVERSION_PID=$!

echo "$(date): HLS conversion started in background (PID: $HLS_CONVERSION_PID)" >> /var/log/nginx/recording.log

# Wait for HLS conversion to complete
if wait_for_hls_conversion "$HLS_STATUS_FILE"; then
    HLS_CONVERSION_SUCCESS=true
    HLS_LOCAL_PATH="$HLS_DIR"
    echo "$(date): HLS conversion completed successfully" >> /var/log/nginx/recording.log
else
    HLS_CONVERSION_SUCCESS=false
    HLS_LOCAL_PATH=""
    echo "$(date): HLS conversion failed or timed out" >> /var/log/nginx/recording.log
    
    # Kill the conversion process if it's still running
    if kill -0 $HLS_CONVERSION_PID 2>/dev/null; then
        echo "$(date): Killing HLS conversion process (PID: $HLS_CONVERSION_PID)" >> /var/log/nginx/recording.log
        kill -TERM $HLS_CONVERSION_PID 2>/dev/null
        sleep 5
        if kill -0 $HLS_CONVERSION_PID 2>/dev/null; then
            kill -KILL $HLS_CONVERSION_PID 2>/dev/null
        fi
    fi
fi

# Clean up status file
rm -f "$HLS_STATUS_FILE"

# Check environment setting and handle file storage/upload
if [ "${ENVIRONMENT:-local}" = "aws" ]; then
    # We're running in AWS, upload to S3
    
    # Get the AWS region and bucket name from environment variables
    AWS_REGION=${AWS_REGION:-"us-east-1"}
    S3_BUCKET=${S3_BUCKET}
    USE_LIGHTSAIL_BUCKET=${USE_LIGHTSAIL_BUCKET:-"true"}
    
    echo "$(date): AWS environment detected. Using AWS_REGION=${AWS_REGION}, S3_BUCKET=${S3_BUCKET}" >> /var/log/nginx/recording.log
    
    # Create a directory structure for the stream in S3 using the unique stream ID
    S3_PATH="s3://$S3_BUCKET/recordings/$STREAM_ID/"
    S3_MP4_PATH="${S3_PATH}$(basename $RECORDING_PATH)"
    S3_HLS_PATH=""
    
    echo "$(date): Uploading recording to $S3_MP4_PATH" >> /var/log/nginx/recording.log
    
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
    
    # Upload HLS files if conversion was successful
    if [ "$HLS_CONVERSION_SUCCESS" = true ] && [ -d "$HLS_DIR" ]; then
        S3_HLS_PATH="${S3_PATH}hls/"
        echo "$(date): Uploading HLS files to $S3_HLS_PATH" >> /var/log/nginx/recording.log
        aws s3 cp "$HLS_DIR/" "$S3_HLS_PATH" --recursive --region "$AWS_REGION" $S3_ENDPOINT >> /var/log/nginx/recording.log 2>&1
        HLS_UPLOAD_STATUS=$?
        
        if [ $HLS_UPLOAD_STATUS -eq 0 ]; then
            echo "$(date): HLS files upload successful" >> /var/log/nginx/recording.log
        else
            echo "$(date): ERROR: HLS files upload failed with status code $HLS_UPLOAD_STATUS" >> /var/log/nginx/recording.log
            S3_HLS_PATH=""  # Reset the path if upload failed
        fi
    else
        echo "$(date): Skipping HLS upload (conversion failed or no HLS files)" >> /var/log/nginx/recording.log
    fi
    
    # Upload the MP4 file
    echo "$(date): Running S3 upload command for MP4 file..." >> /var/log/nginx/recording.log
    aws s3 cp "$RECORDING_PATH" "$S3_MP4_PATH" --region "$AWS_REGION" $S3_ENDPOINT >> /var/log/nginx/recording.log 2>&1
    UPLOAD_STATUS=$?
    
    # Check if upload was successful
    if [ $UPLOAD_STATUS -eq 0 ]; then
        echo "$(date): MP4 upload successful" >> /var/log/nginx/recording.log
        # Send recording metadata to API server with both MP4 and HLS paths
        send_recording_metadata "$RECORDING_PATH" "$S3_MP4_PATH" "${ENVIRONMENT:-aws}" "$FILE_FORMAT" "$HLS_LOCAL_PATH" "$S3_HLS_PATH"
    else
        echo "$(date): ERROR: MP4 upload failed with status code $UPLOAD_STATUS" >> /var/log/nginx/recording.log
        
        # Try again with additional debugging and explicit credentials
        echo "$(date): Retrying upload..." >> /var/log/nginx/recording.log
        
        # Explicitly set credentials again
        export AWS_ACCESS_KEY_ID
        export AWS_SECRET_ACCESS_KEY
        export AWS_REGION
        export AWS_DEFAULT_REGION="$AWS_REGION"
        
        # Retry with debug output
        aws s3 cp "$RECORDING_PATH" "$S3_MP4_PATH" --region "$AWS_REGION" $S3_ENDPOINT >> /var/log/nginx/recording.log 2>&1
        RETRY_STATUS=$?
        
        if [ $RETRY_STATUS -eq 0 ]; then
            echo "$(date): Retry successful" >> /var/log/nginx/recording.log
            send_recording_metadata "$RECORDING_PATH" "$S3_MP4_PATH" "${ENVIRONMENT:-aws}" "$FILE_FORMAT" "$HLS_LOCAL_PATH" "$S3_HLS_PATH"
        else
            echo "$(date): ERROR: Retry also failed with status code $RETRY_STATUS" >> /var/log/nginx/recording.log
        fi
    fi
    
    # Handle local file management based on upload success
    if [ $UPLOAD_STATUS -eq 0 ] || [ ${RETRY_STATUS:-1} -eq 0 ]; then
        # Remove the local files to save space since we're in AWS
        rm "$RECORDING_PATH"
        if [ "$HLS_CONVERSION_SUCCESS" = true ] && [ -d "$HLS_DIR" ]; then
            rm -rf "$HLS_DIR"
        fi
        echo "$(date): Upload was successful - local files removed to save space" >> /var/log/nginx/recording.log
    else
        echo "$(date): ERROR: Upload failed - keeping local files for debugging" >> /var/log/nginx/recording.log
        
        # Send metadata to API server, but without S3 paths
        send_recording_metadata "$RECORDING_PATH" "" "${ENVIRONMENT:-aws}" "$FILE_FORMAT" "$HLS_LOCAL_PATH" ""
        
        # Move the files to a failed uploads directory instead of deleting them
        FAILED_UPLOADS_DIR="/recordings/failed_uploads"
        mkdir -p "$FAILED_UPLOADS_DIR"
        mv "$RECORDING_PATH" "$FAILED_UPLOADS_DIR/$(basename $RECORDING_PATH)"
        if [ "$HLS_CONVERSION_SUCCESS" = true ] && [ -d "$HLS_DIR" ]; then
            mv "$HLS_DIR" "$FAILED_UPLOADS_DIR/hls_$(basename $RECORDING_PATH .mp4)"
        fi
        echo "$(date): Moved failed upload files to $FAILED_UPLOADS_DIR" >> /var/log/nginx/recording.log
    fi
else
    # We're running locally, files are already in the stream directory
    echo "$(date): Running in local environment, skipping AWS upload" >> /var/log/nginx/recording.log
    
    # Send metadata to API server with local paths
    send_recording_metadata "$RECORDING_PATH" "" "local" "$FILE_FORMAT" "$HLS_LOCAL_PATH" ""
    
    # Verify the MP4 file is playable
    echo "$(date): Verifying MP4 file is playable..." >> /var/log/nginx/recording.log
    ffprobe -v error "$RECORDING_PATH" >> /var/log/nginx/recording.log 2>&1
    if [ $? -eq 0 ]; then
        echo "$(date): MP4 file verification successful" >> /var/log/nginx/recording.log
    else
        echo "$(date): WARNING: MP4 file may not be playable" >> /var/log/nginx/recording.log
    fi
    
    # Verify HLS files if conversion was successful
    if [ "$HLS_CONVERSION_SUCCESS" = true ] && [ -f "$HLS_DIR/playlist.m3u8" ]; then
        echo "$(date): Verifying HLS playlist..." >> /var/log/nginx/recording.log
        if [ -s "$HLS_DIR/playlist.m3u8" ]; then
            echo "$(date): HLS playlist verification successful" >> /var/log/nginx/recording.log
            echo "$(date): HLS segments count: $(ls -1 $HLS_DIR/*.ts 2>/dev/null | wc -l)" >> /var/log/nginx/recording.log
        else
            echo "$(date): WARNING: HLS playlist is empty" >> /var/log/nginx/recording.log
        fi
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

echo "$(date): Recording processing completed for stream: $STREAM_NAME" >> /var/log/nginx/recording.log 