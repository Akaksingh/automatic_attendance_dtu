# Project status

_Last updated: 2026-07-14 — v1.5 complete (migrations, TLS automation, bias tooling, tests green)_

## What we're making

An **automatic attendance system for a college (~14k+ students)** that marks
attendance from a **single class group photo**. A teacher starts a session,
takes one photo, and enrolled students are recognised and marked present — with a
human review step before anything is finalised.

**Deployed on the college's own server** — biometric data never leaves their
control.

### Key design decisions (locked in)
- **Face recognition, not classification** — each student is one embedding vector.
- **Roster-scoped matching** — compare only the ~60-90 students in that class.
- **Async processing** — upload returns instantly; Celery worker does matching.
- **Human-in-the-loop** — auto-marks are always reviewable before finalising.
- **Privacy by design** — consent-gated, no long-term photo storage, right-to-erasure, audit log.

### Tech stack
| Layer | Choice |
|---|---|
| API | FastAPI (Python) |
| Face detect + recognise | InsightFace (RetinaFace + ArcFace, `buffalo_l`) |
| Database | PostgreSQL + `pgvector` |
| Queue / worker | Redis + Celery |
| Teacher + Admin client | Vanilla-JS SPA (sidebar, modals, dark theme) |
| Deploy | Docker Compose (dev) + nginx TLS (prod profile) |

---

## What's done (v1.x — complete)

### v1 (original)
- [x] Architecture, Docker Compose stack (Postgres+pgvector, Redis, API, worker)
- [x] Full data model — students, embeddings, courses, rosters, sessions, attendance, audit
- [x] JWT auth + admin/teacher RBAC, bootstrap admin on first boot
- [x] InsightFace engine — detect + embed + roster-scoped greedy cosine match
- [x] Enrollment endpoint (photo → embedding, photo discarded) + bulk_enroll.py
- [x] Session flow: create → upload → async worker → review → correct → finalise
- [x] Teacher web app — login, pick course, capture photo, review, finalise
- [x] Photo auto-purge (retention loop) + full audit logging
- [x] README + DEPLOYMENT guide with DPDP compliance checklist
- [x] Smoke test script

### v1.x additions (this session)
- [x] **Dockerfile fixed** — non-root user now works; `INSIGHTFACE_HOME` points
      to `/data/model_cache` volume (not `/root/.insightface` which appuser
      cannot write); `HEALTHCHECK` added.
- [x] **docker-compose.yml** — model_cache volume corrected, `INSIGHTFACE_HOME`
      env var added to both api and worker; optional `flower` (monitoring) and
      `nginx` (TLS) services behind profiles.
- [x] **Admin UI** — full single-page app with sidebar navigation:
      - **Courses** — create, edit, delete, search; inline roster management
        (add/remove students by roll no)
      - **Students** — create, edit, delete, search (live); paginated load-more;
        consent grant/revoke button with DPDP confirmation dialog
      - **Users** — create teacher/admin accounts, edit name/role, disable
      - **Reports** — run per-course attendance report with date range, see
        attendance bars + below-75% count
- [x] **Attendance reports** — new `/reports` API router:
      - `GET /reports/courses/{id}/attendance` — JSON summary
      - `GET /reports/courses/{id}/attendance.csv` — downloadable CSV
      - `GET /reports/sessions/{id}/attendance.csv` — per-session CSV
- [x] **Consent capture flow** — `POST /students/{id}/consent` with timestamped
      DB record (`consent_recorded_at`, `consent_recorded_by`); admin UI button.
- [x] **New student/course/user endpoints** — PATCH/DELETE on all entities,
      GET single-item, search query on students list.
- [x] **nginx reverse proxy** — `nginx/nginx.conf` with TLS, HTTP→HTTPS redirect,
      security headers, photo upload rate limiting, gzip.
- [x] **pytest suite** — tests for auth, students, courses, sessions, reports
      (SQLite in-memory; no Docker needed in CI).
- [x] **GitHub Actions CI** — ruff lint + pytest on every push/PR.
- [x] **Housekeeping** — MIT LICENSE, `.gitattributes` (LF), `pyproject.toml`.
- [x] **Premium UI redesign** — Inter font, dark sidebar, step wizard, drag-drop
      upload zone, progress bar, stats chips, data tables, roster search, toast
      notifications, modal system, responsive mobile layout.

---

## What's left (v2 / future)

- [x] **GET /sessions list endpoint** — `GET /sessions` with RBAC + course/state filters
      + pagination; "My Sessions" tab now shows a real history table with Review &
      CSV actions.
- [x] **Liveness / anti-spoofing** — two-layer defence:
      - **Passive** (always-on): Laplacian blur check + minimum face-size filter; no
        extra deps.
      - **Active** (optional): plug in any Silent-Face/MIniFASNet ONNX model via
        `LIVENESS_MODEL` env var; score shown in review UI.

### v1.5 additions (this session)
- [x] **Test suite actually runs** — conftest previously connected to the real
      Postgres during TestClient startup and could never pass. Now: env is set
      before app import, StaticPool shares the in-memory SQLite across threads,
      `init_db` skips `CREATE EXTENSION` off-Postgres, retention thread is
      disabled in tests. **48/48 green + ruff clean** (also fixed:
      `POST /courses` now returns `enrolled_count` like the list endpoint).
- [x] **Alembic migrations** — `create_all` replaced on Postgres. Chain:
      `0001` (v1 schema) → `0002` (consent columns + liveness_fail enum).
      Startup auto-adopts pre-Alembic DBs by stamping the detected baseline.
      Verified against pgvector/pg16: fresh install, v1 adoption, re-run.
- [x] **TLS cert provisioning** — `scripts/setup_tls.sh` (self-signed or
      Let's Encrypt webroot issuance); `certbot` compose service renews every
      12 h, nginx reloads every 6 h. Also fixed `limit_req_zone` placement,
      which previously prevented nginx from starting at all.
- [x] **Bias / accuracy validation tooling** — `scripts/evaluate_accuracy.py`
      runs the production engine + threshold over a labeled photo set:
      TAR/FAR, rank-1, per-group (skin tone / lighting) breakdowns, non-zero
      exit when a group deviates >5pp from overall. **The actual validation
      study still needs a consented, labeled photo set from the college.**
- [ ] **Google Meet integration** (v2) — mark online attendance from Meet logs.
      Needs Google Workspace admin credentials from the college.
- [ ] **Scale-up** — GPU inference, more Celery workers if concurrency grows.
      (See DEPLOYMENT.md §6; no code changes required.)

---

## Quick start

```bash
cp .env.example .env      # edit passwords + JWT_SECRET
docker compose up -d --build
# First run downloads InsightFace weights (~300 MB) — wait ~2 min
open http://localhost:8000
```

Run the smoke test:
```bash
bash scripts/smoke_test.sh
```

Run tests (outside Docker):
```bash
cd backend && pip install -r requirements.txt && pytest tests/ -v
```

Start with nginx TLS:
```bash
./scripts/setup_tls.sh self-signed                    # or: letsencrypt <domain> <email>
docker compose --profile prod up -d
```

Monitor Celery workers:
```bash
docker compose --profile monitoring up -d
open http://localhost:5555
```
