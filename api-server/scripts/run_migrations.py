#!/usr/bin/env python3
"""
Script to run database migrations for the RTMP Recording API.
"""

import os
import sys
from dotenv import load_dotenv

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
    from app.models import Base
    from app.database import engine
    
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully using SQLAlchemy.")
    sys.exit(0)
except Exception as e:
    print(f"Error creating tables with SQLAlchemy: {e}")
    sys.exit(1) 