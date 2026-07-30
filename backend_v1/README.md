# Backend v1

Standalone Python 3.12 FastAPI foundation for the enhanced attendance system.
It deliberately does not alter the existing `backend/` proof of concept.

## Local setup (PyCharm)

Create and select a Python 3.12 virtual environment in PyCharm, then install:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set the connection URLs for your PostgreSQL
and Redis instances. Start the API with:

```bash
uvicorn app.main:app --reload
```

To run only its development dependencies in Docker (while keeping Python in
PyCharm), from the repository root run:

```bash
docker compose -f docker-compose.development.yml up -d
```

This exposes PostgreSQL on `localhost:5432` and Redis on `localhost:6379`,
which match the URLs in `.env.example`. Use `DEV_POSTGRES_PORT` or
`DEV_REDIS_PORT` to change either host port when necessary.

Before the frontend has been built, `GET /` returns a hello-world response.
API routes use the `/api` prefix: `GET /api/hello` is the smoke test and
`GET /api/health/dependencies` verifies
that PostgreSQL and Redis are reachable. The Celery application and an example
task are ready to be run with:

```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```

Database schema changes are managed with Alembic. Apply migrations locally with:

```bash
alembic upgrade head
```

The production image applies `alembic upgrade head` before starting FastAPI.

Admin student provisioning supports both a single multipart request and bulk
Excel imports. The Excel header must include `email`, `full_name`, and
`roll_no`; optional columns are `password` and `photo`. The `photo` value is a
filename inside the optional `images_zip` upload. Images are
optional, and any supplied image is queued for Celery face verification. If a
student has no approved photos yet, the first verified single-face image is
accepted without a similarity comparison. Later images must match at least one
previous approved embedding.

Run a worker alongside the API to process queued photos:

```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```

Relevant endpoints:

```text
POST /api/admin/students             # one student, optional file field
POST /api/admin/students/bulk        # .xlsx/.xlsm plus optional images_zip
GET  /api/admin/photo-jobs/{job_id}  # processing status
```

The included Dockerfile uses Python 3.12 and builds the React PWA into the API
image. After a production image starts, FastAPI serves the built frontend at
`/` and reserves `/api/*` for its API routes.
