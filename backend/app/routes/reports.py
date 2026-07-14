"""Attendance reports and CSV export.

Endpoints:
  GET /reports/courses/{course_id}/attendance
      ?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
      → JSON: per-student summary (sessions, attended, %)

  GET /reports/courses/{course_id}/attendance.csv
      → CSV download: Roll No, Name, Sessions, Attended, %

  GET /reports/sessions/{session_id}/attendance.csv
      → CSV for one session: Roll No, Name, Present/Absent, Method, Confidence
"""
import csv
import io
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Attendance,
    AttendanceStatus,
    ClassSession,
    Course,
    Enrollment,
    SessionState,
    Student,
    User,
)
from ..schemas import CourseAttendanceReport, StudentAttendanceSummary
from ..security import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])


def _date_to_dt_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)


def _date_to_dt_end(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def _build_course_report(
    course: Course,
    db: Session,
    from_date: Optional[date],
    to_date: Optional[date],
) -> CourseAttendanceReport:
    """Compute per-student attendance summary for a course over an optional date range."""
    # Determine finalised sessions in range
    q = (
        db.query(ClassSession)
        .filter(
            ClassSession.course_id == course.id,
            ClassSession.state == SessionState.finalized,
        )
    )
    if from_date:
        q = q.filter(ClassSession.started_at >= _date_to_dt_start(from_date))
    if to_date:
        q = q.filter(ClassSession.started_at <= _date_to_dt_end(to_date))
    sessions = q.order_by(ClassSession.started_at).all()
    session_ids = [s.id for s in sessions]
    total_sessions = len(session_ids)

    # All enrolled students
    enrolled = (
        db.query(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.course_id == course.id)
        .order_by(Student.roll_no)
        .all()
    )

    summaries: list[StudentAttendanceSummary] = []
    for student in enrolled:
        if session_ids:
            attended = (
                db.query(Attendance)
                .filter(
                    Attendance.student_id == student.id,
                    Attendance.session_id.in_(session_ids),
                    Attendance.status == AttendanceStatus.present,
                )
                .count()
            )
        else:
            attended = 0
        pct = (attended / total_sessions * 100) if total_sessions > 0 else 0.0
        summaries.append(
            StudentAttendanceSummary(
                student_id=student.id,
                roll_no=student.roll_no,
                full_name=student.full_name,
                total_sessions=total_sessions,
                attended=attended,
                percentage=round(pct, 1),
            )
        )

    return CourseAttendanceReport(
        course_id=course.id,
        course_code=course.code,
        course_name=course.name,
        from_date=_date_to_dt_start(from_date) if from_date else None,
        to_date=_date_to_dt_end(to_date) if to_date else None,
        total_sessions=total_sessions,
        students=summaries,
    )


@router.get("/courses/{course_id}/attendance", response_model=CourseAttendanceReport)
def course_attendance_json(
    course_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _build_course_report(course, db, from_date, to_date)


@router.get("/courses/{course_id}/attendance.csv")
def course_attendance_csv(
    course_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Stream a CSV of per-student attendance for a course."""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    report = _build_course_report(course, db, from_date, to_date)

    def _iter():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Roll No", "Full Name", "Total Sessions", "Attended", "Attendance %"
        ])
        yield buf.getvalue()
        for s in report.students:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                s.roll_no, s.full_name, s.total_sessions, s.attended, f"{s.percentage:.1f}"
            ])
            yield buf.getvalue()

    filename = f"attendance_{course.code}.csv"
    return StreamingResponse(
        _iter(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/attendance.csv")
def session_attendance_csv(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream a CSV for a single finalized session."""
    session = db.get(ClassSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from ..models import Role
    if user.role != Role.admin and session.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    rows = (
        db.query(Attendance, Student)
        .join(Student, Student.id == Attendance.student_id)
        .filter(Attendance.session_id == session_id)
        .order_by(Student.roll_no)
        .all()
    )

    course = db.get(Course, session.course_id)
    course_code = course.code if course else str(session.course_id)

    def _iter():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Roll No", "Full Name", "Status", "Method", "Confidence (%)"
        ])
        yield buf.getvalue()
        for att, st in rows:
            buf = io.StringIO()
            writer = csv.writer(buf)
            conf = f"{att.confidence * 100:.1f}" if att.confidence is not None else ""
            writer.writerow([
                st.roll_no, st.full_name, att.status.value, att.method.value, conf
            ])
            yield buf.getvalue()

    date_str = session.started_at.strftime("%Y%m%d")
    filename = f"session_{course_code}_{date_str}.csv"
    return StreamingResponse(
        _iter(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
