"""Background tasks for account provisioning and face-photo processing."""
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import numpy as np

from .celery_app import celery_app
from .config import settings
from .database import SessionLocal
from .face.engine import cosine_similarity, detect_faces, embed_single_face
from .models import AttendanceRecord, AttendanceStatus, ClassSession, GroupMembership, PhotoJobStatus, PhotoProcessingJob, SessionPhoto, SessionState, Student, StudentPhoto


@celery_app.task(name="app.tasks.ping")
def ping() -> dict[str, str]:
    """Minimal task that confirms the worker can consume a Celery job."""
    return {"status": "ok"}


@celery_app.task(bind=True, name="app.tasks.process_student_photo", max_retries=2)
def process_student_photo(self, job_id: UUID) -> dict[str, object]:
    """Verify one staged image and promote it to the student's photo history."""
    with SessionLocal() as db:
        job = db.get(PhotoProcessingJob, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        if job.status in {PhotoJobStatus.approved, PhotoJobStatus.rejected}:
            return {"status": job.status.value, "job_id": job_id}
        job.status = PhotoJobStatus.processing
        db.commit()
        path = Path(settings.profile_photo_dir) / job.storage_key
        try:
            if not path.is_file():
                raise ValueError("Staged photo file is missing")
            embedding = embed_single_face(path.read_bytes())
            student = db.get(Student, job.student_id)
            if student is None:
                raise ValueError("Student profile no longer exists")
            previous = db.query(StudentPhoto).filter(StudentPhoto.student_id == student.id).all()
            similarity = None
            if previous:
                similarity = max(cosine_similarity(embedding, np.asarray(json.loads(photo.embedding_json), dtype=np.float32)) for photo in previous)
                job.similarity_to_previous = similarity
                if similarity < settings.face_match_threshold:
                    job.status = PhotoJobStatus.rejected
                    job.error = f"Photo does not match the existing profile (similarity {similarity:.3f})"
                    job.completed_at = datetime.now(UTC)
                    db.commit()
                    path.unlink(missing_ok=True)
                    return {"status": "rejected", "job_id": job_id, "similarity": similarity}
            for old_photo in previous:
                old_photo.is_profile = False
                if old_photo.storage_key:
                    (Path(settings.profile_photo_dir) / old_photo.storage_key).unlink(missing_ok=True)
                    old_photo.storage_key = None
            photo = StudentPhoto(student_id=student.id, storage_key=job.storage_key, content_type=job.content_type, embedding_json=json.dumps(embedding.tolist()), similarity_to_previous=similarity, is_profile=True)
            db.add(photo)
            db.flush()
            student.profile_image_url = f"/api/students/photos/{photo.id}/image"
            student.user.profile_image_url = student.profile_image_url
            job.photo_id = photo.id
            job.status = PhotoJobStatus.approved
            job.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "approved", "job_id": job_id, "photo_id": photo.id, "similarity": similarity}
        except (ValueError, RuntimeError) as exc:
            db.rollback()
            job = db.get(PhotoProcessingJob, job_id)
            job.status = PhotoJobStatus.failed
            job.error = str(exc)
            job.completed_at = datetime.now(UTC)
            db.commit()
            path.unlink(missing_ok=True)
            return {"status": "failed", "job_id": job_id, "error": str(exc)}
        except Exception as exc:
            db.rollback()
            job = db.get(PhotoProcessingJob, job_id)
            job.status = PhotoJobStatus.failed
            job.error = "Unexpected photo processing error"
            job.completed_at = datetime.now(UTC)
            db.commit()
            path.unlink(missing_ok=True)
            raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="app.tasks.process_class_session", max_retries=2)
def process_class_session(self, session_id: UUID) -> dict[str, object]:
    """Run face matching for every classroom image and create reviewable records."""
    with SessionLocal() as db:
        session = db.get(ClassSession, session_id)
        if session is None:
            return {"status": "missing", "session_id": str(session_id)}
        session.state = SessionState.processing
        db.commit()
        try:
            memberships = db.query(GroupMembership).filter(GroupMembership.group_id == session.group_id).all()
            user_ids = [membership.student_id for membership in memberships]
            students = db.query(Student).filter(Student.user_id.in_(user_ids)).all() if user_ids else []
            references: dict[UUID, list[np.ndarray]] = {
                student.user_id: [np.asarray(json.loads(photo.embedding_json), dtype=np.float32) for photo in student.photos]
                for student in students
            }
            recognized: dict[UUID, float] = {}
            for photo in session.photos:
                path = Path(settings.session_photo_dir) / photo.storage_key
                faces = detect_faces(path.read_bytes())
                for face in faces:
                    best_user = None
                    best_score = settings.face_match_threshold
                    for user_id, embeddings in references.items():
                        if not embeddings:
                            continue
                        score = max(cosine_similarity(face.embedding, embedding) for embedding in embeddings)
                        if score >= best_score:
                            best_user, best_score = user_id, score
                    if best_user is not None:
                        recognized[best_user] = max(recognized.get(best_user, 0.0), best_score)
                photo.processed_at = datetime.now(UTC)

            for user_id in user_ids:
                record = db.query(AttendanceRecord).filter_by(session_id=session.id, student_id=user_id).first()
                status = AttendanceStatus.present if user_id in recognized else AttendanceStatus.absent
                if record is None:
                    record = AttendanceRecord(session_id=session.id, student_id=user_id, status=status)
                    db.add(record)
                else:
                    record.status = status
                    record.marked_at = datetime.now(UTC)
            session.state = SessionState.review
            db.commit()
            return {"status": "review", "session_id": str(session_id), "recognized": len(recognized), "roster": len(user_ids)}
        except (ValueError, RuntimeError) as exc:
            db.rollback()
            session = db.get(ClassSession, session_id)
            session.state = SessionState.failed
            for photo in session.photos:
                photo.error = str(exc)
            db.commit()
            return {"status": "failed", "session_id": str(session_id), "error": str(exc)}
        except Exception as exc:
            db.rollback()
            session = db.get(ClassSession, session_id)
            session.state = SessionState.failed
            db.commit()
            raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.tasks.expire_session_photo")
def expire_session_photo(photo_id: UUID) -> dict[str, object]:
    with SessionLocal() as db:
        photo = db.get(SessionPhoto, photo_id)
        if photo is None:
            return {"status": "missing", "photo_id": str(photo_id)}
        if photo.expires_at <= datetime.now(UTC):
            (Path(settings.session_photo_dir) / photo.storage_key).unlink(missing_ok=True)
            return {"status": "expired", "photo_id": str(photo_id)}
        return {"status": "not_due", "photo_id": str(photo_id)}
