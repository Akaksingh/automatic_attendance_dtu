"""Courses and roster (enrollment) management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Enrollment, Student, User
from ..schemas import CourseCreate, CourseDetail, CourseOut, CourseUpdate, EnrollRequest, StudentOut
from ..security import audit, get_current_user, require_admin

router = APIRouter(prefix="/courses", tags=["courses"])


def _course_detail(course: Course, db: Session) -> CourseDetail:
    count = db.query(Enrollment).filter(Enrollment.course_id == course.id).count()
    return CourseDetail(
        id=course.id,
        code=course.code,
        name=course.name,
        department=course.department,
        enrolled_count=count,
    )


@router.post("", response_model=CourseDetail, status_code=201)
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
    db.refresh(c)
    return _course_detail(c, db)


@router.get("", response_model=list[CourseDetail])
def list_courses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    courses = db.query(Course).order_by(Course.code).all()
    return [_course_detail(c, db) for c in courses]


@router.get("/{course_id}", response_model=CourseDetail)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_detail(course, db)


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(
    course_id: int,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    for key, val in payload.model_dump(exclude_none=True).items():
        setattr(course, key, val)
    audit(db, "update", "course", course.id, actor_id=admin.id)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    audit(db, "delete", "course", course.id, actor_id=admin.id,
          detail=f"code={course.code}")
    db.delete(course)
    db.commit()


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
    added = 0
    for s in students:
        if s.id not in existing:
            db.add(Enrollment(course_id=course_id, student_id=s.id))
            added += 1
    audit(db, "roster_add", "course", course_id, actor_id=admin.id, detail=f"n={added}")
    db.commit()
    return get_roster(course_id, db, admin)  # type: ignore[arg-type]


@router.delete("/{course_id}/roster/{student_id}", status_code=204)
def remove_from_roster(
    course_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Remove one student from a course roster."""
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.course_id == course_id, Enrollment.student_id == student_id)
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    audit(db, "roster_remove", "course", course_id, actor_id=admin.id,
          detail=f"student_id={student_id}")
    db.delete(enrollment)
    db.commit()


@router.get("/{course_id}/roster", response_model=list[StudentOut])
def get_roster(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
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
            consent_recorded_at=s.consent_recorded_at,
            has_embedding=s.embedding is not None,
            created_at=s.created_at,
        )
        for s in rows
    ]
