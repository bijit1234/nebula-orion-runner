FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create uploads and data directories
RUN mkdir -p uploads data

# Expose default port
EXPOSE 8000

# Use shell form so ${PORT} env variable is expanded at runtime.
# Render sets PORT dynamically; locally it defaults to 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}