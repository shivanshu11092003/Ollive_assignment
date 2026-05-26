FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for python psycopg2 compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for Docker layer caching
COPY services/ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy SDK library and Ingestion service files
COPY sdk /app/sdk
COPY services/ingestion /app/services/ingestion

# Configure PYTHONPATH so cross-module imports function correctly
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "services.ingestion.main:app", "--host", "0.0.0.0", "--port", "8001"]
