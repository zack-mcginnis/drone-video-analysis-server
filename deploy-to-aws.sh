#!/bin/bash
# Script to deploy RTMP server to an existing AWS Lightsail instance

# Configuration - MODIFY THESE VALUES
PUBLIC_IP="YOUR_STATIC_IP_ADDRESS"  # Your static IP
SSH_KEY_PATH="~/.ssh/id_rsa"  # Path to your SSH key
SSH_USER="ec2-user"  # Default user for Amazon Linux 2/2023
DOMAIN_NAME=""  # Your custom domain

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
    
    # Build Docker image (using sudo since we haven't re-logged in yet)
    sudo docker build -t rtmp-server .
    
    # Run container
    sudo docker run -d --restart always \
        -p 1935:1935 \
        -p 80:80 \
        -p 8080:8080 \
        --name rtmp-server-container rtmp-server
    
    echo "Docker container started. You may need to log out and back in to use Docker without sudo."
EOF

echo "RTMP server deployed successfully!"
echo "RTMP URL: rtmp://$PUBLIC_IP/live"

# Display URLs based on whether a domain name is provided
if [ -n "$DOMAIN_NAME" ]; then
    echo "Custom Domain: $DOMAIN_NAME"
    echo "HLS URL (HTTP): http://$DOMAIN_NAME/hls/drone_stream.m3u8"
    echo "HLS URL (HTTPS): https://$DOMAIN_NAME/hls/drone_stream.m3u8"
    echo ""
    echo "Update your webapp-client/.env file with one of these URLs:"
    echo "For HTTP: REACT_APP_HLS_STREAM_URL=http://$DOMAIN_NAME/hls/drone_stream.m3u8"
    echo "For HTTPS: REACT_APP_HLS_STREAM_URL=https://$DOMAIN_NAME/hls/drone_stream.m3u8"
else
    echo "HLS URL (HTTP): http://$PUBLIC_IP:8080/hls/drone_stream.m3u8"
    echo ""
    echo "Update your webapp-client/.env file with this URL:"
    echo "REACT_APP_HLS_STREAM_URL=http://$PUBLIC_IP:8080/hls/drone_stream.m3u8"
fi

# Verify endpoints are accessible
echo "Verifying endpoints..."

# Check if direct IP HTTP endpoint is accessible
echo "Checking direct IP HTTP endpoint..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$PUBLIC_IP:8080/hls/drone_stream.m3u8)

if [ "$HTTP_STATUS" == "200" ]; then
    echo "✅ Direct IP HTTP endpoint is accessible (HTTP 200 OK)"
elif [ "$HTTP_STATUS" == "404" ]; then
    echo "⚠️ Direct IP HTTP endpoint returned 404 Not Found. This is normal if no stream is active yet."
else
    echo "⚠️ Direct IP HTTP endpoint returned HTTP status $HTTP_STATUS"
fi

# If a domain name is provided, check those endpoints too
if [ -n "$DOMAIN_NAME" ]; then
    # Check if domain HTTP endpoint is accessible
    echo "Checking domain HTTP endpoint..."
    DOMAIN_HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$DOMAIN_NAME/hls/drone_stream.m3u8)

    if [ "$DOMAIN_HTTP_STATUS" == "200" ]; then
        echo "✅ Domain HTTP endpoint is accessible (HTTP 200 OK)"
    elif [ "$DOMAIN_HTTP_STATUS" == "404" ]; then
        echo "⚠️ Domain HTTP endpoint returned 404 Not Found. This is normal if no stream is active yet."
    else
        echo "⚠️ Domain HTTP endpoint returned HTTP status $DOMAIN_HTTP_STATUS"
    fi

    # Check if domain HTTPS endpoint is accessible
    echo "Checking domain HTTPS endpoint..."
    DOMAIN_HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN_NAME/hls/drone_stream.m3u8)

    if [ "$DOMAIN_HTTPS_STATUS" == "200" ]; then
        echo "✅ Domain HTTPS endpoint is accessible (HTTP 200 OK)"
    elif [ "$DOMAIN_HTTPS_STATUS" == "404" ]; then
        echo "⚠️ Domain HTTPS endpoint returned 404 Not Found. This is normal if no stream is active yet."
    else
        echo "⚠️ Domain HTTPS endpoint returned HTTP status $DOMAIN_HTTPS_STATUS"
    fi

fi

# Check if ports are open on the direct IP
echo "Checking if ports are open on the server..."
if command -v nc &> /dev/null; then
    # Check RTMP port
    if nc -z -w5 $PUBLIC_IP 1935; then
        echo "✅ RTMP port 1935 is open and accepting connections"
    else
        echo "❌ RTMP port 1935 is not accessible"
    fi
    
    # Check HTTP port
    if nc -z -w5 $PUBLIC_IP 80; then
        echo "✅ HTTP port 80 is open and accepting connections"
    else
        echo "❌ HTTP port 80 is not accessible"
    fi
    
    # Check legacy HTTP port
    if nc -z -w5 $PUBLIC_IP 8080; then
        echo "✅ Legacy HTTP port 8080 is open and accepting connections"
    else
        echo "❌ Legacy HTTP port 8080 is not accessible"
    fi
else
    echo "⚠️ netcat (nc) not found, skipping port checks"
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
echo ""

if [ -n "$DOMAIN_NAME" ]; then
    echo "Your RTMP server is now deployed and accessible via your custom domain."
    echo "The AWS Load Balancer is handling SSL/TLS termination for secure HTTPS connections."
else
    echo "Your RTMP server is now deployed and accessible via the direct IP address."
    echo "Consider setting up a custom domain with an AWS Load Balancer for HTTPS support."
fi 