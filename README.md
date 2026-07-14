# Attendance (face-recognition, on-prem)

Group-photo attendance for a college (~14k+ students). A teacher starts a class
session, takes **one group photo**, and the system recognises enrolled students
and marks attendance — with a human review step before anything is finalised.

Built to be **deployed on the college's own server** (not a cloud service), so
biometric data never leaves their control.

## How it works

```
Teacher web app ──photo──▶ FastAPI ──job──▶ Redis ──▶ Worker (InsightFace)
      ▲                        │                            │
      └────review/correct──────┴──── Postgres (pgvector) ◀──┘
                              (embeddings + attendance + audit)
```

1. **Enroll** each student's face once → stored as a 512-dim ArcFace embedding
   (never a stored photo).
2. **Roster-scoped matching**: a class photo is matched only against the ~60–90
   students enrolled in *that* course — fast, and far fewer false matches than
   searching all 14k+.
3. **Anti-spoofing**: passive liveness checks (blur + face size) always run;
   an optional ONNX model adds an active liveness score.
4. **Async**: the teacher's upload returns immediately; a Celery worker does the
   detection + matching and results appear a few seconds later for review.
5. **Human-in-the-loop**: the teacher confirms/corrects before finalising.

## Features

- **Teacher app** — login, pick course, capture/upload photo, review
  auto-marks (with confidence + liveness score), correct, finalise; session
  history with CSV export.
- **Admin app** — courses (with inline roster management), students (search,
  pagination, consent grant/revoke), user accounts, attendance reports
  (per-course date-range summaries, below-75% list, CSV download).
- **Privacy by design** — consent-gated enrollment with a timestamped record of
  who granted it, right-to-erasure endpoint, raw photos auto-purged after a
  short review window, full audit log. See [DEPLOYMENT.md](DEPLOYMENT.md) §7.
- **Ops** — Alembic schema migrations run automatically at startup, health
  checks on every service, optional nginx TLS proxy with Let's Encrypt
  auto-renewal, optional Flower dashboard for the worker queue.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI (Python 3.11) |
| Face detection + recognition | InsightFace (RetinaFace + ArcFace, `buffalo_l`) |
| DB | PostgreSQL 16 + `pgvector`, migrations via Alembic |
| Queue / worker | Redis + Celery |
| Web clients | Vanilla-JS single-page app (teacher + admin, phone-friendly) |
| Reverse proxy (prod) | nginx with TLS, rate limiting, security headers |
| Deploy | Docker Compose, single server |

## Setup

### Prerequisites

- A Linux server (or any machine with Docker) — 4+ CPU cores and 8 GB RAM are
  plenty for CPU inference; no GPU required.
- Docker Engine 24+ with the Compose plugin (`docker compose version`).
- Ports: 8000 (dev) or 80/443 (prod profile).

### 1. Clone and configure

```bash
git clone https://github.com/Akaksingh/automatic_attendance_dtu.git
cd automatic_attendance_dtu
cp .env.example .env
```

Edit `.env` — you **must** change these before going live:

| Variable | What to set |
|---|---|
| `POSTGRES_PASSWORD` | a long random string |
| `JWT_SECRET` | output of `openssl rand -hex 32` |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | your first admin login |

Everything else has sensible defaults (thresholds, retention window, liveness
knobs — all documented inline in [.env.example](.env.example)).

### 2. Start the stack

```bash
docker compose up -d --build
```

First run downloads the InsightFace model weights (~300 MB) into the
`model_cache` volume — give it a couple of minutes, then open
**http://localhost:8000** and log in with the bootstrap admin credentials.
The database schema is created/upgraded automatically (Alembic) on startup.

On Windows, `start_docker.bat` wraps the same thing.

### 3. Onboard students

In the admin UI: create courses, add students, record consent, manage rosters.
For bulk onboarding from a CSV + a folder of photos:

```bash
python scripts/bulk_enroll.py --api http://localhost:8000 \
    --admin-email admin@college.edu --admin-password '...' \
    --csv students.csv --photos-dir ./photos
```

Photos are converted to embeddings server-side and are **not** stored; delete
your local copies afterwards. See [scripts/students.sample.csv](scripts/students.sample.csv)
for the CSV format.

### 4. Production (TLS)

```bash
./scripts/setup_tls.sh self-signed                    # intranet deployments
# or, with a public hostname (auto-renews via the certbot service):
./scripts/setup_tls.sh letsencrypt attendance.example.edu admin@example.edu

docker compose --profile prod up -d
```

The `prod` profile adds nginx (TLS termination, HTTP→HTTPS redirect, security
headers, upload rate-limiting) on ports 80/443. Read the security & compliance
checklist in [DEPLOYMENT.md](DEPLOYMENT.md) before enrolling real students.

### Optional extras

```bash
docker compose --profile monitoring up -d   # Flower (Celery dashboard) on :5555
bash scripts/smoke_test.sh                  # end-to-end smoke test against the stack
```

### Running the tests (no Docker needed)

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v          # runs on in-memory SQLite; 48 tests
ruff check app/ tests/    # lint (same as CI)
```

CI (GitHub Actions) runs both on every push and pull request.

## Repository layout

```
├── docker-compose.yml       All services: db (pgvector), redis, api, worker,
│                            + profiles: flower (monitoring), nginx/certbot (prod)
├── .env.example             Every setting, documented — copy to .env
├── backend/
│   ├── Dockerfile           API + worker image (non-root, healthcheck)
│   ├── requirements.txt     Pinned Python dependencies
│   ├── alembic/             Schema migrations (run automatically at startup)
│   ├── app/
│   │   ├── main.py          FastAPI app: routers, lifespan (migrations,
│   │   │                    bootstrap admin, retention loop), static frontend
│   │   ├── config.py        Settings loaded from environment / .env
│   │   ├── database.py      Engine, session factory, init_db
│   │   ├── migrations.py    Programmatic Alembic runner (+ adoption of
│   │   │                    pre-Alembic databases)
│   │   ├── models.py        SQLAlchemy models: users, students, embeddings,
│   │   │                    courses, enrollments, sessions, attendance, audit
│   │   ├── schemas.py       Pydantic request/response models
│   │   ├── security.py      Password hashing, JWT, RBAC deps, audit helper
│   │   ├── retention.py     Background purge of raw photos after review window
│   │   ├── worker.py        Celery task: photo → liveness filter →
│   │   │                    roster-scoped matching → attendance rows
│   │   ├── face/engine.py   InsightFace wrapper: detect, embed, cosine match
│   │   └── routes/
│   │       ├── auth.py      Login, /me, user management (admin)
│   │       ├── students.py  CRUD, search, consent, face enroll/erase
│   │       ├── courses.py   CRUD + roster add/remove
│   │       ├── sessions.py  Create → upload photo → review → correct → finalise
│   │       └── reports.py   Attendance summaries + CSV exports
│   └── tests/               pytest suite (in-memory SQLite, no Docker)
├── frontend/                Teacher + admin single-page app (vanilla JS)
├── nginx/                   Reverse-proxy image + TLS config
├── scripts/
│   ├── bulk_enroll.py       One-time onboarding: CSV + photos → students + faces
│   ├── evaluate_accuracy.py Accuracy/bias harness (TAR/FAR/rank-1, per-group
│   │                        skin-tone / lighting breakdowns, bias flags)
│   ├── setup_tls.sh         Cert provisioning: self-signed or Let's Encrypt
│   └── smoke_test.sh        End-to-end check against a running stack
├── .github/workflows/ci.yml Lint + tests on every push/PR
├── DEPLOYMENT.md            Full deployment guide + DPDP compliance checklist
└── PROJECT_STATUS.md        What's done, what's next
```

## Scope

- **Now:** in-person classroom attendance via group photo, with admin tooling,
  reports, liveness checks, and production TLS.
- **Future:** Google Meet participant-log integration (online attendance from
  join/leave times — no face recognition needed there); GPU inference if
  concurrency outgrows CPU.

## Compliance

Face embeddings are biometric data under India's **DPDP Act 2023**. The system
requires per-student consent (recorded with timestamp and recorder), supports
the right to erasure, auto-deletes raw photos, and logs all matches and
corrections. Validate accuracy across demographic groups with
`scripts/evaluate_accuracy.py` and read the checklist in
[DEPLOYMENT.md §7](DEPLOYMENT.md) before going live.

## License

[MIT](LICENSE)
