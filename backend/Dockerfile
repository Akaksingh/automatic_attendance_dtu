FROM python:3.11-slim

# System deps: OpenCV runtime libs + build tools for insightface's native bits
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 libgomp1 \
        build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build context is the repo root (see docker-compose.yml), so paths are prefixed.
COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY frontend ./frontend

# Non-root runtime user
RUN useradd -m appuser \
    && mkdir -p /data/photos /data/model_cache \
    && chown -R appuser /data /app
USER appuser

# Point InsightFace at the writable volume (not /root which appuser can't access)
ENV INSIGHTFACE_HOME=/data/model_cache \
    HOME=/home/appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
