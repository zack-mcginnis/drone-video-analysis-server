#!/bin/bash
# Script to deploy RTMP server to an existing AWS Lightsail instance

# Configuration - MODIFY THESE VALUES
PUBLIC_IP="YOUR_STATIC_IP_ADDRESS"  # Your static IP
SSH_KEY_PATH="~/.ssh/id_rsa"  # Path to your SSH key
SSH_USER="ec2-user"  # Default user for Amazon Linux 2/2023

# Validate inputs
if [[ "$PUBLIC_IP" == "YOUR_STATIC_IP_ADDRESS" ]]; then
    echo "Error: Please edit the script to set your static IP address."
    exit 1
fi

echo "Deploying to Lightsail instance at $PUBLIC_IP..."

# Expand the SSH key path if it uses ~
SSH_KEY_PATH="${SSH_KEY_PATH/#\~/$HOME}"

# Check if the SSH key exists
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "Error: SSH key not found at $SSH_KEY_PATH"
    exit 1
fi

# Fix SSH key permissions
echo "Setting correct permissions for SSH key..."
chmod 600 "$SSH_KEY_PATH"
echo "SSH key permissions updated."

# Connect to the instance and set up Docker
echo "Setting up Docker on the instance..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no $SSH_USER@$PUBLIC_IP << 'EOF'
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
    
    # Create directory for RTMP server
    mkdir -p ~/rtmp-server
    
    # We need to re-login to apply the docker group membership
    # For now, use sudo for docker commands
    
    # Stop and remove existing container if it exists
    if sudo docker ps -a | grep -q rtmp-server-container; then
        echo "Stopping and removing existing container..."
        sudo docker stop rtmp-server-container
        sudo docker rm rtmp-server-container
    fi
EOF

# Copy files to the instance
echo "Copying files to the instance..."
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no rtmp-server/Dockerfile rtmp-server/nginx.conf rtmp-server/start.sh $SSH_USER@$PUBLIC_IP:~/rtmp-server/

# Build and run the Docker container
echo "Building and running the Docker container..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no $SSH_USER@$PUBLIC_IP << 'EOF'
    cd ~/rtmp-server
    
    # Make start.sh executable
    chmod +x start.sh
    
    # Build Docker image (using sudo since we haven't re-logged in yet)
    sudo docker build -t rtmp-server .
    
    # Run container
    sudo docker run -d --restart always -p 1935:1935 -p 8080:8080 --name rtmp-server-container rtmp-server
    
    echo "Docker container started. You may need to log out and back in to use Docker without sudo."
EOF

echo "RTMP server deployed successfully!"
echo "RTMP URL: rtmp://$PUBLIC_IP/live"
echo "HLS URL: http://$PUBLIC_IP:8080/hls/drone_stream.m3u8"
echo ""
echo "Update your webapp-client/.env file with:"
echo "REACT_APP_HLS_STREAM_URL=http://$PUBLIC_IP:8080/hls/drone_stream.m3u8"

# Verify endpoints are accessible
echo "Verifying endpoints..."
echo "Checking HLS endpoint..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$PUBLIC_IP:8080/hls/drone_stream.m3u8)

if [ "$HTTP_STATUS" == "200" ]; then
    echo "✅ HLS endpoint is accessible (HTTP 200 OK)"
elif [ "$HTTP_STATUS" == "404" ]; then
    echo "⚠️ HLS endpoint returned 404 Not Found. This is normal if no stream is active yet."
else
    echo "⚠️ HLS endpoint returned HTTP status $HTTP_STATUS"
fi

# Check if RTMP port is open
echo "Checking if RTMP port is open..."
if nc -z -w5 $PUBLIC_IP 1935; then
    echo "✅ RTMP port 1935 is open and accepting connections"
else
    echo "❌ RTMP port 1935 is not accessible"
fi

# Check if HTTP port is open
echo "Checking if HTTP port is open..."
if nc -z -w5 $PUBLIC_IP 8080; then
    echo "✅ HTTP port 8080 is open and accepting connections"
else
    echo "❌ HTTP port 8080 is not accessible"
fi

# Check Docker container status
echo "Checking Docker container status on the server..."
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no $SSH_USER@$PUBLIC_IP << 'EOF'
    echo "Docker container status:"
    sudo docker ps | grep rtmp-server-container
    
    echo "Docker container logs (last 10 lines):"
    sudo docker logs rtmp-server-container --tail 10
EOF

echo "Verification complete!" 