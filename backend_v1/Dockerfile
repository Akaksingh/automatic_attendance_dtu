FROM node:23-alpine AS frontend-build

WORKDIR /frontend
COPY frontend_v1/package.json frontend_v1/package-lock.json ./
RUN npm ci
COPY frontend_v1 ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend_v1/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend_v1/app ./app
COPY backend_v1/alembic.ini ./alembic.ini
COPY backend_v1/alembic ./alembic
COPY --from=frontend-build /frontend/dist /app/frontend

# Mount persistent storage at /app/data in deployment environments.
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
