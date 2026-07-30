"""Class-session lifecycle, classroom image review, and attendance correction."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AttendanceRecord, AttendanceStatus, ClassSession, Group, GroupMembership, SessionPhoto, SessionState, User, UserRole
from ..schemas import AttendanceStatusUpdate, SessionAttendanceOut, SessionOut, SessionPhotoOut
from ..security import CurrentUser, require_roles
from ..tasks import expire_session_photo, process_class_session

router = APIRouter(prefix="/api", tags=["sessions"])
DbSession = Annotated[Session, Depends(get_db)]


def _get_session(session_id: UUID, db: Session) -> ClassSession:
    session = db.get(ClassSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _staff_can_manage(session: ClassSession, user: User) -> bool:
    return user.role == UserRole.admin or (user.role == UserRole.teacher and session.group.owner_id == user.id)


def _authorized(session: ClassSession, user: User, db: Session) -> bool:
    if _staff_can_manage(session, user):
        return True
    return user.role == UserRole.student and db.query(GroupMembership).filter_by(group_id=session.group_id, student_id=user.id).first() is not None


def _photo_url(request: Request, photo_id: UUID) -> str:
    return str(request.url_for("session_photo_image", photo_id=photo_id))


def _to_out(session: ClassSession, request: Request, user: User, db: Session) -> SessionOut:
    attendance = session.attendance_records
    if user.role == UserRole.student:
        attendance = [record for record in attendance if record.student_id == user.id]
    return SessionOut(
        id=session.id,
        group_id=session.group_id,
        created_by_id=session.created_by_id,
        state=session.state,
        started_at=session.started_at,
        finalized_at=session.finalized_at,
        photos=[SessionPhotoOut(id=photo.id, image_url=_photo_url(request, photo.id), expires_at=photo.expires_at, processed_at=photo.processed_at, error=photo.error, created_at=photo.created_at) for photo in session.photos],
        attendance=[SessionAttendanceOut(id=record.id, student_id=record.student_id, status=record.status, marked_at=record.marked_at) for record in attendance],
    )


@router.post("/groups/{group_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    group_id: UUID,
    request: Request,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> SessionOut:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Archived groups cannot start sessions")
    if user.role != UserRole.admin and group.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only start sessions for groups you created")
    session = ClassSession(group_id=group.id, created_by_id=user.id, state=SessionState.created)
    db.add(session)
    db.commit()
    db.refresh(session)
    return _to_out(session, request, user, db)


@router.get("/groups/{group_id}/sessions", response_model=list[SessionOut])
def list_sessions(group_id: UUID, request: Request, db: DbSession, user: CurrentUser) -> list[SessionOut]:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if user.role == UserRole.admin:
        pass
    elif user.role == UserRole.teacher and group.owner_id == user.id:
        pass
    elif user.role == UserRole.student and db.query(GroupMembership).filter_by(group_id=group_id, student_id=user.id).first():
        pass
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access these sessions")
    sessions = db.query(ClassSession).filter(ClassSession.group_id == group_id).order_by(ClassSession.started_at.desc()).all()
    return [_to_out(session, request, user, db) for session in sessions]


@router.post("/sessions/{session_id}/photos", response_model=SessionOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_session_photos(
    session_id: UUID,
    request: Request,
    db: DbSession,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> SessionOut:
    session = _get_session(session_id, db)
    if not _staff_can_manage(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage this session")
    if session.state == SessionState.finalized:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Finalized sessions cannot be changed")
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Upload at least one classroom image")
    staged: list[Path] = []
    try:
        expires_at = datetime.now(UTC) + timedelta(days=settings.session_photo_retention_days)
        for file in files:
            if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Use JPEG, PNG, or WebP classroom images")
            content = await file.read()
            if len(content) > settings.max_profile_photo_bytes:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Classroom image is too large")
            key = f"{session.id}/{uuid4()}{Path(file.filename or '').suffix.lower() or '.jpg'}"
            path = Path(settings.session_photo_dir) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            staged.append(path)
            db.add(SessionPhoto(session_id=session.id, storage_key=key, content_type=file.content_type, expires_at=expires_at))
        session.state = SessionState.processing
        db.commit()
    except Exception:
        db.rollback()
        for path in staged:
            path.unlink(missing_ok=True)
        raise
    db.refresh(session)
    process_class_session.delay(session.id)
    for photo in session.photos:
        expire_session_photo.apply_async(args=[photo.id], countdown=settings.session_photo_retention_days * 86400)
    return _to_out(session, request, user, db)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: UUID, request: Request, db: DbSession, user: CurrentUser) -> SessionOut:
    session = _get_session(session_id, db)
    if not _authorized(session, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this session")
    return _to_out(session, request, user, db)


@router.get("/sessions/photos/{photo_id}/image", name="session_photo_image", include_in_schema=False)
def session_photo_image(photo_id: UUID, user: CurrentUser, db: DbSession):
    photo = db.get(SessionPhoto, photo_id)
    if photo is None or photo.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session image is unavailable")
    session = _get_session(photo.session_id, db)
    if not _authorized(session, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this image")
    path = Path(settings.session_photo_dir) / photo.storage_key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session image is unavailable")
    return FileResponse(path, media_type=photo.content_type)


@router.patch("/sessions/{session_id}/attendance/{student_id}", response_model=SessionAttendanceOut)
def update_attendance(
    session_id: UUID,
    student_id: UUID,
    payload: AttendanceStatusUpdate,
    db: DbSession,
    user: User = Depends(require_roles(UserRole.admin, UserRole.teacher)),
) -> AttendanceRecord:
    session = _get_session(session_id, db)
    if not _staff_can_manage(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot modify this session")
    if session.state == SessionState.finalized:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Finalized attendance cannot be changed")
    if not db.query(GroupMembership).filter_by(group_id=session.group_id, student_id=student_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not in this group")
    record = db.query(AttendanceRecord).filter_by(session_id=session.id, student_id=student_id).first()
    if record is None:
        record = AttendanceRecord(session_id=session.id, student_id=student_id, status=payload.status)
        db.add(record)
    else:
        record.status = payload.status
        record.marked_at = datetime.now(UTC)
    db.commit()
    db.refresh(record)
    return record


@router.post("/sessions/{session_id}/finalize", response_model=SessionOut)
def finalize_session(session_id: UUID, request: Request, db: DbSession, user: User = Depends(require_roles(UserRole.admin, UserRole.teacher))) -> SessionOut:
    session = _get_session(session_id, db)
    if not _staff_can_manage(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot finalize this session")
    if session.state != SessionState.review:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session must finish processing before finalization")
    session.state = SessionState.finalized
    session.finalized_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return _to_out(session, request, user, db)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: UUID, db: DbSession, user: User = Depends(require_roles(UserRole.admin, UserRole.teacher))) -> None:
    session = _get_session(session_id, db)
    if not _staff_can_manage(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete this session")
    for photo in session.photos:
        (Path(settings.session_photo_dir) / photo.storage_key).unlink(missing_ok=True)
    db.delete(session)
    db.commit()
