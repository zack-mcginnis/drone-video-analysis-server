import subprocess
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .routers import recordings
from . import models
from .database import engine
import boto3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Run migrations if in AWS environment
if os.getenv("ENVIRONMENT", "local").lower() == "aws":
    try:
        logger.info("Running database migrations...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        logger.info("Migrations completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running migrations: {e}")
        # Continue anyway, as the app might be able to function with existing tables

# Create database tables (fallback if migrations fail)
try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.error(f"Error creating database tables: {e}")

# Create FastAPI app
app = FastAPI(
    title="RTMP Recording API",
    description="API for managing RTMP recordings",
    version="1.0.0",
)

# Configure CORS
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://master.d30ze8pk52gyx8.amplifyapp.com",
    "*",  # Allow all origins for video streaming
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(recordings.router)

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
        s3_client.head_object(
            Bucket=os.getenv("S3_BUCKET"),
            Key=f'videos/{video_id}/playlist.m3u8'
        )
    except:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Generate CloudFront URL if available, otherwise use S3 URL
    if os.getenv("CLOUDFRONT_DOMAIN"):
        cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
        stream_url = f"https://{cloudfront_domain}/videos/{video_id}/playlist.m3u8"
    else:
        # Fallback to direct S3 URL
        region = os.getenv("AWS_REGION", "us-east-1")
        bucket = os.getenv("S3_BUCKET")
        stream_url = f"https://{bucket}.s3.{region}.amazonaws.com/videos/{video_id}/playlist.m3u8"
    
    return {"stream_url": stream_url} 