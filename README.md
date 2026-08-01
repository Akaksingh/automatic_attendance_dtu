# DTU ClassLens Attendance

ClassLens is a CV-assisted attendance system being developed for Delhi Technological University (DTU). A teacher creates a class, starts an attendance session, uploads one or more classroom images, reviews the recognition results, corrects them when necessary, and finalizes the attendance record. Students can view their enrolled classes, session history, attendance, and retained session images. Administrators manage users, groups, imports, exports, and operational access.

This repository contains two generations of the product:

- `backend/` and `frontend/` are the original proof of concept and are retained as reference material.
- `backend_v1/` and `frontend_v1/` are the active deployable-product implementation and should be used for current development.

The previous top-level documentation for the proof of concept is preserved in [`readme_prev.md`](readme_prev.md).

## Current product capabilities

### Teachers

- Create, search, rename, archive, and unarchive classes.
- Manage class rosters by roll number or Excel import.
- Start attendance sessions and upload classroom images incrementally.
- Upload images one at a time from a mobile device; images are uploaded immediately and shown as preview cards.
- Process all collected images together, review detected attendance, correct results, and finalize the session.
- View attendance summaries and export session or group attendance to Excel.
- Update account password and view profile details.

### Students

- View enrolled classes and class details.
- Join a class using its join code.
- View attendance for individual sessions.
- View classroom images retained for the configured verification window.
- View and update the verified profile photo and change the account password.
- Open the profile from the top-right profile avatar.

### Administrators

- View and search all classes and inspect sessions, attendance, and classroom images.
- Rename active classes and export group/session attendance workbooks.
- Search users by email, name, or roll number and filter by role.
- Create individual student and teacher accounts.
- Edit individual student name, email, and roll number.
- Reset passwords, disable accounts, and re-enable disabled accounts.
- Bulk create students or teachers from Excel files.
- Bulk update student details from Excel.
- View administrator details and change the administrator password.

## Architecture

The active v1 stack is currently organized as follows:

```text
Teacher / Student / Admin browser
                 │ HTTPS + cookie authentication
                 ▼
        FastAPI backend (`backend_v1`)
          │              │
          │              ├── PostgreSQL: users, groups, sessions, attendance, audit logs
          │              ├── Object storage: profile/session/import files
          │              └── Redis + Celery: recognition and import jobs
          ▼
   InsightFace recognition worker
   roster-scoped face matching
   human review before finalization
```

The backend uses role-based access control for admin, teacher, and student workflows. Session classroom images are retained temporarily for verification; the current default is seven days. Attendance is not considered final until a teacher or administrator finalizes the session.

The recognition path is intentionally asynchronous. The API stages images and queues processing, while the worker performs detection, embedding, roster-scoped matching, and attendance candidate generation. The first InsightFace initialization downloads the required model weights into the configured model cache if they are not already present; production deployments should warm this cache during image build or controlled startup rather than relying on a user request to trigger a cold download.

## Repository layout

```text
.
├── backend_v1/
│   ├── app/
│   │   ├── main.py              FastAPI application and startup wiring
│   │   ├── config.py            Environment-backed settings
│   │   ├── models.py            SQLAlchemy models
│   │   ├── schemas.py           Pydantic request/response schemas
│   │   ├── security.py          Password hashing, JWT cookies, RBAC
│   │   ├── tasks.py             Celery imports and recognition processing
│   │   ├── face/engine.py       InsightFace integration
│   │   └── routes/               Auth, groups, sessions, students, admin, imports
│   ├── alembic/                  Database migrations
│   ├── tests/                    v1 backend tests and contract checks
│   ├── Dockerfile
│   └── .env.example
├── frontend_v1/
│   ├── src/
│   │   ├── pages/                Role-specific dashboards and detail pages
│   │   ├── components/           Shared UI and feature components
│   │   ├── context/              Authentication state
│   │   ├── lib/                  API, media URL, and utility helpers
│   │   └── types/                Shared API types
│   ├── package.json
│   └── .env.example
├── backend/                      Legacy proof-of-concept backend
├── frontend/                     Legacy proof-of-concept frontend
├── docker-compose.yml            Existing container orchestration reference
├── docker-compose.development.yml
├── DEPLOYMENT.md                 Existing deployment notes
├── PROJECT_STATUS.md             Project status notes
└── readme_prev.md                Previous proof-of-concept README
```

## Local development

### Backend

```bash
cd backend_v1
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The backend expects PostgreSQL and Redis according to the values in `backend_v1/.env`. Celery workers are required for InsightFace processing and asynchronous imports:

```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend_v1
npm install
npm run dev
```

The frontend uses the API base URL in `frontend_v1/.env`. The production build can be checked with:

```bash
npm run build
```

### Verification commands

```bash
cd backend_v1
python -m compileall -q app alembic

cd ../frontend_v1
npm run build
```

## Excel import formats

Student account creation requires:

```text
email, full_name, roll_no
```

Teacher account creation requires:

```text
email, full_name
```

Student detail updates use the current roll number as the stable lookup key:

```text
rollno, newrollno, fullname, email, password
```

The `email` and `password` columns are optional for updates. Passwords are hashed, existing refresh sessions are revoked, and a welcome email is queued when a password is supplied. Import jobs run asynchronously and expose progress and a downloadable error CSV in the administrator interface.

## Configuration and deployment notes

The current v1 settings are documented in [`backend_v1/.env.example`](backend_v1/.env.example). Important production settings include:

- PostgreSQL connection and credentials.
- Redis/Celery connection.
- Strong JWT and bootstrap-admin secrets.
- Secure authentication cookies behind HTTPS.
- Profile-photo and classroom-image retention periods.
- Object storage configuration.
- Email backend; AWS SES is supported by the existing email service.
- InsightFace model cache location.

The repository contains Docker files and Compose configurations, but the active v1 paths should be checked before production use. In particular, the root Compose file still contains references to legacy directories in some service definitions and should be reviewed as part of deployment hardening.

Before using real student biometric data, complete an accuracy evaluation, threat model, retention review, consent/legal review, backup and restore test, incident-response plan, and load test. Human review must remain available for uncertain matches and recognition failures.

## Offline and edge evaluation

Offline attendance is technically feasible and may be valuable across a large campus, but it changes the system from a request/response web application into a distributed system with local identity data, synchronization, conflict resolution, and device security requirements.

### Recommended direction

Use a cloud control plane on AWS and deploy a small number of trusted edge nodes at selected DTU buildings or network zones:

```text
                         AWS control plane
      ALB/API ── FastAPI ── Aurora PostgreSQL
         │          │       S3 + KMS + CloudWatch
         │          └─────── SQS/EventBridge or Redis-compatible jobs
         │
         └──── secure bidirectional sync over mTLS / HTTPS
                         │
        ┌────────────────┴────────────────┐
        │                                 │
  Edge node: building A             Edge node: building B
  local API + worker                local API + worker
  encrypted local DB                encrypted local DB
  temporary image spool             temporary image spool
  campus clients                    campus clients
```

An edge node should not be treated as a second independent university database. It should operate as a bounded local cache and processing appliance:

1. The AWS control plane remains the authoritative source for users, rosters, enrollment state, class membership, and finalized attendance records.
2. Before a class, an edge node receives a signed, versioned roster package containing only the students and face representations required for its assigned classes.
3. During a network outage, the edge node accepts session creation, image uploads, recognition, teacher review, and provisional finalization locally.
4. Every local mutation is written to an encrypted append-only outbox with an idempotency key, device identity, actor identity, local timestamp, and schema version.
5. When connectivity returns, the node uploads events and result artifacts. The cloud validates authorization, roster version, signatures, and idempotency before committing them.
6. Conflicts are resolved by explicit policy. Human corrections and finalized attendance should not be silently overwritten by a stale edge node.
7. The edge cache and image spool expire automatically and can be remotely revoked or wiped if a node is lost.

### AWS deployment mapping

One reasonable AWS starting point is:

- CloudFront and an application load balancer for the web/API entry point.
- ECS on Fargate for the API and ordinary workers, or EKS if the operational team already runs Kubernetes.
- Aurora PostgreSQL for the authoritative relational database.
- S3 with SSE-KMS for import files, profile assets, and short-lived session images.
- ElastiCache for Redis if retaining the current Celery/Redis design; alternatively, SQS can be introduced for durable cloud job queues.
- AWS IoT Core or a private VPN/mTLS channel for edge-node identity and connectivity management.
- AWS Systems Manager, CloudWatch, and centralized audit logs for edge fleet operations.
- AWS SES for account emails.
- KMS, Secrets Manager, IAM roles, private subnets, security groups, and CloudTrail for key, secret, network, and administrative controls.

The first implementation should keep the cloud API and edge API contract identical where practical, with an explicit `sync_metadata` section rather than exposing the cloud database directly to edge nodes.

### Important design decisions before implementation

- Whether edge nodes store raw classroom images at all, or only transiently process them and sync attendance evidence.
- Whether face embeddings may be cached outside the primary server boundary and how student consent covers that cache.
- How often rosters and revoked accounts are synchronized.
- Whether edge nodes may finalize attendance offline or only create a teacher-approved provisional record.
- What happens when the same session is opened on two devices.
- How to handle a student being removed, a profile photo changing, or a group being archived while an edge node is offline.
- Whether the campus network can provide reliable private connectivity, or whether each edge node needs an internet fallback.
- How node tampering, disk extraction, clock manipulation, and replayed sync events are detected.
- How a lost node is remotely revoked and how cached biometric material is destroyed.

### Suggested rollout

1. Build a single-node offline prototype using the existing backend domain model and an encrypted local database.
2. Add an outbox/inbox protocol with idempotency and signed event envelopes.
3. Test network interruption, duplicate delivery, stale rosters, clock skew, and simultaneous edits.
4. Pilot one building with synthetic or consented data and measure recognition latency, sync delay, storage growth, and operational recovery.
5. Only then decide whether multiple edge nodes are justified compared with a single highly available AWS deployment and campus-local network caching.

## Status

The v1 application is still under active development and should be treated as a product prototype until deployment hardening, security review, biometric accuracy evaluation, accessibility review, and operational testing are complete.

## License

See [`LICENSE`](LICENSE).
