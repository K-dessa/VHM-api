FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache \
    CRAWL4AI_DB_PATH=/app/.cache/crawl4ai

# Install system dependencies including Rust for some packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gcc g++ build-essential \
    pkg-config libssl-dev rustc cargo \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd -m app || true \
 && mkdir -p /app/.cache /app/logs /app/data /app/data/crawl4ai \
 && chown -R app:app /app

# Install Python dependencies (excluding problematic ones first)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir fastapi uvicorn pydantic httpx beautifulsoup4 lxml openai python-decouple structlog tenacity psutil \
 && pip install --no-cache-dir pydantic-settings \
 && echo "Installed basic requirements, now trying crawl4ai..." \
 && (pip install --no-cache-dir crawl4ai==0.3.74 || echo "Crawl4ai failed, continuing...") \
 && pip install --no-cache-dir requests

COPY app/ /app/app/
COPY test_production_endpoints.py /app/test_production_endpoints.py

USER app
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}