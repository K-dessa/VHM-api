FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache \
    CRAWL4AI_DB_PATH=/app/.cache/crawl4ai \
    PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

# Install system dependencies including Rust for some packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gcc g++ build-essential \
    pkg-config libssl-dev rustc cargo \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd -m app || true \
 && mkdir -p /app/.cache /app/logs /app/data /app/data/crawl4ai \
 && chown -R app:app /app

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

# Install Playwright and download Chromium browser and required OS deps
# Do this at build time so production containers have browsers available.
RUN pip install --no-cache-dir playwright \
 && playwright install --with-deps chromium \
 && mkdir -p /app/.cache/ms-playwright \
 && chmod -R a+rx /app/.cache/ms-playwright || true

# Copy application code
COPY app/ /app/app/

# Set ownership
RUN chown -R app:app /app

USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Railway uses PORT environment variable
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
