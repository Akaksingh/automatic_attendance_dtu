"""Tests for student CRUD, consent, and enrollment."""
from .conftest import auth_headers


def _create_student(client, token, roll="2021CSE001", name="Alice", consent=False):
    return client.post("/students", json={
        "roll_no": roll,
        "full_name": name,
        "department": "CSE",
        "biometric_consent": consent,
    }, headers=auth_headers(token))


def test_create_student(client, admin_token):
    res = _create_student(client, admin_token)
    assert res.status_code == 201
    data = res.json()
    assert data["roll_no"] == "2021CSE001"
    assert data["biometric_consent"] is False
    assert data["has_embedding"] is False


def test_create_student_duplicate_roll(client, admin_token):
    _create_student(client, admin_token)
    res = _create_student(client, admin_token)
    assert res.status_code == 409


def test_teacher_cannot_create_student(client, teacher_token):
    res = _create_student(client, teacher_token)
    assert res.status_code == 403


def test_list_students(client, admin_token):
    _create_student(client, admin_token, roll="S001", name="Alice")
    _create_student(client, admin_token, roll="S002", name="Bob")
    res = client.get("/students", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_list_students_search(client, admin_token):
    _create_student(client, admin_token, roll="SRCH001", name="Searchable")
    res = client.get("/students?search=Searchable", headers=auth_headers(admin_token))
    assert res.status_code == 200
    names = [s["full_name"] for s in res.json()]
    assert "Searchable" in names


def test_get_student(client, admin_token):
    res = _create_student(client, admin_token, roll="G001", name="Get Me")
    sid = res.json()["id"]
    res = client.get(f"/students/{sid}", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["full_name"] == "Get Me"


def test_update_student(client, admin_token):
    res = _create_student(client, admin_token, roll="U001", name="Before")
    sid = res.json()["id"]
    res = client.patch(f"/students/{sid}", json={"full_name": "After"}, headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["full_name"] == "After"


def test_delete_student(client, admin_token):
    res = _create_student(client, admin_token, roll="DEL001")
    sid = res.json()["id"]
    res = client.delete(f"/students/{sid}", headers=auth_headers(admin_token))
    assert res.status_code == 204
    res = client.get(f"/students/{sid}", headers=auth_headers(admin_token))
    assert res.status_code == 404


def test_consent_record(client, admin_token):
    res = _create_student(client, admin_token, roll="CON001", consent=False)
    sid = res.json()["id"]
    assert res.json()["biometric_consent"] is False
    # Grant consent
    res = client.post(f"/students/{sid}/consent", json={"granted": True}, headers=auth_headers(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["biometric_consent"] is True
    assert data["consent_recorded_at"] is not None


def test_consent_created_with_flag(client, admin_token):
    """When a student is created with biometric_consent=True, consent_recorded_at must be set."""
    res = _create_student(client, admin_token, roll="CONF001", consent=True)
    assert res.status_code == 201
    data = res.json()
    assert data["biometric_consent"] is True
    assert data["consent_recorded_at"] is not None


def test_consent_revoke(client, admin_token):
    res = _create_student(client, admin_token, roll="REV001", consent=True)
    sid = res.json()["id"]
    res = client.post(f"/students/{sid}/consent", json={"granted": False}, headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["biometric_consent"] is False
    assert res.json()["consent_recorded_at"] is None
