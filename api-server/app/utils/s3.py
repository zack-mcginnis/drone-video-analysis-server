import boto3
import os
import logging
from dotenv import load_dotenv
from typing import Tuple, Optional, BinaryIO, Dict
import requests
from botocore.config import Config
from botocore.exceptions import ClientError
import json
from urllib.parse import urlparse
import io
import tempfile

load_dotenv()
logger = logging.getLogger(__name__)

def get_s3_client():
    """
    Get an S3 client configured for Lightsail bucket access.
    
    Returns:
        boto3.client: Configured S3 client
    """
    # Log AWS credentials status (without revealing the actual values)
    access_key_status = "set" if os.getenv("AWS_ACCESS_KEY_ID") else "not set"
    secret_key_status = "set" if os.getenv("AWS_SECRET_ACCESS_KEY") else "not set"
    logger.info(f"AWS credentials status - Access Key: {access_key_status}, Secret Key: {secret_key_status}")
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    bucket_name = os.getenv('AWS_BUCKET_NAME', 'bucket-d8mdwm')
    
    # Create a config specifically for Lightsail bucket access
    config = Config(
        region_name=region,
        retries={
            'max_attempts': 5,
            'mode': 'adaptive',
            'total_max_attempts': 10
        },
        s3={
            'addressing_style': 'path',  # Changed to path style for Lightsail compatibility
            'signature_version': 's3v4',
            'use_accelerate_endpoint': False
        },
        connect_timeout=10,
        read_timeout=30
    )
    
    # For Lightsail buckets, we need to use the regional endpoint
    endpoint_url = f'https://s3.{region}.amazonaws.com'
    
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        
        logger.info(f"Using S3 endpoint: {endpoint_url} with path-style addressing")
        
        return boto3.client(
            's3',
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=config
        )
    else:
        logger.error("AWS credentials not found in environment variables")
        raise ValueError("AWS credentials not found in environment variables")

def generate_presigned_url(s3_path: str, expiration: int = 3600) -> Optional[str]:
    """
    Generate a pre-signed URL for an S3 object.
    
    Args:
        s3_path: Path in format bucket-name/object-key
        expiration: URL expiration time in seconds (default 1 hour)
        
    Returns:
        Pre-signed URL or None if error
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        region = os.getenv('AWS_REGION', 'us-east-1')
        use_lightsail_bucket = os.getenv('USE_LIGHTSAIL_BUCKET', 'true').lower() == 'true'

        # Common parameters for pre-signed URL
        params = {
            'Bucket': bucket_name,
            'Key': object_key,
            'ResponseContentDisposition': f'attachment; filename="{os.path.basename(object_key)}"',
            'ResponseContentType': 'application/octet-stream'  # Ensure proper content type
        }
        
        try:
            # Generate the pre-signed URL
            url = s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration,
                HttpMethod='GET'
            )
            
            # Log the generated URL (without query parameters for security)
            base_url = url.split('?')[0]
            logger.info(f"Generated pre-signed URL base: {base_url}")
            
            # Verify the URL format
            parsed_url = urlparse(url)
            logger.info(f"URL scheme: {parsed_url.scheme}")
            logger.info(f"URL netloc: {parsed_url.netloc}")
            logger.info(f"URL path: {parsed_url.path}")
            
            return url
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            logger.error(f"Failed to generate pre-signed URL: {error_code} - {error_msg}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating pre-signed URL: {str(e)}")
        return None

def download_from_s3(s3_path: str, local_path: str) -> bool:
    """
    Download a file from Lightsail bucket using bucket-specific access.
    
    Args:
        s3_path: Path in format bucket-name/object-key
        local_path: Local path to save the file
        
    Returns:
        True if download was successful, False otherwise
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        
        try:
            # Create a temporary file to store the download
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                logger.info(f"Downloading from Lightsail bucket: {bucket_name}/{object_key}")
                
                # Use get_object instead of download_fileobj for better error handling
                response = s3_client.get_object(
                    Bucket=bucket_name,
                    Key=object_key
                )
                
                # Stream the content to avoid memory issues with large files
                for chunk in response['Body'].iter_chunks(chunk_size=8192):
                    temp_file.write(chunk)
                
                temp_file_path = temp_file.name
            
            # Ensure the target directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Move the temporary file to the target location
            os.replace(temp_file_path, local_path)
            logger.info(f"Successfully downloaded {s3_path} to {local_path}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            logger.error(f"S3 client error: {error_code} - {error_msg}")
            
            if error_code == 'AccessDenied':
                logger.error("Access denied. Please verify your Lightsail bucket access keys are correct")
                logger.error("You may need to create new access keys in the Lightsail console")
            return False
            
    except Exception as e:
        logger.error(f"Error downloading from Lightsail bucket: {str(e)}")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except:
                pass
        return False

def get_object_from_s3(s3_path: str) -> Optional[BinaryIO]:
    """
    Get an object from S3 bucket using direct access.
    
    Args:
        s3_path: Path in format bucket-name/object-key
        
    Returns:
        Object body or None if error
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        
        try:
            # Get the object directly using the S3 client
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=object_key
            )
            return response['Body']
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            logger.error(f"S3 client error: {error_code} - {error_msg}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting object from S3: {str(e)}")
        return None

def parse_s3_path(s3_path: str) -> Tuple[str, str]:
    """
    Parse an S3 path into bucket name and object key.
    
    Args:
        s3_path: Path in format bucket-name/object-key or s3://bucket-name/object-key
        
    Returns:
        Tuple of (bucket_name, object_key)
    """
    if s3_path.startswith("s3://"):
        s3_path = s3_path[5:]
    
    parts = s3_path.split("/", 1)
    if len(parts) < 2:
        return parts[0], ""
    return parts[0], parts[1]

def upload_to_s3(local_path: str, s3_path: str) -> bool:
    """
    Upload a file to S3 bucket.
    
    Args:
        local_path: Local path of the file
        s3_path: Path in format bucket-name/object-key
        
    Returns:
        True if upload was successful, False otherwise
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        
        # Upload directly using the S3 client
        logger.info(f"Uploading to S3: {bucket_name}/{object_key}")
        s3_client.upload_file(
            Filename=local_path,
            Bucket=bucket_name,
            Key=object_key
        )
        
        return True
    except Exception as e:
        logger.error(f"Error uploading to S3 bucket: {str(e)}")
        return False