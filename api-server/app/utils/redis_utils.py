import os
import time
import socket
import logging
import redis
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

def get_redis_connection_params():
    """
    Get Redis connection parameters from environment variables with defaults
    """
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    redis_socket_timeout = int(os.getenv('REDIS_SOCKET_TIMEOUT', '30'))
    redis_socket_connect_timeout = int(os.getenv('REDIS_SOCKET_CONNECT_TIMEOUT', '30'))
    redis_retry_on_timeout = os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true'
    redis_max_retries = int(os.getenv('REDIS_MAX_RETRIES', '10'))
    
    # Parse host and port from Redis URL
    redis_host = 'redis'  # Default host
    redis_port = 6379     # Default port
    
    if redis_url.startswith('redis://'):
        parts = redis_url.replace('redis://', '').split(':')
        if len(parts) >= 1 and parts[0]:
            redis_host = parts[0]
        if len(parts) >= 2:
            try:
                port_parts = parts[1].split('/')
                redis_port = int(port_parts[0])
            except (ValueError, IndexError):
                pass
    
    # Try to resolve Redis hostname to IP
    try:
        redis_ip = socket.gethostbyname(redis_host)
        logger.info(f"Resolved Redis hostname {redis_host} to IP {redis_ip}")
        
        # Use IP-based Redis URL
        db_part = redis_url.split('/')[-1] if '/' in redis_url else '0'
        redis_url = f"redis://{redis_ip}:{redis_port}/{db_part}"
        logger.info(f"Using IP-based Redis URL: {redis_url}")
    except socket.gaierror:
        logger.warning(f"Could not resolve Redis hostname {redis_host}, using original URL")
    
    return {
        'url': redis_url,
        'host': redis_host,
        'port': redis_port,
        'socket_timeout': redis_socket_timeout,
        'socket_connect_timeout': redis_socket_connect_timeout,
        'retry_on_timeout': redis_retry_on_timeout,
        'max_retries': redis_max_retries
    }

def check_redis_connection(host='redis', port=6379, retry_attempts=5, retry_delay=2) -> bool:
    """
    Check if Redis is accessible using socket connection
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    logger.info(f"Testing Redis connection to {host}:{port}...")
    
    for attempt in range(retry_attempts):
        try:
            # Try direct socket connection first
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            s.close()
            logger.info(f"Successfully connected to Redis at {host}:{port}")
            return True
        except (socket.timeout, socket.error, ConnectionRefusedError) as e:
            logger.warning(f"Redis connection attempt {attempt+1}/{retry_attempts} failed: {str(e)}")
            if attempt < retry_attempts - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
    
    logger.error(f"Could not connect to Redis after {retry_attempts} attempts")
    return False

def get_redis_client() -> Optional[redis.Redis]:
    """
    Get a Redis client with connection retry logic
    
    Returns:
        Optional[redis.Redis]: Redis client or None if connection fails
    """
    params = get_redis_connection_params()
    
    try:
        # Check connection using socket first
        if not check_redis_connection(params['host'], params['port']):
            # Try with resolved IP if hostname doesn't work
            try:
                ip = socket.gethostbyname(params['host'])
                if ip != params['host']:  # Only try if IP is different from host
                    logger.info(f"Trying Redis connection with resolved IP {ip}")
                    if check_redis_connection(ip, params['port']):
                        # Use IP address instead of hostname
                        params['host'] = ip
                        # Update URL with IP
                        db_part = params['url'].split('/')[-1] if '/' in params['url'] else '0'
                        params['url'] = f"redis://{ip}:{params['port']}/{db_part}"
            except socket.gaierror:
                logger.warning(f"Could not resolve Redis hostname {params['host']}")
        
        # Create Redis client with optimized connection parameters
        client = redis.Redis.from_url(
            params['url'],
            socket_timeout=params['socket_timeout'],
            socket_connect_timeout=params['socket_connect_timeout'],
            retry_on_timeout=params['retry_on_timeout'],
            decode_responses=True
        )
        
        # Test connection
        client.ping()
        logger.info("Redis client connected successfully")
        return client
    except (redis.ConnectionError, redis.exceptions.RedisError) as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        return None 