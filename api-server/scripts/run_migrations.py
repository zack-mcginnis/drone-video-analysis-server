#!/usr/bin/env python3
"""
Script to run database migrations for the RTMP Recording API.
"""

import os
import sys
from dotenv import load_dotenv

# Add the parent directory to sys.path to ensure app module can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Set environment to AWS for migrations
os.environ["ENVIRONMENT"] = "aws"

# Ensure the versions directory exists
versions_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic", "versions")
if not os.path.exists(versions_dir):
    print(f"Creating Alembic versions directory: {versions_dir}")
    os.makedirs(versions_dir)
    # Create an empty __init__.py file in the versions directory
    with open(os.path.join(versions_dir, "__init__.py"), "w") as f:
        pass

# Add after imports
def test_db_connection():
    """Test the database connection before attempting migrations."""
    from sqlalchemy import text
    from app.database import engine, SQLALCHEMY_DATABASE_URL
    
    print(f"Testing connection to database...")
    print(f"Database URL (without credentials): {SQLALCHEMY_DATABASE_URL.split('@')[1]}")
    
    try:
        # Try to connect and execute a simple query
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"Database connection successful!")
            print(f"PostgreSQL version: {version}")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        print("Environment variables:")
        print(f"ENVIRONMENT: {os.getenv('ENVIRONMENT')}")
        print(f"POSTGRES_USER: {os.getenv('POSTGRES_USER')}")
        print(f"POSTGRES_HOST: {os.getenv('POSTGRES_HOST')}")
        print(f"POSTGRES_PORT: {os.getenv('POSTGRES_PORT')}")
        print(f"POSTGRES_DB: {os.getenv('POSTGRES_DB')}")
        return False

# Add before running migrations
if not test_db_connection():
    print("Cannot proceed with migrations due to database connection failure")
    sys.exit(1)

# Try to run Alembic migrations first
try:
    print("Attempting to run Alembic migrations...")
    import subprocess
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        check=False,  # Don't raise an exception on non-zero exit
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(result.stdout)
        print("Alembic migrations completed successfully.")
        sys.exit(0)
    else:
        print(f"Alembic migrations failed: {result.stderr}")
        print("Falling back to SQLAlchemy table creation...")
except Exception as e:
    print(f"Error running Alembic: {e}")
    print("Falling back to SQLAlchemy table creation...")

# Fall back to SQLAlchemy table creation
try:
    print("Creating tables using SQLAlchemy...")
    # Import here to ensure the app module can be found
    from app.models import Base
    from app.database import engine
    
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully using SQLAlchemy.")
    sys.exit(0)
except Exception as e:
    print(f"Error creating tables with SQLAlchemy: {e}")
    sys.exit(1) 