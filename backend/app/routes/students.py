"""Student CRUD, face enrollment, and the DPDP 'right to erasure' endpoint."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..face.engine import embed_single_face
from ..models import FaceEmbedding, Student, User
from ..schemas import StudentCreate, StudentOut
from ..security import audit, get_current_user, require_admin

router = APIRouter(prefix="/students", tags=["students"])


def _to_out(s: Student) -> StudentOut:
    return StudentOut(
        id=s.id,
        roll_no=s.roll_no,
        full_name=s.full_name,
        department=s.department,
        biometric_consent=s.biometric_consent,
        has_embedding=s.embedding is not None,
    )


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(Student).filter(Student.roll_no == payload.roll_no).first():
        raise HTTPException(status_code=409, detail="roll_no already exists")
    s = Student(**payload.model_dump())
    db.add(s)
    db.flush()
    audit(db, "create", "student", s.id, actor_id=admin.id)
    db.commit()
    return _to_out(s)


@router.get("", response_model=list[StudentOut])
def list_students(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
):
    rows = db.query(Student).order_by(Student.id).offset(offset).limit(limit).all()
    return [_to_out(s) for s in rows]


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
