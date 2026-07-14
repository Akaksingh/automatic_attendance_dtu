"""Tests for the class session lifecycle (create → upload → review → finalize)."""
from .conftest import auth_headers


def _setup_course_and_student(client, admin_token):
    """Helper: create a course, a student with consent, add to roster."""
    course = client.post("/courses", json={"code": "SES101", "name": "Test Course", "department": "CSE"},
                         headers=auth_headers(admin_token)).json()
    student = client.post("/students", json={
        "roll_no": "SES_S1", "full_name": "Session Student", "department": "CSE", "biometric_consent": True
    }, headers=auth_headers(admin_token)).json()
    client.post(f"/courses/{course['id']}/roster", json={"roll_nos": ["SES_S1"]},
                headers=auth_headers(admin_token))
    return course, student


def test_create_session(client, admin_token):
    course, _ = _setup_course_and_student(client, admin_token)
    res = client.post("/sessions", json={"course_id": course["id"]}, headers=auth_headers(admin_token))
    assert res.status_code == 201
    data = res.json()
    assert data["state"] == "created"
    assert data["course_id"] == course["id"]


def test_create_session_unknown_course(client, admin_token):
    res = client.post("/sessions", json={"course_id": 99999}, headers=auth_headers(admin_token))
    assert res.status_code == 404


def test_get_session(client, admin_token):
    course, _ = _setup_course_and_student(client, admin_token)
    sess = client.post("/sessions", json={"course_id": course["id"]},
                       headers=auth_headers(admin_token)).json()
    res = client.get(f"/sessions/{sess['id']}", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["id"] == sess["id"]


def test_teacher_cannot_access_other_session(client, admin_token, teacher_token):
    """A teacher should get 403 trying to access another teacher's session."""
    course, _ = _setup_course_and_student(client, admin_token)
    sess = client.post("/sessions", json={"course_id": course["id"]},
                       headers=auth_headers(admin_token)).json()
    res = client.get(f"/sessions/{sess['id']}", headers=auth_headers(teacher_token))
    assert res.status_code == 403


def test_apply_corrections_and_finalize(client, admin_token, db):
    """Simulate worker having written review state, then teacher finalises."""
    from app.models import (
        ClassSession, SessionState, Attendance, AttendanceStatus,
        AttendanceMethod, Enrollment, Student, Course
    )
    # Build directly in DB to avoid the worker
    course = db.query(Course).filter(Course.code == "SES101").first()
    if not course:
        course = Course(code="SES101F", name="Fin Course", department="CSE")
        db.add(course)
        db.flush()
    student = db.query(Student).filter(Student.roll_no == "SES_S1F").first()
    if not student:
        student = Student(roll_no="SES_S1F", full_name="Fin Student", department="CSE", biometric_consent=True)
        db.add(student)
        db.flush()
    db.add(Enrollment(course_id=course.id, student_id=student.id))
    db.flush()

    from app.models import User, Role
    from app.security import hash_password
    teacher = User(email="t_fin@test.com", full_name="T", password_hash=hash_password("pass1234"), role=Role.teacher)
    db.add(teacher)
    db.flush()

    session = ClassSession(
        course_id=course.id, teacher_id=teacher.id, state=SessionState.review, faces_detected=1
    )
    db.add(session)
    db.flush()
    db.add(Attendance(
        session_id=session.id, student_id=student.id,
        status=AttendanceStatus.absent, method=AttendanceMethod.auto
    ))
    db.commit()

    # Log in as teacher
    res = client.post("/auth/login", data={"username": "t_fin@test.com", "password": "pass1234"})
    tok = res.json()["access_token"]

    # Apply corrections: mark absent student as present
    res = client.post(f"/sessions/{session.id}/corrections", json={
        "corrections": [{"student_id": student.id, "status": "present"}]
    }, headers=auth_headers(tok))
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "finalized"
    rec = next(r for r in data["records"] if r["student_id"] == student.id)
    assert rec["status"] == "present"
    assert rec["method"] == "manual"


def test_corrections_on_wrong_state(client, admin_token):
    course, _ = _setup_course_and_student(client, admin_token)
    sess = client.post("/sessions", json={"course_id": course["id"]},
                       headers=auth_headers(admin_token)).json()
    # State is "created" — should reject corrections
    res = client.post(f"/sessions/{sess['id']}/corrections", json={"corrections": []},
                      headers=auth_headers(admin_token))
    assert res.status_code == 409


def test_list_sessions_admin_sees_all(client, admin_token):
    """Admin should see all sessions in the list endpoint."""
    course, _ = _setup_course_and_student(client, admin_token)
    client.post("/sessions", json={"course_id": course["id"]}, headers=auth_headers(admin_token))

    res = client.get("/sessions", headers=auth_headers(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Verify shape
    first = data[0]
    assert "id" in first
    assert "course_code" in first
    assert "course_name" in first
    assert "state" in first
    assert "teacher_name" in first


def test_list_sessions_teacher_sees_only_own(client, admin_token, teacher_token, db):
    """A teacher should only see their own sessions, not the admin's."""

    # Create a course
    course_res = client.post("/courses", json={"code": "LIST101", "name": "List Test", "department": "CSE"},
                             headers=auth_headers(admin_token))
    course_id = course_res.json()["id"]

    # Admin creates a session
    admin_sess = client.post("/sessions", json={"course_id": course_id},
                             headers=auth_headers(admin_token)).json()

    # Teacher creates their own session
    teacher_sess = client.post("/sessions", json={"course_id": course_id},
                               headers=auth_headers(teacher_token)).json()

    # Teacher list — should only contain teacher's session
    res = client.get("/sessions", headers=auth_headers(teacher_token))
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()]
    assert teacher_sess["id"] in ids
    assert admin_sess["id"] not in ids


def test_list_sessions_state_filter(client, admin_token):
    """State filter should narrow results correctly."""
    course, _ = _setup_course_and_student(client, admin_token)
    client.post("/sessions", json={"course_id": course["id"]}, headers=auth_headers(admin_token))

    # Filter by 'created' — should contain the session we just made
    res = client.get("/sessions?state=created", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert all(s["state"] == "created" for s in res.json())

    # Filter by 'finalized' — none should exist for this fresh course
    res2 = client.get(f"/sessions?state=finalized&course_id={course['id']}",
                      headers=auth_headers(admin_token))
    assert res2.status_code == 200
    assert res2.json() == []

