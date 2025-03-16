from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Determine environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")

# Get database connection details based on environment
if ENVIRONMENT.lower() == "aws":
    # Use AWS PostgreSQL configuration
    POSTGRES_USER = os.getenv("AWS_POSTGRES_USER", "dbmasteruser")
    POSTGRES_PASSWORD = os.getenv("AWS_POSTGRES_PASSWORD", "")
    POSTGRES_HOST = os.getenv("AWS_POSTGRES_HOST", "")
    POSTGRES_PORT = os.getenv("AWS_POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("AWS_POSTGRES_DB", "recordings")
else:
    # Use local PostgreSQL configuration
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "recordings")

# Create SQLAlchemy database URL
SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create SQLAlchemy engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

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