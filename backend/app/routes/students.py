"""Student CRUD, face enrollment, consent recording, and the DPDP 'right to erasure' endpoint."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..face.engine import embed_single_face
from ..models import FaceEmbedding, Student, User
from ..schemas import ConsentRequest, StudentCreate, StudentOut, StudentUpdate
from ..security import audit, get_current_user, require_admin

router = APIRouter(prefix="/students", tags=["students"])


def _to_out(s: Student) -> StudentOut:
    return StudentOut(
        id=s.id,
        roll_no=s.roll_no,
        full_name=s.full_name,
        department=s.department,
        biometric_consent=s.biometric_consent,
        consent_recorded_at=s.consent_recorded_at,
        has_embedding=s.embedding is not None,
        created_at=s.created_at,
    )


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(Student).filter(Student.roll_no == payload.roll_no).first():
        raise HTTPException(status_code=409, detail="roll_no already exists")
    data = payload.model_dump()
    # If consent is given at creation, record who created it and when
    consent_flag = data.pop("biometric_consent", False)
    s = Student(**data, biometric_consent=consent_flag)
    if consent_flag:
        s.consent_recorded_at = datetime.now(timezone.utc)
        s.consent_recorded_by = admin.id
    db.add(s)
    db.flush()
    audit(db, "create", "student", s.id, actor_id=admin.id)
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.get("", response_model=list[StudentOut])
def list_students(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    limit: int = 200,
    offset: int = 0,
    search: str = "",
):
    q = db.query(Student)
    if search:
        like = f"%{search}%"
        q = q.filter(
            Student.full_name.ilike(like) | Student.roll_no.ilike(like)
        )
    rows = q.order_by(Student.roll_no).offset(offset).limit(limit).all()
    return [_to_out(s) for s in rows]


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return _to_out(student)


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    updates = payload.model_dump(exclude_none=True)
    # Handle consent flag changes with timestamp tracking
    if "biometric_consent" in updates:
        new_consent = updates.pop("biometric_consent")
        if new_consent != student.biometric_consent:
            student.biometric_consent = new_consent
            if new_consent:
                student.consent_recorded_at = datetime.now(timezone.utc)
                student.consent_recorded_by = admin.id
                audit(db, "consent_granted", "student", student.id, actor_id=admin.id)
            else:
                student.consent_recorded_at = None
                student.consent_recorded_by = None
                audit(db, "consent_revoked", "student", student.id, actor_id=admin.id)
    for key, val in updates.items():
        setattr(student, key, val)
    audit(db, "update", "student", student.id, actor_id=admin.id)
    db.commit()
    db.refresh(student)
    return _to_out(student)


@router.delete("/{student_id}", status_code=204)
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Full right-to-erasure: delete student record, embedding, and all attendance history."""
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    audit(db, "delete", "student", student.id, actor_id=admin.id,
          detail=f"roll_no={student.roll_no}")
    db.delete(student)
    db.commit()


@router.post("/{student_id}/consent", response_model=StudentOut)
def record_consent(
    student_id: int,
    payload: ConsentRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Explicitly record or revoke biometric consent with a named audit trail entry."""
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    student.biometric_consent = payload.granted
    if payload.granted:
        student.consent_recorded_at = datetime.now(timezone.utc)
        student.consent_recorded_by = admin.id
        audit(db, "consent_granted", "student", student.id, actor_id=admin.id)
    else:
        student.consent_recorded_at = None
        student.consent_recorded_by = None
        audit(db, "consent_revoked", "student", student.id, actor_id=admin.id)
        # Revoke consent must also delete any existing embedding
        if student.embedding:
            db.delete(student.embedding)
            audit(db, "erase_face", "student", student.id, actor_id=admin.id,
                  detail="auto-erased on consent revocation")
    db.commit()
    db.refresh(student)
    return _to_out(student)


@router.post("/{student_id}/face", response_model=StudentOut)
async def enroll_face(
    student_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Enroll or replace a student's face embedding from a single-face photo.

    The uploaded photo is NEVER stored — only the derived embedding is kept.
    """
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if not student.biometric_consent:
        raise HTTPException(
            status_code=403,
            detail="Biometric consent not recorded for this student (DPDP Act 2023).",
        )

    image_bytes = await file.read()
    try:
        vector = embed_single_face(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        del image_bytes  # do not persist the raw photo

    if student.embedding:
        student.embedding.vector = vector.tolist()
    else:
        db.add(FaceEmbedding(student_id=student.id, vector=vector.tolist()))
    audit(db, "enroll_face", "student", student.id, actor_id=admin.id)
    db.commit()
    db.refresh(student)
    return _to_out(student)


@router.delete("/{student_id}/face", status_code=204)
def delete_face(
    student_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Right to erasure: delete a student's biometric embedding."""
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if student.embedding:
        db.delete(student.embedding)
        audit(db, "erase_face", "student", student.id, actor_id=admin.id)
        db.commit()
