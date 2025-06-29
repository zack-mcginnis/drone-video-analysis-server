#!/bin/bash
# Script to deploy RTMP server and API server to separate AWS Lightsail instances

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

# Check if required environment variables are set for both instances
if [ -z "$RTMP_PUBLIC_IP" ] || [ -z "$API_PUBLIC_IP" ] || [ -z "$RTMP_SSH_KEY_PATH" ] || [ -z "$API_SSH_KEY_PATH" ] || [ -z "$SSH_USER" ]; then
    echo "Error: Required environment variables are not set."
    echo "Please make sure RTMP_PUBLIC_IP, API_PUBLIC_IP, RTMP_SSH_KEY_PATH, API_SSH_KEY_PATH, and SSH_USER are set in the .env file."
    exit 1
fi

# Check and fix SSH key permissions immediately
echo "Checking and fixing SSH key permissions..."
if [ ! -f "$RTMP_SSH_KEY_PATH" ]; then
    echo "Error: RTMP SSH key file does not exist at $RTMP_SSH_KEY_PATH"
    exit 1
fi

if [ ! -f "$API_SSH_KEY_PATH" ]; then
    echo "Error: API SSH key file does not exist at $API_SSH_KEY_PATH"
    exit 1
fi

chmod 600 "$RTMP_SSH_KEY_PATH"
chmod 600 "$API_SSH_KEY_PATH"
echo "SSH key permissions have been set to 600"

# Check if AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Warning: AWS credentials are not set in the .env file."
    echo "S3 upload functionality will not work without AWS credentials."
    read -p "Do you want to continue without AWS credentials? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Function to setup Docker on an instance
setup_docker() {
    local ip=$1
    local key_path=$2
    local remote_user=$3
    echo "Setting up Docker on instance $ip..."
    ssh -i "$key_path" -o StrictHostKeyChecking=no $remote_user@$ip << SETUP_EOF
        if grep -q "Amazon Linux 2023" /etc/os-release; then
            echo "Detected Amazon Linux 2023"
            if ! command -v docker &> /dev/null; then
                echo "Installing Docker for Amazon Linux 2023..."
                sudo dnf update -y
                sudo dnf install -y docker
                sudo systemctl enable docker.service
                sudo systemctl start docker.service
                sudo usermod -aG docker \$(whoami)
                echo "Docker installed successfully."
            else
                echo "Docker already installed."
                # Ensure Docker is running and user has proper permissions
                sudo systemctl restart docker.service
                sudo usermod -aG docker \$(whoami)
                # Verify Docker is running5d681821afb4
                sudo systemctl status docker.service
            fi
        else
            echo "Detected Amazon Linux 2"
            if ! command -v docker &> /dev/null; then
                echo "Installing Docker for Amazon Linux 2..."
                sudo yum update -y
                sudo amazon-linux-extras install docker -y
                sudo service docker start
                sudo systemctl enable docker
                sudo usermod -a -G docker \$(whoami)
                echo "Docker installed successfully."
            else
                echo "Docker already installed."
                # Ensure Docker is running and user has proper permissions
                sudo service docker restart
                sudo usermod -a -G docker \$(whoami)
                # Verify Docker is running
                sudo service docker status
            fi
        fi
        # Create project directory and set permissions
        sudo mkdir -p ~/drone-rtmp-project
        sudo chown -R \$(whoami):\$(whoami) ~/drone-rtmp-project
SETUP_EOF
}

# Create temporary directories and prepare files
TEMP_DIR=$(mktemp -d)
echo "Creating temporary directory: $TEMP_DIR"

# Copy necessary files
echo "Copying project files to temporary directory..."
cp -r rtmp-server $TEMP_DIR/
cp -r api-server $TEMP_DIR/

# Create tarballs for each service
echo "Creating project tarballs..."
tar -czf rtmp-project.tar.gz -C $TEMP_DIR rtmp-server
tar -czf api-project.tar.gz -C $TEMP_DIR api-server

# Setup Docker on both instances
setup_docker $RTMP_PUBLIC_IP $RTMP_SSH_KEY_PATH $SSH_USER
setup_docker $API_PUBLIC_IP $API_SSH_KEY_PATH $SSH_USER

# Deploy RTMP Server
echo "Deploying RTMP server to $RTMP_PUBLIC_IP..."
scp -i "$RTMP_SSH_KEY_PATH" rtmp-project.tar.gz "$SSH_USER@$RTMP_PUBLIC_IP:~/rtmp-project.tar.gz"
ssh -i "$RTMP_SSH_KEY_PATH" "$SSH_USER@$RTMP_PUBLIC_IP" << EOF
    mkdir -p ~/drone-rtmp-project
    tar -xzf rtmp-project.tar.gz -C ~/drone-rtmp-project
    rm rtmp-project.tar.gz
    cd ~/drone-rtmp-project/rtmp-server
    
    echo "Building RTMP server image..."
    sudo docker build -t rtmp-server .
    
    sudo docker stop rtmp-server-container 2>/dev/null || true
    sudo docker rm rtmp-server-container 2>/dev/null || true
    
    echo "Deploying RTMP server..."
    sudo docker run -d --restart always \
        --name rtmp-server-container \
        -p 1935:1935 \
        -p 80:80 \
        -p 8080:8080 \
        --log-driver json-file \
        --log-opt max-size=10m \
        --log-opt max-file=3 \
        -e ENVIRONMENT=aws \
        -e AWS_REGION=$AWS_REGION \
        -e S3_BUCKET=$S3_BUCKET \
        -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
        -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
        -e USE_LIGHTSAIL_BUCKET=$USE_LIGHTSAIL_BUCKET \
        -e API_SERVER_URL=http://$API_PUBLIC_IP:8000 \
        rtmp-server
EOF

# Deploy API Server with error handling
echo "Deploying API server to $API_PUBLIC_IP..."
ERROR_OUTPUT=$(scp -i "$API_SSH_KEY_PATH" -o ConnectTimeout=30 -o ServerAliveInterval=60 -o ServerAliveCountMax=3 api-project.tar.gz "$SSH_USER@$API_PUBLIC_IP:~/api-project.tar.gz" 2>&1) || {
    echo "ERROR: Failed to copy API project files"
    echo "Error output: $ERROR_OUTPUT"
    exit 1
}

# Create a temporary env file for the remote host
cat > remote_env.sh << EOF
export POSTGRES_HOST="${POSTGRES_HOST}"
export POSTGRES_PORT="${POSTGRES_PORT}"
export POSTGRES_DB="${POSTGRES_DB}"
export POSTGRES_USER="${POSTGRES_USER}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
export AWS_REGION="${AWS_REGION}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"
export S3_BUCKET="${S3_BUCKET}"
export USE_LIGHTSAIL_BUCKET="${USE_LIGHTSAIL_BUCKET}"
export CLOUDFRONT_DOMAIN="${CLOUDFRONT_DOMAIN}"
export AUTH0_DOMAIN="${AUTH0_DOMAIN}"
export AUTH0_AUDIENCE="${AUTH0_AUDIENCE}"
export AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID}"
export AUTH0_CLIENT_SECRET="${AUTH0_CLIENT_SECRET}"
export RTMP_SERVER_URL="http://${RTMP_PUBLIC_IP}:8080"
export TEMP_TOKEN_SECRET="${TEMP_TOKEN_SECRET}"
EOF

# Copy the env file to the remote host
ERROR_OUTPUT=$(scp -i "$API_SSH_KEY_PATH" -o ConnectTimeout=30 -o ServerAliveInterval=60 -o ServerAliveCountMax=3 remote_env.sh "$SSH_USER@$API_PUBLIC_IP:~/remote_env.sh" 2>&1) || {
    echo "ERROR: Failed to copy environment file"
    echo "Error output: $ERROR_OUTPUT"
    rm remote_env.sh
    exit 1
}

# Remove the local env file
rm remote_env.sh

ERROR_OUTPUT=$(ssh -i "$API_SSH_KEY_PATH" -o ConnectTimeout=30 -o ServerAliveInterval=60 -o ServerAliveCountMax=3 "$SSH_USER@$API_PUBLIC_IP" << 'EOF'
    set -e
    # Source the environment variables
    source ~/remote_env.sh
    rm ~/remote_env.sh

    # Ensure Docker is running
    sudo systemctl restart docker.service || sudo service docker restart
    sudo usermod -aG docker $(whoami)
    # Re-login to apply group changes
    exec sg docker -c '
    mkdir -p ~/drone-rtmp-project
    tar -xzf api-project.tar.gz -C ~/drone-rtmp-project || {
        echo "Failed to extract API project files"
        exit 1
    }
    rm api-project.tar.gz
    cd ~/drone-rtmp-project/api-server
    
    echo "Building API server image..."
    docker build -t api-server . || {
        echo "Failed to build API server image"
        exit 1
    }
    
    echo "Stopping and removing existing container if it exists..."
    docker stop api-server-container 2>/dev/null || true
    docker rm api-server-container 2>/dev/null || true



    docker run -d --restart always \
        --name api-server-container \
        -p 80:80 \
        -p 8000:8000 \
        --log-driver json-file \
        --log-opt max-size=10m \
        --log-opt max-file=3 \
        -e ENVIRONMENT=aws \
        -e POSTGRES_HOST="${POSTGRES_HOST}" \
        -e POSTGRES_PORT="${POSTGRES_PORT}" \
        -e POSTGRES_DB="${POSTGRES_DB}" \
        -e POSTGRES_USER="${POSTGRES_USER}" \
        -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
        -e AWS_REGION="${AWS_REGION}" \
        -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
        -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
        -e AWS_BUCKET_NAME="${S3_BUCKET}" \
        -e USE_LIGHTSAIL_BUCKET="${USE_LIGHTSAIL_BUCKET}" \
        -e CLOUDFRONT_DOMAIN="${CLOUDFRONT_DOMAIN}" \
        -e AUTH0_DOMAIN="${AUTH0_DOMAIN}" \
        -e AUTH0_AUDIENCE="${AUTH0_AUDIENCE}" \
        -e AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID}" \
        -e AUTH0_CLIENT_SECRET="${AUTH0_CLIENT_SECRET}" \
        -e RTMP_SERVER_URL="http://${RTMP_PUBLIC_IP}:8080" \
        -e TEMP_TOKEN_SECRET="${TEMP_TOKEN_SECRET}" \
        -e PYTHONUNBUFFERED=1 \
        api-server || {
            echo "Failed to start API server container"
            exit 1
        }

    # Check if containers are running
    echo "Checking if containers are running..."
    if ! docker ps | grep -q api-server-container; then
        echo "Error: API server container is not running"
        echo "API server container logs:"
        docker logs api-server-container 2>&1
        exit 1
    fi
    '
EOF
) || {
    echo "ERROR: Failed to deploy API server"
    echo "Error output: $ERROR_OUTPUT"
    exit 1
}

# Clean up local temporary files
echo "Cleaning up local temporary files..."
rm -rf $TEMP_DIR
rm rtmp-project.tar.gz api-project.tar.gz

# Check if deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment successful!"
    echo "RTMP server is running at rtmp://$RTMP_PUBLIC_IP/live"
    echo "HLS stream is available at http://$RTMP_PUBLIC_IP:8080/hls/drone_stream.m3u8"
    echo "API server is running at http://$API_PUBLIC_IP:8000"
    
    # Update webapp-client/.env.aws if it exists
    if [ -f webapp-client/.env.aws ]; then
        echo "Updating webapp-client/.env.aws..."
        sed -i "s|REACT_APP_HLS_STREAM_URL=.*|REACT_APP_HLS_STREAM_URL=http://$RTMP_PUBLIC_IP:8080/hls/drone_stream.m3u8|g" webapp-client/.env.aws
        if ! grep -q "REACT_APP_API_URL" webapp-client/.env.aws; then
            echo "REACT_APP_API_URL=http://$API_PUBLIC_IP:8000" >> webapp-client/.env.aws
        else
            sed -i "s|REACT_APP_API_URL=.*|REACT_APP_API_URL=http://$API_PUBLIC_IP:8000|g" webapp-client/.env.aws
        fi
    fi
    
    echo -e "\nIMPORTANT: Please ensure you have:"
    echo "1. Configured Lightsail firewall rules to allow traffic between instances"
    echo "2. Enabled ports 80 (HTTP), 1935 (RTMP), and 8080 (HLS) in your Lightsail firewall settings"
    echo "3. Set up proper security groups if using VPC peering"
    echo "4. Your API server is now accessible on both port 80 and 8000"
else
    echo "Deployment failed!"
    echo "Please check the logs for more information."
fi 