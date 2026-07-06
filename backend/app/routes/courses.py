"""Courses and roster (enrollment) management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Enrollment, Student, User
from ..schemas import CourseCreate, CourseOut, EnrollRequest, StudentOut
from ..security import audit, get_current_user, require_admin

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=CourseOut, status_code=201)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(Course).filter(Course.code == payload.code).first():
        raise HTTPException(status_code=409, detail="Course code already exists")
    c = Course(**payload.model_dump())
    db.add(c)
    db.flush()
    audit(db, "create", "course", c.id, actor_id=admin.id)
    db.commit()
    return c


@router.get("", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Course).order_by(Course.code).all()


@router.post("/{course_id}/roster", response_model=list[StudentOut])
def add_to_roster(
    course_id: int,
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Enroll students (by roll_no) into a course roster. Idempotent."""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    students = db.query(Student).filter(Student.roll_no.in_(payload.roll_nos)).all()
    found = {s.roll_no for s in students}
    missing = set(payload.roll_nos) - found
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown roll_nos: {sorted(missing)}")

    existing = {
        e.student_id
        for e in db.query(Enrollment).filter(Enrollment.course_id == course_id).all()
    }
    for s in students:
        if s.id not in existing:
            db.add(Enrollment(course_id=course_id, student_id=s.id))
    audit(db, "roster_add", "course", course_id, actor_id=admin.id, detail=f"n={len(students)}")
    db.commit()
    return get_roster(course_id, db)  # type: ignore[arg-type]


@router.get("/{course_id}/roster", response_model=list[StudentOut])
def get_roster(course_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    rows = (
        db.query(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.course_id == course_id)
        .order_by(Student.roll_no)
        .all()
    )
    return [
        StudentOut(
            id=s.id,
            roll_no=s.roll_no,
            full_name=s.full_name,
            department=s.department,
            biometric_consent=s.biometric_consent,
            has_embedding=s.embedding is not None,
        )
        for s in rows
    ]
