# AWS Deployment Guide for RTMP Server

This guide explains how to deploy the RTMP server to AWS Lightsail.

## Prerequisites

1. AWS account
2. AWS CLI installed and configured
3. SSH key pair

## Deployment to a New Instance

1. Make sure you have the AWS CLI installed and configured:
   ```
   aws configure
   ```

2. Run the deployment script:
   ```
   ./deploy-to-aws.sh
   ```

3. The script will:
   - Create a new AWS Lightsail instance
   - Install Docker
   - Copy the necessary files
   - Build and run the Docker container
   - Output the RTMP and HLS URLs

4. Update your webapp-client/.env file with the new HLS URL.

## Deployment to an Existing Instance

If you already have a Lightsail instance with a static IP:

1. Edit the `deploy-to-aws.sh` script to set your static IP address and SSH key path:
   ```bash
   PUBLIC_IP="YOUR_STATIC_IP_ADDRESS"  # Replace with your static IP
   SSH_KEY_PATH="~/.ssh/id_rsa"        # Path to your SSH key
   ```

2. Run the deployment script:
   ```
   ./deploy-to-aws.sh
   ```

## Manual Deployment

If you prefer to deploy manually:

1. Create an AWS Lightsail instance with Amazon Linux 2.
2. Connect to the instance via SSH.
3. Install Docker:
   ```
   sudo yum update -y
   sudo amazon-linux-extras install docker -y
   sudo service docker start
   sudo systemctl enable docker
   sudo usermod -a -G docker ec2-user
   ```
4. Copy the Dockerfile, nginx.conf, and start.sh to the instance.
5. Build and run the Docker container:
   ```
   docker build -t rtmp-server .
   docker run -d --restart always -p 1935:1935 -p 8080:8080 --name rtmp-server-container rtmp-server
   ```

## Costs

- AWS Lightsail nano instance ($3.50/month)
- Data transfer: First 1TB/month is included in the instance price
- Static IP: $0.005/hour (~$3.60/month) when not attached to a running instance

## Security Considerations

For production use:
1. Update the nginx.conf file to restrict who can publish to your RTMP server
2. Set up SSL for secure connections
3. Consider setting up a CDN for large audiences 