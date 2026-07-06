# Attendance (face-recognition, on-prem)

Group-photo attendance for a college. A teacher starts a class session, takes
one group photo, and the system recognises enrolled students and marks
attendance — with a human review step before anything is finalised.

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
3. **Async**: the teacher's upload returns immediately; a Celery worker does the
   detection + matching and results appear a few seconds later for review.
4. **Human-in-the-loop**: the teacher confirms/corrects before finalising.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI (Python) |
| Face detection + recognition | InsightFace (RetinaFace + ArcFace, `buffalo_l`) |
| DB | PostgreSQL + `pgvector` |
| Queue / worker | Redis + Celery |
| Teacher client | Vanilla-JS web app (works on any phone browser) |
| Deploy | Docker Compose, single server |

## Quick start

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the full guide. TL;DR:

```bash
cp .env.example .env      # then edit secrets
docker compose up -d --build
# open http://localhost:8000/
```

## Project layout

```
docker-compose.yml      Postgres+pgvector, Redis, API, worker
backend/app/
  main.py               FastAPI app + startup (schema, bootstrap admin, retention)
  models.py             SQLAlchemy models
  face/engine.py        InsightFace detect + embed + cosine match
  worker.py             Celery task: photo -> roster-scoped matching -> attendance
  routes/               auth, students (enroll/erase face), courses, sessions
  retention.py          background purge of raw photos
scripts/bulk_enroll.py  one-time onboarding of students + faces from a CSV
frontend/               teacher web app (login, capture, review, finalise)
```

## Scope

- **v1 (this repo):** in-person classroom attendance via group photo.
- **Not yet:** Google Meet participant-log integration (planned; would mark
  online attendance from join/leave times, no face recognition needed there).

## Compliance

Face embeddings are biometric data under India's **DPDP Act 2023**. The system
requires per-student consent, supports the right to erasure, auto-deletes raw
photos, and logs all matches/corrections. Read the checklist in
[DEPLOYMENT.md §7](DEPLOYMENT.md) before going live.
