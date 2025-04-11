import subprocess
import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .routers import recordings, users, stream, devices
from . import models
from .database import engine, SQLALCHEMY_DATABASE_URL
import boto3
import logging
import asyncio
from contextlib import asynccontextmanager
from alembic.config import Config
from alembic import command
from alembic.runtime import migration
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_db(max_retries=30, retry_interval=1):
    """Wait for the database to be ready with exponential backoff"""
    retries = 0
    while retries < max_retries:
        try:
            # Try to establish a connection and run a simple query
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                logger.info("Successfully connected to the database")
                return True
        except OperationalError as e:
            wait_time = retry_interval * (2 ** retries)  # Exponential backoff
            wait_time = min(wait_time, 10)  # Cap at 10 seconds
            logger.warning(f"Database not ready yet (attempt {retries + 1}/{max_retries}). Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            retries += 1
    
    raise Exception("Could not connect to the database after maximum retries")

def run_migrations_sync():
    """Run database migrations using Alembic"""
    try:
        logger.info("Running database migrations...")
        # Create Alembic configuration
        alembic_cfg = Config("alembic.ini")
        
        # Get the migration script directory
        script = ScriptDirectory.from_config(alembic_cfg)
        
        # Get the current head revision
        head_revision = script.get_current_head()
        
        # Run the migration
        with engine.begin() as connection:
            alembic_cfg.attributes['connection'] = connection
            command.upgrade(alembic_cfg, "head")
            
        logger.info(f"Migrations completed successfully. Head revision: {head_revision}")
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wait for database to be ready and run migrations in a separate thread
    try:
        await asyncio.get_event_loop().run_in_executor(None, wait_for_db)
        await asyncio.get_event_loop().run_in_executor(None, run_migrations_sync)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    yield

# Create FastAPI app
app = FastAPI(
    title="RTMP Recording API",
    description="API for managing RTMP recordings",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
# Configure CORS only for local development
if os.getenv("ENVIRONMENT", "local").lower() == "local":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # Local Frontend URL
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(recordings.router)
app.include_router(users.router)
app.include_router(stream.router)
app.include_router(devices.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the RTMP Recording API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/videos/{video_id}/stream")
def get_video_stream(video_id: str):
    # Check if the video exists in S3
    s3_client = boto3.client('s3')
    try:
        # First check for HLS playlist
        s3_client.head_object(
            Bucket=os.getenv("S3_BUCKET"),
            Key=f'videos/{video_id}/playlist.m3u8'
        )
        
        # If HLS playlist exists, return the HLS URL
        if os.getenv("CLOUDFRONT_DOMAIN"):
            cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
            stream_url = f"https://{cloudfront_domain}/videos/{video_id}/playlist.m3u8"
        else:
            # Fallback to direct S3 URL
            region = os.getenv("AWS_REGION", "us-east-1")
            bucket = os.getenv("S3_BUCKET")
            stream_url = f"https://{bucket}.s3.{region}.amazonaws.com/videos/{video_id}/playlist.m3u8"
        
        return {
            "stream_url": stream_url,
            "format": "hls",
            "mime_type": "application/vnd.apple.mpegurl"
        }
    except:
        # If HLS playlist doesn't exist, check for direct video file
        try:
            s3_client.head_object(
                Bucket=os.getenv("S3_BUCKET"),
                Key=f'videos/{video_id}.mp4'
            )
            
            # Return direct video URL
            if os.getenv("CLOUDFRONT_DOMAIN"):
                cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
                stream_url = f"https://{cloudfront_domain}/videos/{video_id}.mp4"
            else:
                region = os.getenv("AWS_REGION", "us-east-1")
                bucket = os.getenv("S3_BUCKET")
                stream_url = f"https://{bucket}.s3.{region}.amazonaws.com/videos/{video_id}.mp4"
            
            return {
                "stream_url": stream_url,
                "format": "mp4",
                "mime_type": "video/mp4"
            }
        except:
            raise HTTPException(status_code=404, detail="Video not found") 