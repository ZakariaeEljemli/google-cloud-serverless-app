# Multi-stage lightweight Docker image for Cloud Run
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install dependencies first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/

# Expose port (Cloud Run sets PORT env var)
EXPOSE 8080

# Run with Gunicorn WSGI server: 1 worker process, 8 threads
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app.main:app
