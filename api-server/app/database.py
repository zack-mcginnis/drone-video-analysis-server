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

# Create SQLAlchemy engine with connection debugging and TCP-specific settings
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=True,  # Enable SQL logging
    pool_pre_ping=True,  # Enable connection health checks
    connect_args={
        "application_name": "api-server",  # Helps identify connections in pg_stat_activity
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 