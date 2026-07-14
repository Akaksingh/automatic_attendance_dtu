"""Tests for course and roster management."""
from .conftest import auth_headers


def _create_course(client, token, code="CS101", name="Intro to CS"):
    return client.post("/courses", json={
        "code": code, "name": name, "department": "CSE"
    }, headers=auth_headers(token))


def _create_student(client, token, roll="R001"):
    return client.post("/students", json={
        "roll_no": roll, "full_name": "Student " + roll, "department": "CSE", "biometric_consent": False
    }, headers=auth_headers(token))


def test_create_course(client, admin_token):
    res = _create_course(client, admin_token)
    assert res.status_code == 201
    data = res.json()
    assert data["code"] == "CS101"
    assert data["enrolled_count"] == 0


def test_create_course_duplicate(client, admin_token):
    _create_course(client, admin_token)
    res = _create_course(client, admin_token)
    assert res.status_code == 409


def test_teacher_cannot_create_course(client, teacher_token):
    res = _create_course(client, teacher_token)
    assert res.status_code == 403


def test_list_courses(client, admin_token):
    _create_course(client, admin_token, code="C1", name="C1")
    _create_course(client, admin_token, code="C2", name="C2")
    res = client.get("/courses", headers=auth_headers(admin_token))
    assert res.status_code == 200
    codes = [c["code"] for c in res.json()]
    assert "C1" in codes and "C2" in codes


def test_get_course(client, admin_token):
    res = _create_course(client, admin_token, code="GC01")
    cid = res.json()["id"]
    res = client.get(f"/courses/{cid}", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["code"] == "GC01"


def test_update_course(client, admin_token):
    res = _create_course(client, admin_token, code="UPD1", name="Old Name")
    cid = res.json()["id"]
    res = client.patch(f"/courses/{cid}", json={"name": "New Name"}, headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"


def test_delete_course(client, admin_token):
    res = _create_course(client, admin_token, code="DEL1")
    cid = res.json()["id"]
    res = client.delete(f"/courses/{cid}", headers=auth_headers(admin_token))
    assert res.status_code == 204
    res = client.get(f"/courses/{cid}", headers=auth_headers(admin_token))
    assert res.status_code == 404


def test_add_to_roster(client, admin_token):
    cid = _create_course(client, admin_token, code="RST1").json()["id"]
    _create_student(client, admin_token, roll="RST_S1")
    res = client.post(f"/courses/{cid}/roster", json={"roll_nos": ["RST_S1"]}, headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert len(res.json()) == 1
    # Enrolled count should reflect the addition
    res = client.get(f"/courses/{cid}", headers=auth_headers(admin_token))
    assert res.json()["enrolled_count"] == 1


def test_add_to_roster_unknown_roll(client, admin_token):
    cid = _create_course(client, admin_token, code="RST2").json()["id"]
    res = client.post(f"/courses/{cid}/roster", json={"roll_nos": ["DOESNOTEXIST"]}, headers=auth_headers(admin_token))
    assert res.status_code == 404


def test_remove_from_roster(client, admin_token):
    cid = _create_course(client, admin_token, code="RST3").json()["id"]
    st_res = _create_student(client, admin_token, roll="RST_S3")
    sid = st_res.json()["id"]
    client.post(f"/courses/{cid}/roster", json={"roll_nos": ["RST_S3"]}, headers=auth_headers(admin_token))
    res = client.delete(f"/courses/{cid}/roster/{sid}", headers=auth_headers(admin_token))
    assert res.status_code == 204
    roster = client.get(f"/courses/{cid}/roster", headers=auth_headers(admin_token)).json()
    assert all(s["id"] != sid for s in roster)


def test_get_roster(client, admin_token):
    cid = _create_course(client, admin_token, code="RST4").json()["id"]
    _create_student(client, admin_token, roll="RST_S4A")
    _create_student(client, admin_token, roll="RST_S4B")
    client.post(f"/courses/{cid}/roster", json={"roll_nos": ["RST_S4A", "RST_S4B"]}, headers=auth_headers(admin_token))
    roster = client.get(f"/courses/{cid}/roster", headers=auth_headers(admin_token)).json()
    assert len(roster) == 2
