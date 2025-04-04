# AWS Deployment Guide for RTMP Server with Load Balancer

This guide explains how to deploy the RTMP server to AWS Lightsail with HTTPS support through an AWS Load Balancer.

## Prerequisites

1. AWS account
2. AWS CLI installed and configured
3. SSH key pair
4. AWS Load Balancer configured with SSL/TLS certificate

## Deployment Configuration

1. Create a `.env` file with your deployment configuration:
   ```
   # AWS Lightsail Deployment Configuration
   PUBLIC_IP=YOUR_STATIC_IP_ADDRESS
   SSH_KEY_PATH=PATH_TO_YOUR_SSH_KEY
   SSH_USER=ec2-user
   DOMAIN_NAME=YOUR_DOMAIN_NAME
   ```

   You can copy the `.env.example` file as a starting point:
   ```
   cp .env.example .env
   ```

2. Edit the `.env` file with your specific configuration.

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

1. Update your `.env` file with your static IP address and SSH key path.
2. Run the deployment script:
   ```
   ./deploy-to-aws.sh
   ```

## HTTPS Support with AWS Load Balancer

Since you're using an AWS Load Balancer with an SSL/TLS certificate:

1. The Load Balancer handles SSL termination, so the RTMP server doesn't need to manage certificates.
2. Your stream is accessible via both HTTP and HTTPS:
   - HTTP: `http://YOUR_DOMAIN/hls/drone_stream.m3u8`
   - HTTPS: `https://YOUR_DOMAIN/hls/drone_stream.m3u8`
3. The HTTPS connection is secure with a valid certificate provided by the Load Balancer.

## CORS Configuration

The NGINX configuration includes CORS headers to allow access from specific origins. If you need to add more allowed origins, edit the `nginx.conf` file:

```nginx
# Map to handle CORS for multiple origins
# NOTE: add your custom origin here
map $http_origin $cors_origin {
    default "";
    "http://localhost:3000" $http_origin;
    "https://your-app-domain.com" $http_origin;
}
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
   docker run -d --restart always -p 1935:1935 -p 80:80 -p 8080:8080 --name rtmp-server-container rtmp-server
   ```

## Costs

- AWS Lightsail nano instance ($3.50/month)
- Data transfer: First 1TB/month is included in the instance price
- Static IP: $0.005/hour (~$3.60/month) when not attached to a running instance
- AWS Load Balancer: Additional costs apply

## Security Considerations

1. The AWS Load Balancer provides a secure HTTPS connection with a valid certificate
2. Consider restricting who can publish to your RTMP server
3. Consider setting up a CDN for large audiences 

## Recording Configuration

The RTMP server is configured to record all streams. When a stream ends, the recording is saved and processed:

1. **Local Development**: Recordings are saved to the `/recordings` directory inside the Docker container. You can access them at `http://localhost:8080/recordings/`.

2. **AWS Deployment**: Recordings are uploaded to an AWS S3 bucket. To configure this:

   a. Create an S3 bucket for your recordings
   b. Update your `.env` file with the S3 bucket information:
      ```
      AWS_REGION=us-west-2
      S3_BUCKET=your-bucket-name
      AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
      AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
      ```
   c. Make sure the AWS credentials have permission to write to the S3 bucket

3. **IAM Policy**: Create an IAM user with the following policy:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:PutObject",
                   "s3:GetObject",
                   "s3:ListBucket"
               ],
               "Resource": [
                   "arn:aws:s3:::your-bucket-name",
                   "arn:aws:s3:::your-bucket-name/*"
               ]
           }
       ]
   }
   ```

4. **Accessing Recordings**: Recordings are organized in the S3 bucket by stream name and timestamp:
   ```
   s3://your-bucket-name/recordings/stream_name/YYYY/MM/DD/HH-MM-SS/recording.flv
   ``` 