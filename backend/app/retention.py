"""Data-retention: purge raw class photos after a short review window.

Embeddings and attendance records are kept; raw photos are biometric source
material and are deleted once the teacher's dispute-review window has passed.
Runs as a lightweight background loop inside the API process.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone

from .config import settings
from .database import SessionLocal
from .models import ClassSession
from .security import audit

_PURGE_INTERVAL_SECONDS = 300  # check every 5 minutes


def purge_expired_photos() -> int:
    """Delete raw photos older than the retention window. Returns count purged."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.photo_retention_minutes)
    db = SessionLocal()
    purged = 0
    try:
        sessions = (
            db.query(ClassSession)
            .filter(
                ClassSession.photo_purged.is_(False),
                ClassSession.photo_path.isnot(None),
                ClassSession.started_at < cutoff,
            )
            .all()
        )
        for s in sessions:
            try:
                if s.photo_path and os.path.exists(s.photo_path):
                    os.remove(s.photo_path)
            except OSError:
                pass  # best-effort; will retry next cycle if it still exists
            s.photo_purged = True
            audit(db, "purge", "session", s.id, detail="raw photo deleted")
            purged += 1
        if purged:
            db.commit()
    finally:
        db.close()
    return purged


def start_retention_loop() -> threading.Thread:
    """Start the purge loop on a daemon thread."""

    def _loop() -> None:
        while True:
            try:
                purge_expired_photos()
            except Exception:  # noqa: BLE001  — never let the loop die
                pass
            time.sleep(_PURGE_INTERVAL_SECONDS)

    t = threading.Thread(target=_loop, name="retention", daemon=True)
    t.start()
    return t
