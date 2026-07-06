# Deployment guide — Attendance (on-prem)

This system is designed to run **entirely on the college's own server**. No
student data — photos, face embeddings, or attendance records — ever leaves
that machine. Everything runs as Docker containers via a single Compose file.

---

## 1. Requirements

- A Linux server (Ubuntu 22.04+ recommended) the college controls.
- **Docker** + **Docker Compose v2** installed.
- ~4 GB RAM, 2+ CPU cores. A GPU is **optional** (see §6).
- Outbound internet access **once**, on first run, to download the face model
  (~300 MB) and container images. After that it can run fully offline.

For the expected load (~10 concurrent class sessions), CPU-only is sufficient.
Each class photo takes a few seconds to process on CPU.

---

## 2. First-time setup

```bash
git clone <your-repo-url> attendance
cd attendance

cp .env.example .env
# Edit .env — you MUST change these before going live:
#   POSTGRES_PASSWORD   -> a long random string
#   JWT_SECRET          -> output of: openssl rand -hex 32
#   BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD -> your first admin login

docker compose up -d --build
```

On first boot the API will:
- create the database schema (and the `pgvector` extension),
- create the bootstrap admin account from your `.env`,
- start the photo-retention loop.

The InsightFace model downloads on the **first face operation** (first
enrollment or first class photo), not at boot — the first one is slower.

Check it's healthy:
```bash
curl http://localhost:8000/health      # -> {"status":"ok"}
```

Open the teacher app at `http://<server>:8000/` and log in as the admin.

---

## 3. Onboarding students (bulk)

Prepare a CSV and a folder of one-face-per-student photos:

```
# students.csv
roll_no,full_name,department,photo,consent
2021CS001,Asha Rao,CSE,2021CS001.jpg,yes
2021CS002,Vikram Nair,CSE,2021CS002.jpg,yes
```

`consent` **must** be yes for a face to be enrolled (see §7). Then:

```bash
python scripts/bulk_enroll.py \
  --api http://localhost:8000 \
  --admin-email admin@college.edu --admin-password '...' \
  --csv students.csv --photos-dir ./photos
```

The script sends each photo to the API, which converts it to an embedding and
**discards the photo**. After the run, delete your local `./photos` folder —
it is source biometric material you no longer need.

Create courses and rosters via the API (`POST /courses`, then
`POST /courses/{id}/roster` with a list of roll numbers), or build a small
admin screen later.

---

## 4. Daily use (teacher)

1. Log in at `http://<server>:8000/`.
2. Pick the course → **Start session**.
3. Take/upload the class group photo → **Upload & recognise**.
4. Review the auto-marked roster; tap any name to correct present/absent.
5. **Finalise** — the record becomes authoritative.

---

## 5. What must NEVER enter git

`.gitignore` already blocks these, but to be explicit — committing biometric
data would be a serious DPDP breach:

| Never commit | Where it actually lives |
|---|---|
| `.env` (secrets) | server only |
| Raw student/class photos | transient disk, auto-purged |
| Face embeddings | Postgres (`db_data` volume) |
| Attendance records | Postgres |
| The Postgres data volume / dumps | server only |

Only **code**, `docker-compose.yml`, and docs belong in git.

---

## 6. GPU (optional, only if you scale up)

CPU is fine for ~10 concurrent classes. If you later run many more, install the
NVIDIA container toolkit and:
- set `FACE_PROVIDER=CUDAExecutionProvider` in `.env`,
- change `onnxruntime` to `onnxruntime-gpu` in `backend/requirements.txt`,
- add a `deploy.resources.reservations.devices` GPU reservation to the `worker`
  service, and rebuild.

To handle more simultaneous photos, raise the worker `--concurrency` and/or run
more `worker` replicas.

---

## 7. Security & compliance checklist (do NOT skip)

Facial embeddings are **biometric data** — sensitive personal data under
India's DPDP Act 2023. Before enrolling a single real student:

- [ ] **Consent**: record explicit, informed biometric consent per student. The
      API refuses face enrollment unless `biometric_consent` is true.
- [ ] **Opt-out path**: offer manual roll-call for anyone who declines. Never
      make face recognition the only way to be marked present.
- [ ] **Change all default secrets** in `.env`.
- [ ] **TLS**: put the API behind a reverse proxy (nginx/Caddy) with HTTPS. Do
      not expose port 8000 in cleartext beyond localhost.
- [ ] **Disk encryption**: enable full-disk / volume encryption on the server so
      the Postgres volume (embeddings) is encrypted at rest.
- [ ] **Backups**: back up the `db_data` volume; store backups encrypted.
- [ ] **Right to erasure**: `DELETE /students/{id}/face` removes a student's
      embedding on request.
- [ ] **Retention**: raw photos auto-delete after `PHOTO_RETENTION_MINUTES`.
      Define and document how long attendance records themselves are kept.
- [ ] **Access**: teachers only see their own sessions (enforced in code).
      Every match and correction is written to the `audit_log` table.
- [ ] **Base image patching**: rebuild periodically so OS CVEs in the Python
      base image are picked up (`docker compose build --pull`).
- [ ] **Bias / accuracy testing**: validate match accuracy across skin tones and
      lighting before trusting auto-marks; keep the human review step.
- [ ] Loop in the college's data-protection officer / legal before go-live.

---

## 8. Operations

```bash
docker compose ps                 # status
docker compose logs -f api        # API logs
docker compose logs -f worker     # matching logs
docker compose down               # stop (data volumes persist)
docker compose build --pull && docker compose up -d   # update + patch base image
```

Backup the database:
```bash
docker compose exec db pg_dump -U attendance attendance > backup_$(date +%F).sql
# store this file encrypted, off-server; then delete the local plaintext copy
```
