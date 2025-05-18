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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import sys

# Configure logging to output to stdout with a more straightforward configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Force reconfiguration of the root logger
)

# Create logger for this module
logger = logging.getLogger("api")
# Set the log level for this logger
logger.setLevel(logging.INFO)
# Ensure all handlers propagate logs to stdout
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
        logger.addHandler(handler)

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

# Add request logging middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging request/response details and error messages"""
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log directly to stdout in addition to logger
        print(f"API REQUEST: {request.method} {request.url.path}")
        
        # Get the real client IP from X-Forwarded-For if available
        client_host = request.headers.get("x-forwarded-for", request.client.host)
        # Get query parameters if any
        query_params = dict(request.query_params)
        query_str = f" - Query: {query_params}" if query_params else ""
        
        # Log request with more details
        log_message = (
            f">>> Request: {request.method} {request.url.path}{query_str} "
            f"- Client: {client_host}"
        )
        logger.info(log_message)
        print(log_message)  # Direct stdout logging as backup
        
        try:
            # Process request and get response
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Check if it's an error response (4xx or 5xx status code)
            if response.status_code >= 400:
                # For error responses, try to capture the response body
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk
                
                # Try to decode the response body
                try:
                    body_text = response_body.decode()
                except UnicodeDecodeError:
                    body_text = "[Binary response body]"
                
                # Log error response with body content
                log_response = (
                    f"<<< Error Response: {request.method} {request.url.path} "
                    f"- Status: {response.status_code} "
                    f"- Time: {process_time:.3f}s "
                    f"- Body: {body_text}"
                )
                logger.error(log_response)
                print(log_response)  # Direct stdout logging as backup
                
                # Create a new response with the same body
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            else:
                # Log successful response
                log_response = (
                    f"<<< Response: {request.method} {request.url.path} "
                    f"- Status: {response.status_code} "
                    f"- Time: {process_time:.3f}s"
                )
                logger.info(log_response)
                print(log_response)  # Direct stdout logging as backup
            
            return response
            
        except Exception as e:
            # Log error response
            process_time = time.time() - start_time
            log_error = (
                f"!!! Error: {request.method} {request.url.path} "
                f"- Error: {str(e)} "
                f"- Type: {type(e).__name__} "
                f"- Time: {process_time:.3f}s"
            )
            logger.error(log_error)
            print(log_error)  # Direct stdout logging as backup
            
            # Log exception details for debugging
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Traceback: {error_traceback}")
            print(f"Traceback: {error_traceback}")  # Direct stdout logging as backup
            
            raise

# Create FastAPI app
app = FastAPI(
    title="RTMP Recording API",
    description="API for managing RTMP recordings",
    version="1.0.0",
    lifespan=lifespan,
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

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