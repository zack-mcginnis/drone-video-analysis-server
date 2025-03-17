#!/bin/bash
# Script to deploy RTMP server to an existing AWS Lightsail instance

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

# Check if required environment variables are set
if [ -z "$PUBLIC_IP" ] || [ -z "$SSH_KEY_PATH" ] || [ -z "$SSH_USER" ]; then
    echo "Error: Required environment variables are not set."
    echo "Please make sure PUBLIC_IP, SSH_KEY_PATH, and SSH_USER are set in the .env file."
    exit 1
fi

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

# Set default values for AWS region and S3 bucket if not provided
AWS_REGION=${AWS_REGION:-"us-west-2"}
S3_BUCKET=${S3_BUCKET:-"drone-video-recordings"}

# Check if the SSH key has the correct permissions
if [ "$(stat -c %a "$SSH_KEY_PATH")" != "600" ]; then
    echo "Warning: SSH key file has incorrect permissions. Setting to 600..."
    chmod 600 "$SSH_KEY_PATH"
fi

# Create a temporary directory for the project files
TEMP_DIR=$(mktemp -d)
echo "Creating temporary directory: $TEMP_DIR"

# Copy necessary files to the temporary directory
echo "Copying project files to temporary directory..."
cp -r rtmp-server $TEMP_DIR/
cp -r api-server $TEMP_DIR/

# Create a tarball of the project files
echo "Creating project tarball..."
tar -czf project.tar.gz -C $TEMP_DIR .

# Connect to the instance and set up Docker
echo "Setting up Docker on the instance..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no $SSH_USER@$PUBLIC_IP << 'SETUP_EOF'
    # Check OS version
    if grep -q "Amazon Linux 2023" /etc/os-release; then
        echo "Detected Amazon Linux 2023"
        # Install Docker on Amazon Linux 2023
        if ! command -v docker &> /dev/null; then
            echo "Installing Docker for Amazon Linux 2023..."
            sudo dnf update -y
            sudo dnf install -y docker
            sudo systemctl enable docker.service
            sudo systemctl start docker.service
            sudo usermod -aG docker $USER
            echo "Docker installed successfully."
        else
            echo "Docker already installed."
        fi
    else
        echo "Detected Amazon Linux 2"
        # Install Docker on Amazon Linux 2
        if ! command -v docker &> /dev/null; then
            echo "Installing Docker for Amazon Linux 2..."
            sudo yum update -y
            sudo amazon-linux-extras install docker -y
            sudo service docker start
            sudo systemctl enable docker
            sudo usermod -a -G docker $USER
            echo "Docker installed successfully."
        else
            echo "Docker already installed."
        fi
    fi
    
    # Create project directory if it doesn't exist
    mkdir -p ~/drone-rtmp-project
SETUP_EOF

# Copy the project tarball to the server
echo "Copying project files to the server..."
scp -i "$SSH_KEY_PATH" project.tar.gz "$SSH_USER@$PUBLIC_IP:~/project.tar.gz"

# Clean up local temporary files
echo "Cleaning up local temporary files..."
rm -rf $TEMP_DIR
rm project.tar.gz

# SSH into the server and deploy the Docker containers
echo "Deploying Docker containers on the server..."
ssh -i "$SSH_KEY_PATH" "$SSH_USER@$PUBLIC_IP" << EOF
    # Extract project files
    echo "Extracting project files..."
    mkdir -p ~/drone-rtmp-project
    tar -xzf project.tar.gz -C ~/drone-rtmp-project
    rm project.tar.gz
    
    # Change to project directory
    cd ~/drone-rtmp-project
    
    # Build Docker images on the server
    echo "Building Docker images on the server..."
    echo "Building RTMP server image..."
    sudo docker build -t rtmp-server ./rtmp-server
    echo "Building API server image..."
    sudo docker build -t api-server ./api-server
    
    # Stop and remove existing containers
    echo "Stopping and removing existing containers..."
    sudo docker stop rtmp-server-container 2>/dev/null || true
    sudo docker rm rtmp-server-container 2>/dev/null || true
    sudo docker stop api-server-container 2>/dev/null || true
    sudo docker rm api-server-container 2>/dev/null || true
    
    # Create a Docker network for the containers to communicate
    echo "Creating Docker network..."
    sudo docker network create drone-network 2>/dev/null || true
    
    # Deploy API server with environment variables from the .env file
    echo "Deploying API server..."
    echo "Debug: Environment variables being passed:"
    echo "POSTGRES_HOST=${POSTGRES_HOST}"
    echo "POSTGRES_USER=${POSTGRES_USER}"
    echo "POSTGRES_PORT=${POSTGRES_PORT}"
    echo "POSTGRES_DB=${POSTGRES_DB}"
    sudo docker run -d --restart always \
        --name api-server-container \
        --network drone-network \
        -p 8000:8000 \
        -e ENVIRONMENT=aws \
        -e AWS_REGION="${AWS_REGION}" \
        -e S3_BUCKET="${S3_BUCKET}" \
        -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
        -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
        -e USE_LIGHTSAIL_BUCKET="${USE_LIGHTSAIL_BUCKET}" \
        -e CLOUDFRONT_DOMAIN="${CLOUDFRONT_DOMAIN}" \
        -e POSTGRES_HOST="${POSTGRES_HOST}" \
        -e POSTGRES_PORT="${POSTGRES_PORT}" \
        -e POSTGRES_DB="${POSTGRES_DB}" \
        -e POSTGRES_USER="${POSTGRES_USER}" \
        -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
        api-server
    
    # Wait a moment for the container to start
    sleep 5
    
    # Run migrations inside the container
    echo "Running database migrations..."
    sudo docker exec api-server-container python /app/scripts/run_migrations.py
    
    # Deploy RTMP server
    echo "Deploying RTMP server..."
    sudo docker run -d --restart always \
        --name rtmp-server-container \
        --network drone-network \
        -p 1935:1935 \
        -p 80:80 \
        -p 8080:8080 \
        -e AWS_REGION=$AWS_REGION \
        -e S3_BUCKET=$S3_BUCKET \
        -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
        -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
        -e API_SERVER=http://api-server-container:8000 \
        rtmp-server
    
    # Check if containers are running
    echo "Checking container status..."
    sudo docker ps
EOF

# Check if deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment successful!"
    echo "RTMP server is running at rtmp://$PUBLIC_IP/live"
    echo "HLS stream is available at http://$PUBLIC_IP:8080/hls/drone_stream.m3u8"
    echo "API server is running at http://$PUBLIC_IP:8000"
    
    # Update webapp-client/.env.aws if it exists
    if [ -f webapp-client/.env.aws ]; then
        echo "Updating webapp-client/.env.aws..."
        sed -i "s|REACT_APP_HLS_STREAM_URL=.*|REACT_APP_HLS_STREAM_URL=http://$PUBLIC_IP:8080/hls/drone_stream.m3u8|g" webapp-client/.env.aws
        if ! grep -q "REACT_APP_API_URL" webapp-client/.env.aws; then
            echo "REACT_APP_API_URL=http://$PUBLIC_IP:8000" >> webapp-client/.env.aws
        else
            sed -i "s|REACT_APP_API_URL=.*|REACT_APP_API_URL=http://$PUBLIC_IP:8000|g" webapp-client/.env.aws
        fi
    fi
    
    # If a domain name is provided, suggest setting up a custom domain
    if [ ! -z "$DOMAIN_NAME" ]; then
        echo "To use your custom domain ($DOMAIN_NAME), set up DNS records to point to $PUBLIC_IP"
        echo "Consider setting up a custom domain with an AWS Load Balancer for HTTPS support."
    fi
else
    echo "Deployment failed!"
    echo "Please check the logs for more information."
fi 