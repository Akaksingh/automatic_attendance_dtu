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
RUN useradd -m appuser && mkdir -p /data/photos && chown -R appuser /data /app
# insightface caches model weights under the home dir; keep it writable + on a volume
RUN mkdir -p /root/.insightface && chown -R appuser /root/.insightface || true
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
