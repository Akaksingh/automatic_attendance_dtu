"""Tests for attendance reports and CSV export."""
from .conftest import auth_headers


def _build_finalized_session(db):
    """Create a finalized session with one present student directly in DB."""
    from app.models import (
        User, Role, Course, Student, Enrollment, ClassSession,
        SessionState, Attendance, AttendanceStatus, AttendanceMethod
    )
    from app.security import hash_password

    teacher = User(email="rpt_t@test.com", full_name="T", password_hash=hash_password("pass1234"), role=Role.teacher)
    db.add(teacher)
    db.flush()

    course = Course(code="RPT101", name="Report Course", department="CSE")
    db.add(course)
    db.flush()

    student = Student(roll_no="RPT_S1", full_name="Report Student", department="CSE", biometric_consent=True)
    db.add(student)
    db.flush()

    db.add(Enrollment(course_id=course.id, student_id=student.id))
    db.flush()

    session = ClassSession(
        course_id=course.id, teacher_id=teacher.id,
        state=SessionState.finalized, faces_detected=1
    )
    db.add(session)
    db.flush()

    db.add(Attendance(
        session_id=session.id, student_id=student.id,
        status=AttendanceStatus.present, method=AttendanceMethod.auto, confidence=0.92
    ))
    db.commit()
    return course, student, session, teacher


def test_course_attendance_json(client, admin_token, db):
    course, student, session, _ = _build_finalized_session(db)
    res = client.get(f"/reports/courses/{course.id}/attendance", headers=auth_headers(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["total_sessions"] == 1
    assert len(data["students"]) == 1
    s = data["students"][0]
    assert s["roll_no"] == "RPT_S1"
    assert s["attended"] == 1
    assert s["percentage"] == 100.0


def test_course_attendance_csv(client, admin_token, db):
    course, student, session, _ = _build_finalized_session(db)
    res = client.get(f"/reports/courses/{course.id}/attendance.csv", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    lines = res.text.strip().split("\n")
    assert "Roll No" in lines[0]
    assert "RPT_S1" in res.text


def test_session_attendance_csv(client, db):
    course, student, session, teacher = _build_finalized_session(db)
    # Get a new teacher (the one from _build), log in
    res = client.post("/auth/login", data={"username": "rpt_t@test.com", "password": "pass1234"})
    tok = res.json()["access_token"]
    res = client.get(f"/reports/sessions/{session.id}/attendance.csv", headers=auth_headers(tok))
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "RPT_S1" in res.text
    assert "present" in res.text


def test_course_not_found(client, admin_token):
    res = client.get("/reports/courses/99999/attendance", headers=auth_headers(admin_token))
    assert res.status_code == 404


def test_report_requires_auth(client):
    res = client.get("/reports/courses/1/attendance")
    assert res.status_code == 401
