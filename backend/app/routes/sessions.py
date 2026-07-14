"""Class sessions: create, upload class photo, review auto-results, correct/finalize."""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import (
    Attendance,
    AttendanceMethod,
    ClassSession,
    Course,
    SessionState,
    Student,
    User,
)
from ..schemas import (
    AttendanceRow,
    CorrectionRequest,
    SessionCreate,
    SessionDetail,
    SessionListItem,
    SessionOut,
)
from ..security import audit, get_current_user
from ..worker import process_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionListItem])
def list_sessions(
    course_id: int | None = None,
    state: SessionState | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List sessions. Teachers see only their own; admins see all.

    Optional query params:
      - course_id: filter by course
      - state: filter by session state (created/processing/review/finalized/failed)
      - limit / offset: pagination
    """
    from ..models import Course, Role

    q = (
        db.query(ClassSession, Course, User)
        .join(Course, Course.id == ClassSession.course_id)
        .outerjoin(User, User.id == ClassSession.teacher_id)
    )
    if user.role != Role.admin:
        q = q.filter(ClassSession.teacher_id == user.id)
    if course_id is not None:
        q = q.filter(ClassSession.course_id == course_id)
    if state is not None:
        q = q.filter(ClassSession.state == state)

    rows = q.order_by(ClassSession.started_at.desc()).offset(offset).limit(limit).all()

    return [
        SessionListItem(
            id=s.id,
            course_id=s.course_id,
            course_code=c.code,
            course_name=c.name,
            state=s.state,
            started_at=s.started_at,
            faces_detected=s.faces_detected,
            teacher_name=t.full_name if t else "—",
        )
        for s, c, t in rows
    ]


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    course = db.get(Course, payload.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    s = ClassSession(course_id=course.id, teacher_id=user.id, state=SessionState.created)
    db.add(s)
    db.flush()
    audit(db, "create", "session", s.id, actor_id=user.id)
    db.commit()
    db.refresh(s)
    return s


@router.post("/{session_id}/photo", response_model=SessionOut)
async def upload_photo(
    session_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload the class group photo and queue it for async face matching.

    The raw photo is written to a transient directory and deleted by the
    retention job after PHOTO_RETENTION_MINUTES.
    """
    session = _owned_session(db, session_id, user)

    os.makedirs(settings.photo_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    path = os.path.join(settings.photo_dir, f"session_{session_id}_{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(await file.read())

    session.photo_path = path
    session.photo_purged = False
    session.state = SessionState.processing
    session.error = None
    audit(db, "upload_photo", "session", session_id, actor_id=user.id)
    db.commit()

    process_session.delay(session_id)  # hand off to the worker
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_session(db, session_id, user)
    rows = (
        db.query(Attendance, Student)
        .join(Student, Student.id == Attendance.student_id)
        .filter(Attendance.session_id == session_id)
        .order_by(Student.roll_no)
        .all()
    )
    records = [
        AttendanceRow(
            student_id=st.id,
            roll_no=st.roll_no,
            full_name=st.full_name,
            status=att.status,
            method=att.method,
            confidence=att.confidence,
        )
        for att, st in rows
    ]
    return SessionDetail(
        id=session.id,
        course_id=session.course_id,
        state=session.state,
        started_at=session.started_at,
        faces_detected=session.faces_detected,
        error=session.error,
        records=records,
    )


@router.post("/{session_id}/corrections", response_model=SessionDetail)
def apply_corrections(
    session_id: int,
    payload: CorrectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Teacher overrides auto-marks, then the session is finalized (authoritative)."""
    session = _owned_session(db, session_id, user)
    if session.state not in (SessionState.review, SessionState.finalized):
        raise HTTPException(status_code=409, detail=f"Session not reviewable (state={session.state.value})")

    by_student = {c.student_id: c.status for c in payload.corrections}
    rows = db.query(Attendance).filter(Attendance.session_id == session_id).all()
    valid_ids = {r.student_id for r in rows}
    unknown = set(by_student) - valid_ids
    if unknown:
        raise HTTPException(status_code=422, detail=f"Students not in this session: {sorted(unknown)}")

    for rec in rows:
        if rec.student_id in by_student and rec.status != by_student[rec.student_id]:
            rec.status = by_student[rec.student_id]
            rec.method = AttendanceMethod.manual
            rec.corrected_by = user.id

    session.state = SessionState.finalized
    audit(db, "finalize", "session", session_id, actor_id=user.id, detail=f"corrections={len(by_student)}")
    db.commit()
    return get_session(session_id, db, user)


def _owned_session(db: Session, session_id: int, user: User) -> ClassSession:
    """Fetch a session, enforcing that a teacher can only touch their own."""
    session = db.get(ClassSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from ..models import Role

    if user.role != Role.admin and session.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    return session
