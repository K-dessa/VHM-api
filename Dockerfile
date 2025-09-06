FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache \
    CRAWL4AI_DB_PATH=/app/.cache/crawl4ai

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd -m app || true \
 && mkdir -p /app/.cache /app/logs /app/data /app/data/crawl4ai \
 && chown -R app:app /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app/ /app/app/
COPY main.py /app/main.py

USER app
EXPOSE 8000
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}