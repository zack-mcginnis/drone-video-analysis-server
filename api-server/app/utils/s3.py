import boto3
import os
import logging
from typing import Optional, Tuple, BinaryIO

logger = logging.getLogger(__name__)

def get_s3_client(region: str = None):
    """
    Get an S3 client for Lightsail bucket.
    
    Args:
        region: AWS region
        
    Returns:
        S3 client
    """
    region = region or os.getenv("AWS_REGION", "us-west-2")
    
    # Check if we're using a Lightsail bucket
    if os.getenv("USE_LIGHTSAIL_BUCKET", "false").lower() == "true":
        # For Lightsail buckets, we need to use a different endpoint
        return boto3.client(
            's3',
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
    else:
        # Standard S3 bucket
        return boto3.client('s3', region_name=region)

def parse_s3_path(s3_path: str) -> Tuple[str, str]:
    """
    Parse an S3 path into bucket name and object key.
    
    Args:
        s3_path: S3 path (s3://bucket-name/object-key)
        
    Returns:
        Tuple of (bucket_name, object_key)
    """
    if s3_path.startswith("s3://"):
        s3_path = s3_path[5:]  # Remove "s3://" prefix
    
    parts = s3_path.split("/", 1)
    if len(parts) < 2:
        return parts[0], ""
    return parts[0], parts[1]

def download_from_s3(s3_path: str, local_path: str) -> bool:
    """
    Download a file from S3.
    
    Args:
        s3_path: S3 path (s3://bucket-name/object-key)
        local_path: Local path to save the file
        
    Returns:
        True if download was successful, False otherwise
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3_client.download_file(bucket_name, object_key, local_path)
        
        return True
    except Exception as e:
        logger.error(f"Error downloading from S3: {str(e)}")
        return False

def upload_to_s3(local_path: str, s3_path: str) -> bool:
    """
    Upload a file to S3.
    
    Args:
        local_path: Local path of the file
        s3_path: S3 path (s3://bucket-name/object-key)
        
    Returns:
        True if upload was successful, False otherwise
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        
        s3_client.upload_file(local_path, bucket_name, object_key)
        
        return True
    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        return False

def get_object_from_s3(s3_path: str) -> Optional[BinaryIO]:
    """
    Get an object from S3.
    
    Args:
        s3_path: S3 path (s3://bucket-name/object-key)
        
    Returns:
        Object body or None if error
    """
    try:
        bucket_name, object_key = parse_s3_path(s3_path)
        s3_client = get_s3_client()
        
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        return response['Body']
    except Exception as e:
        logger.error(f"Error getting object from S3: {str(e)}")
        return None 