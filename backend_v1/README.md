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

## Agent implementation guide

### System boundaries

`backend_v1/app/main.py` creates the FastAPI application and registers the
routers. Route modules contain HTTP validation and authorization; SQLAlchemy
models live in `app/models.py`; Pydantic API contracts live in `app/schemas.py`.
Long-running face work must run through Celery tasks in `app/tasks.py`, never in
an HTTP request. The worker uses the same `DATABASE_URL`, `REDIS_URL`, face
model settings, and filesystem paths as the API.

The original proof-of-concept directories are out of scope. Changes for this
application belong in `backend_v1` (and, when needed, `frontend_v1`).

### Authentication model

Authentication uses an intentional hybrid model:

* Access JWTs are short-lived and stateless. Middleware reads the bearer header
  or `access_token` HttpOnly cookie and stores only the UUID in request state.
* Refresh JWTs are rotated on every use. Their `jti`, owner, expiry, and
  revocation state are stored in `refresh_tokens`; the raw token is never
  stored. This permits logout, password-change revocation, device/session
  revocation, and replay detection.
* Browser state-changing requests should use same-site cookies and, when the
  deployment has cross-site requirements, add an explicit CSRF token mechanism.
  Do not weaken HttpOnly or cookie security settings to work around frontend
  integration problems.

Roles are enforced with `require_roles(...)`, while object-level access is
checked in each route. Admins can see all groups; teachers can manage only
groups they own; students can read only groups they joined and their own
attendance.

### Pagination and roster APIs

Collection endpoints return an envelope with `items` and `meta`:

```json
{"items": [], "meta": {"page": 1, "page_size": 25, "total": 0, "pages": 0}}
```

Use `?page=1&page_size=25`; page size is capped at 100. Pagination is
available on groups, group sessions, group attendance, admin student listings,
and group rosters. Roster management is exposed through:

```text
GET    /api/groups/{group_id}/students
DELETE /api/groups/{group_id}/students/{student_id}
```

The roster `student_id` in the delete URL is the UUID of the `User` referenced
by attendance and membership records. Each roster item also includes the
separate student-profile UUID. Teachers can modify only their own groups;
students can read joined-group rosters but cannot modify them.

### CSRF contract

Login and refresh set an HttpOnly access/refresh cookie pair plus a readable
`csrf_token` cookie. Browser clients must copy the CSRF cookie value into the
`X-CSRF-Token` header on every cookie-authenticated `POST`, `PUT`, `PATCH`, or
`DELETE` request. Bearer-token requests are not subject to the cookie check.
Login, registration, and refresh are exempt because they establish
authentication. A missing or mismatched token returns HTTP 403.

### Session lifecycle

`created -> processing -> review -> finalized` is the successful lifecycle.
`failed` is terminal until a future retry/reprocess endpoint is added. Classroom
photos are stored under `SESSION_PHOTO_DIR` for seven days by default. Each
upload schedules delayed deletion, and Celery Beat runs a periodic cleanup
backstop. The `DELETE /api/sessions/{id}` contract is deliberately a bodyless
HTTP 204 response; do not return a JSON object from this endpoint.

Attendance processing must remain idempotent: the unique
`(session_id, student_id)` constraint means a retry updates the existing record
instead of creating duplicates. Future changes to the task must preserve this
property and must not mark a session `review` until all photos have been
processed.

### Worker progress

Redis delivers Celery tasks, while PostgreSQL stores durable session progress.
`process_class_session` updates `processing_total`, `processing_completed`,
and `processing_message` after each classroom image. Clients can poll
`GET /api/sessions/{id}` or `GET /api/sessions/{id}/progress`; progress remains
available after a worker restart instead of relying only on transient Celery
result metadata.

### Files and uploads

All uploaded images are validated by MIME type, size, and generated storage
keys. Bulk ZIP entries reject traversal paths and oversized entries. The ZIP is
optional, and Excel `photo` values are matched to ZIP filenames. Never use an
uploaded filename as a filesystem path without normalization.

The Docker image declares `/app/data` as a volume. Production deployments must
mount durable storage there or replace the local path implementation with an
object-storage adapter. Container-local storage is suitable only for local
development and will lose images when the container is recreated.

Set `STORAGE_BACKEND=s3` in production to use the S3 adapter. Configure
`STORAGE_BUCKET`, `STORAGE_REGION`, and credentials through the environment or
the workload's IAM role. `STORAGE_ENDPOINT_URL` supports S3-compatible systems
such as MinIO. Profile images, classroom images, staged imports, and generated
CSV error reports all use this adapter.

### Email and student credentials

Admin-created student accounts receive a cryptographically random ten-character
temporary password. The password is not stored in plaintext; it is sent once
to the queued email task and then discarded. Development delivery uses Python
SMTP (`EMAIL_BACKEND=smtp`), normally against MailHog/Mailpit on port 1025.
Production can use AWS SES with `EMAIL_BACKEND=ses` and `SES_REGION`; use an IAM
role rather than putting AWS keys in the repository. The welcome message is an
HTML email with a plain-text alternative.

### Asynchronous Excel imports

All supported public Excel imports are staged and processed by Celery:

```text
POST /api/admin/students/bulk
POST /api/admin/students/bulk-update
POST /api/groups/{group_id}/students/bulk
GET  /api/import-jobs/{job_id}
GET  /api/import-jobs/{job_id}/errors
```

`bulk-update` expects `RollNo`, `New RollNo`, and `Full Name` columns. Header
matching is case- and whitespace-insensitive. Import responses contain a job
ID, and the status response reports `total`, `processed`, `succeeded`, and
`failed`. Failed rows are written to a downloadable CSV containing `row` and
`error` columns. The optional ZIP in student creation is staged with the Excel
file and processed by the worker. Never process these uploads synchronously in
an HTTP route or return a success result before the job has been committed. A
`password` column may be supplied for controlled development imports; when it
is absent, the worker generates a random temporary password and sends it by
email. Do not use a shared password column in production.

### Migrations and verification

Every model change needs an Alembic revision. Apply and inspect migrations with:

```bash
alembic upgrade head
alembic current
pytest -q
python -m compileall -q app alembic
git diff --check
```

The current import-job revision is `0010_import_jobs`. Migration downgrades should
be implemented before a production rollback policy depends on them.

Run the API and worker separately during development:

```bash
uvicorn app.main:app --reload
celery -A app.celery_app.celery_app worker --loglevel=info
celery -A app.celery_app.celery_app beat --loglevel=info
```

Only one Beat scheduler should run for a deployment. Without Beat, queued
photo processing still works, but periodic retention and refresh-token cleanup
will not run.

### Change checklist for future agents

1. Confirm the change is under `backend_v1` and inspect existing migrations.
2. Preserve UUID primary and foreign keys; do not introduce integer object IDs.
3. Add or update an Alembic migration for schema changes.
4. Enforce both role-level and object-level authorization.
5. Keep image/face processing asynchronous and retry-safe.
6. Add audit logging for administrative or attendance mutations.
7. Add a regression test for every response-contract or permission change.
8. Run migrations, tests, compile checks, and `git diff --check` before handoff.
