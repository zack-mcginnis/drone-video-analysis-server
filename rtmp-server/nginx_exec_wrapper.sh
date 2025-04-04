#!/bin/bash

# This script is called directly by nginx's exec_record_done
# It sources the environment variables and then calls the main wrapper

echo "$(date): nginx_exec_wrapper.sh started with args: $@" >> /var/log/nginx/recording.log

# Source the environment variables
if [ -f "/tmp/aws_env_vars.sh" ]; then
    # Read and set each variable directly
    while IFS='=' read -r key value; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        
        # Remove any leading/trailing whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        
        # Export the variable
        export "$key=$value"
    done < /tmp/aws_env_vars.sh
else
    echo "$(date): ERROR - /tmp/aws_env_vars.sh not found!" >> /var/log/nginx/recording.log
fi

# Create a new environment file with exports for the wrapper
WRAPPER_ENV="/tmp/wrapper_env.sh"

cat > "$WRAPPER_ENV" << EOF
#!/bin/bash
export ENVIRONMENT="${ENVIRONMENT}"
export USE_LIGHTSAIL_BUCKET="${USE_LIGHTSAIL_BUCKET}"
export AWS_REGION="${AWS_REGION}"
export S3_BUCKET="${S3_BUCKET}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-}"
export API_SERVER_URL="${API_SERVER_URL:-http://api-server:8000}"
exec /usr/local/bin/record_done_wrapper.sh "\$@"
EOF

chmod 755 "$WRAPPER_ENV"

# Call the wrapper script through the new environment file
exec "$WRAPPER_ENV" "$@" 