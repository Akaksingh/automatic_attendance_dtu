"""Celery worker: process a class photo into attendance records.

Matching is ROSTER-SCOPED: each detected face is compared only against the
embeddings of students enrolled in that session's course (~60-90 vectors), not
the whole institution. This is both faster and dramatically reduces the chance
of misidentifying a student as someone from another department.
"""
from __future__ import annotations

import os

import numpy as np
from celery import Celery
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import (
    Attendance,
    AttendanceMethod,
    AttendanceStatus,
    ClassSession,
    Enrollment,
    FaceEmbedding,
    SessionState,
    Student,
)
from .security import audit

celery_app = Celery("attendance", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "attendance"


def _load_roster(db: Session, course_id: int) -> list[tuple[int, np.ndarray]]:
    """Return (student_id, embedding) for enrolled students who have a face vector."""
    rows = (
        db.query(FaceEmbedding.student_id, FaceEmbedding.vector)
        .join(Enrollment, Enrollment.student_id == FaceEmbedding.student_id)
        .filter(Enrollment.course_id == course_id)
        .all()
    )
    return [(sid, np.asarray(vec, dtype=np.float32)) for sid, vec in rows]


def _match_faces(
    face_embeddings: list[np.ndarray],
    roster: list[tuple[int, np.ndarray]],
    threshold: float,
) -> dict[int, float]:
    """Greedy best-match: assign each roster student at most once.

    Returns {student_id: confidence} for confident matches. We build the full
    similarity matrix, then repeatedly take the globally highest (face, student)
    pair above threshold, removing both once assigned. This prevents two faces
    from both claiming the same student.
    """
    if not face_embeddings or not roster:
        return {}

    faces = np.vstack(face_embeddings)                 # (F, 512)
    roster_mat = np.vstack([v for _, v in roster])     # (S, 512)
    student_ids = [sid for sid, _ in roster]

    # Both sides are L2-normalized, so dot product == cosine similarity.
    sims = faces @ roster_mat.T                        # (F, S)

    result: dict[int, float] = {}
    used_faces: set[int] = set()
    used_students: set[int] = set()

    # Flatten and sort candidate pairs by similarity, descending.
    fi, si = np.unravel_index(np.argsort(sims, axis=None)[::-1], sims.shape)
    for f, s in zip(fi.tolist(), si.tolist()):
        score = float(sims[f, s])
        if score < threshold:
            break  # everything after is smaller
        if f in used_faces or s in used_students:
            continue
        used_faces.add(f)
        used_students.add(s)
        result[student_ids[s]] = score
    return result


@celery_app.task(name="app.worker.process_session")
def process_session(session_id: int) -> dict:
    """Detect faces in the session photo and write attendance for the roster."""
    # Import here so the API process never needs to load the heavy face model.
    from .face.engine import detect_faces

    db = SessionLocal()
    try:
        session = db.get(ClassSession, session_id)
        if session is None:
            return {"error": "session not found"}

        if not session.photo_path or not os.path.exists(session.photo_path):
            session.state = SessionState.failed
            session.error = "photo missing"
            db.commit()
            return {"error": "photo missing"}

        try:
            with open(session.photo_path, "rb") as fh:
                image_bytes = fh.read()
            faces = detect_faces(image_bytes)
        except Exception as e:  # noqa: BLE001
            session.state = SessionState.failed
            session.error = f"processing error: {e}"
            db.commit()
            return {"error": str(e)}

        session.faces_detected = len(faces)
        roster = _load_roster(db, session.course_id)
        matches = _match_faces(
            [f.embedding for f in faces], roster, settings.face_match_threshold
        )

        # Write one attendance row per enrolled student: present if matched.
        enrolled_ids = [
            e.student_id
            for e in db.query(Enrollment).filter(Enrollment.course_id == session.course_id).all()
        ]
        for sid in enrolled_ids:
            present = sid in matches
            rec = (
                db.query(Attendance)
                .filter(Attendance.session_id == session_id, Attendance.student_id == sid)
                .first()
            )
            if rec is None:
                rec = Attendance(session_id=session_id, student_id=sid)
                db.add(rec)
            rec.status = AttendanceStatus.present if present else AttendanceStatus.absent
            rec.method = AttendanceMethod.auto
            rec.confidence = matches.get(sid)

        session.state = SessionState.review
        audit(
            db, "match", "session", session_id,
            detail=f"faces={len(faces)} matched={len(matches)} roster={len(enrolled_ids)}",
        )
        db.commit()
        return {
            "session_id": session_id,
            "faces_detected": len(faces),
            "matched": len(matches),
            "roster_size": len(enrolled_ids),
        }
    finally:
        db.close()
