from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

load_dotenv()

# Determine environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")

# Get database connection details based on environment
if ENVIRONMENT.lower() == "aws":
    # Use AWS PostgreSQL configuration
    POSTGRES_USER = os.getenv("POSTGRES_USER", "dbmasteruser")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "recordings")
    
    # Escape special characters in password
    escaped_password = quote_plus(POSTGRES_PASSWORD)
    
    # Log connection details (without sensitive info)
    logger.info(f"Connecting to AWS PostgreSQL at {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    
    # Use explicit TCP connection with escaped password
    SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{escaped_password}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode=require"
else:
    # Use local PostgreSQL configuration
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "recordings")
    
    # Use explicit TCP connection for local development
    SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Connection pool size configuration
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))

# Create SQLAlchemy engine with optimized connection pooling and TCP-specific settings
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Only enable SQL logging when explicitly set
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=POOL_SIZE,  # Number of connections to keep open
    max_overflow=MAX_OVERFLOW,  # Allow creating more connections when under load
    pool_recycle=POOL_RECYCLE,  # Recycle connections after 1 hour
    pool_timeout=POOL_TIMEOUT,  # Time to wait for a connection from pool
    connect_args={
        "application_name": "api-server",  # Helps identify connections in pg_stat_activity
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "options": "-c statement_timeout=30000"  # 30s statement timeout to prevent long-running queries
    }
)

# Create SessionLocal class with optimized settings
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False  # Improve performance by not expiring objects after commit
)

# Create Base class
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 