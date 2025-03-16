FROM python:3.9-slim

WORKDIR /app

# Install dependencies including ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app /app/app
COPY ./alembic /app/alembic
COPY ./alembic.ini /app/alembic.ini
COPY ./scripts /app/scripts

# Create the versions directory if it doesn't exist
RUN mkdir -p /app/alembic/versions && touch /app/alembic/versions/__init__.py

# Make the migration script executable
RUN chmod +x /app/scripts/run_migrations.py

# Expose port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 