"""Celery worker: process a class photo into attendance records.

Matching is ROSTER-SCOPED: each detected face is compared only against the
embeddings of students enrolled in that session's course (~60-90 vectors), not
the whole institution. This is both faster and dramatically reduces the chance
of misidentifying a student as someone from another department.

Anti-spoofing (liveness) — two layers:
  1. Passive: blur + minimum face-size heuristics (always active, no extra deps).
  2. Active: optional ONNX liveness model (e.g. Silent-Face / MIniFASNet) loaded
     from LIVENESS_MODEL path.  If the env var is empty, only passive checks run.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import cv2
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
)
from .security import audit

logger = logging.getLogger("attendance.worker")

celery_app = Celery("attendance", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "attendance"

# ── Liveness settings (read once at import time) ────────────────────────────
_LIVENESS_MODEL_PATH: str = os.environ.get("LIVENESS_MODEL", "").strip()
_LIVENESS_THRESHOLD: float = float(os.environ.get("LIVENESS_THRESHOLD", "0.5"))
_BLUR_THRESHOLD: float = float(os.environ.get("LIVENESS_BLUR_THRESHOLD", "60.0"))
_MIN_FACE_PX: int = int(os.environ.get("LIVENESS_MIN_FACE_PX", "32"))

# ONNX runtime session — loaded lazily on first use so it doesn't slow API boot
_onnx_session: Optional[object] = None
_onnx_loaded: bool = False


def _get_onnx_session():
    """Load the ONNX liveness model on first call; return None if unavailable."""
    global _onnx_session, _onnx_loaded
    if _onnx_loaded:
        return _onnx_session
    _onnx_loaded = True
    if not _LIVENESS_MODEL_PATH or not os.path.isfile(_LIVENESS_MODEL_PATH):
        if _LIVENESS_MODEL_PATH:
            logger.warning(
                "LIVENESS_MODEL path does not exist: %s — running passive-only",
                _LIVENESS_MODEL_PATH,
            )
        return None
    try:
        import onnxruntime as ort  # optional dep — only needed when model is set
        _onnx_session = ort.InferenceSession(
            _LIVENESS_MODEL_PATH,
            providers=["CPUExecutionProvider"],
        )
        logger.info("Liveness ONNX model loaded: %s", _LIVENESS_MODEL_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load liveness model: %s", exc)
        _onnx_session = None
    return _onnx_session


def _check_liveness(chip_bgr: np.ndarray, bbox: tuple) -> tuple[bool, float | None]:
    """Run liveness checks on a single face chip.

    Returns (passes: bool, score: float | None).
    score is None when only passive checks run, 0-1 when the ONNX model fires.

    Passive checks (always):
      * Face bounding-box must be at least MIN_FACE_PX x MIN_FACE_PX.
      * Laplacian variance of the chip must exceed BLUR_THRESHOLD.
        A blurry face is a strong signal of a photo-of-a-photo attack.

    Active check (optional, when LIVENESS_MODEL is set):
      * ONNX model returns a liveness score; must be >= LIVENESS_THRESHOLD.
    """
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1

    # ── Passive: size ──────────────────────────────────────────────────────
    if w < _MIN_FACE_PX or h < _MIN_FACE_PX:
        logger.debug("Liveness FAIL (too small): %dx%d px", w, h)
        return False, None

    # ── Passive: blur ──────────────────────────────────────────────────────
    gray = cv2.cvtColor(chip_bgr, cv2.COLOR_BGR2GRAY) if chip_bgr.ndim == 3 else chip_bgr
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur_score < _BLUR_THRESHOLD:
        logger.debug("Liveness FAIL (blur=%.1f < %.1f)", blur_score, _BLUR_THRESHOLD)
        return False, None

    # ── Active: ONNX model ─────────────────────────────────────────────────
    sess = _get_onnx_session()
    if sess is None:
        return True, None  # no model configured — passive checks passed

    try:
        # Prepare input: resize to 80x80, normalize to [0,1], NCHW
        resized = cv2.resize(chip_bgr, (80, 80)).astype(np.float32) / 255.0
        inp = np.transpose(resized, (2, 0, 1))[np.newaxis, ...]  # (1, 3, 80, 80)
        input_name = sess.get_inputs()[0].name
        output = sess.run(None, {input_name: inp})[0]
        # Model outputs shape (1, 2) — class 1 = real
        probs = np.exp(output[0]) / np.exp(output[0]).sum()
        score = float(probs[1])
        if score < _LIVENESS_THRESHOLD:
            logger.debug("Liveness FAIL (score=%.3f < %.3f)", score, _LIVENESS_THRESHOLD)
            return False, score
        return True, score
    except Exception as exc:  # noqa: BLE001
        logger.warning("Liveness model inference error: %s — treating as live", exc)
        return True, None


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
            # Decode image once so we can pass chips to liveness check
            nparr = np.frombuffer(image_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            faces = detect_faces(image_bytes)
        except Exception as e:  # noqa: BLE001
            session.state = SessionState.failed
            session.error = f"processing error: {e}"
            db.commit()
            return {"error": str(e)}

        session.faces_detected = len(faces)
        liveness_failed_count = 0

        # ── Liveness filter ────────────────────────────────────────────────
        # faces that pass liveness -> go into the matcher
        # faces that fail -> excluded from matching (marked absent automatically)
        live_embeddings: list[np.ndarray] = []

        for face in faces:
            chip = None
            bbox = (0, 0, 0, 0)
            if img_bgr is not None and hasattr(face, "bbox") and face.bbox is not None:
                x1, y1, x2, y2 = [int(v) for v in face.bbox[:4]]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(img_bgr.shape[1], x2), min(img_bgr.shape[0], y2)
                chip = img_bgr[y1:y2, x1:x2]
                bbox = (x1, y1, x2, y2)

            if chip is not None and chip.size > 0:
                passes, _ = _check_liveness(chip, bbox)
            else:
                # No chip available (e.g. bbox missing) — skip liveness, treat as live
                passes = True

            if passes:
                live_embeddings.append(face.embedding)
            else:
                liveness_failed_count += 1

        # ── Roster matching (live faces only) ──────────────────────────────
        roster = _load_roster(db, session.course_id)
        matches = _match_faces(live_embeddings, roster, settings.face_match_threshold)

        # ── Write attendance rows ──────────────────────────────────────────
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
            detail=(
                f"faces={len(faces)} live={len(live_embeddings)} "
                f"liveness_fail={liveness_failed_count} "
                f"matched={len(matches)} roster={len(enrolled_ids)}"
            ),
        )
        db.commit()
        return {
            "session_id": session_id,
            "faces_detected": len(faces),
            "liveness_failed": liveness_failed_count,
            "matched": len(matches),
            "roster_size": len(enrolled_ids),
        }
    finally:
        db.close()

