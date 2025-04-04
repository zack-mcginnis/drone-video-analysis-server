#!/bin/bash
# Wrapper script to ensure environment variables are passed to record_done.sh

# Log that the wrapper is running
echo "$(date): record_done_wrapper.sh started with args: $@" >> /var/log/nginx/recording.log

# Load environment variables from a file that start.sh creates
if [ -f "/tmp/aws_env_vars.sh" ]; then
    echo "$(date): Loading environment variables from /tmp/aws_env_vars.sh" >> /var/log/nginx/recording.log
    # Use . instead of source for better compatibility
    set -a  # Automatically export all variables
    . /tmp/aws_env_vars.sh
    set +a  # Turn off auto-export
    
    # Explicitly export the variables we need
    export ENVIRONMENT
    export USE_LIGHTSAIL_BUCKET
    export AWS_REGION
    export S3_BUCKET
    export AWS_ACCESS_KEY_ID
    export AWS_SECRET_ACCESS_KEY
    export API_SERVER_URL
    export AWS_DEFAULT_REGION="$AWS_REGION"
fi

# Call record_done.sh with all arguments
/usr/local/bin/record_done.sh "$@"
EXIT_CODE=$?

exit $EXIT_CODE 