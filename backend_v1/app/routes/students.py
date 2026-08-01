"""Student profile and verified photo enrollment routes."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import PhotoProcessingJob, Student, StudentPhoto, User, UserRole
from ..schemas import PhotoJobOut, StudentOut, StudentPhotoOut
from ..security import CurrentUser, require_roles
from ..storage import storage
from ..tasks import process_student_photo

router = APIRouter(prefix="/api/students", tags=["students"])
DbSession = Annotated[Session, Depends(get_db)]


def _photo_url(request: Request, photo_id: UUID) -> str:
    return str(request.url_for("student_photo_image", photo_id=photo_id).path)


def _to_out(student: Student, request: Request) -> StudentOut:
    photos = sorted(student.photos, key=lambda photo: photo.created_at, reverse=True)
    return StudentOut(
        id=student.id,
        user_id=student.user_id,
        roll_no=student.roll_no,
        full_name=student.full_name,
        profile_image_url=student.profile_image_url,
        photo_count=len(photos),
        photos=[StudentPhotoOut(id=p.id, image_url=_photo_url(request, p.id) if p.storage_key else None, similarity_to_previous=p.similarity_to_previous, is_profile=p.is_profile, created_at=p.created_at) for p in photos],
    )


def _student_for_user(user: User, db: Session) -> Student:
    student = db.query(Student).filter(Student.user_id == user.id).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student profile not found")
    return student


@router.get("/me", response_model=StudentOut)
def my_student_profile(request: Request, user: CurrentUser, db: DbSession) -> StudentOut:
    if user.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students have student profiles")
    return _to_out(_student_for_user(user, db), request)


@router.post("/me/photos", response_model=PhotoJobOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_profile_photo(
    request: Request,
    db: DbSession,
    file: UploadFile = File(...),
    user: User = Depends(require_roles(UserRole.student)),
) -> PhotoJobOut:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Use JPEG, PNG, or WebP")
    image_bytes = await file.read()
    if len(image_bytes) > settings.max_profile_photo_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Profile photo is too large")
    student = _student_for_user(user, db)
    key = f"profile/pending/{student.id}/{secrets.token_urlsafe(24)}.{file.content_type.split('/')[-1]}"
    storage.put_bytes(key, image_bytes, file.content_type)
    job = PhotoProcessingJob(student_id=student.id, storage_key=key, content_type=file.content_type)
    db.add(job)
    db.flush()
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    process_student_photo.delay(job.id)
    db.refresh(job)
    return PhotoJobOut.model_validate(job)


@router.get("/me/photo-jobs/{job_id}", response_model=PhotoJobOut)
def my_photo_job_status(job_id: UUID, db: DbSession, user: User = Depends(require_roles(UserRole.student))) -> PhotoProcessingJob:
    student = _student_for_user(user, db)
    job = db.get(PhotoProcessingJob, job_id)
    if job is None or job.student_id != student.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo job not found")
    return job


@router.get("/photos/{photo_id}/image", name="student_photo_image", include_in_schema=False)
def student_photo_image(photo_id: UUID, user: CurrentUser, db: DbSession):
    photo = db.get(StudentPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    student = db.get(Student, photo.student_id)
    if user.role != UserRole.admin and (user.role != UserRole.student or student is None or student.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this photo")
    if photo.storage_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Only the latest profile image is retained")
    if not storage.exists(photo.storage_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo file not found")
    return StreamingResponse(BytesIO(storage.get_bytes(photo.storage_key)), media_type=photo.content_type)
