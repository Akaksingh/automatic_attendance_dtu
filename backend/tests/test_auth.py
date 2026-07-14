"""Tests for authentication and user management endpoints."""
from .conftest import auth_headers


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_login_success(client, admin_token):
    assert admin_token is not None
    assert len(admin_token) > 10


def test_login_wrong_password(client, db):
    from app.models import User, Role
    from app.security import hash_password
    user = User(email="u@test.com", full_name="U", password_hash=hash_password("correct"), role=Role.teacher, is_active=True)
    db.add(user)
    db.commit()
    res = client.post("/auth/login", data={"username": "u@test.com", "password": "wrong"})
    assert res.status_code == 401


def test_login_inactive_user(client, db):
    from app.models import User, Role
    from app.security import hash_password
    user = User(email="inactive@test.com", full_name="I", password_hash=hash_password("pass1234"), role=Role.teacher, is_active=False)
    db.add(user)
    db.commit()
    res = client.post("/auth/login", data={"username": "inactive@test.com", "password": "pass1234"})
    assert res.status_code == 403


def test_me(client, admin_token):
    res = client.get("/auth/me", headers=auth_headers(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "admin@test.com"
    assert data["role"] == "admin"


def test_me_unauthenticated(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_create_user_admin(client, admin_token):
    res = client.post("/auth/users", json={
        "email": "newteacher@test.com",
        "full_name": "New Teacher",
        "password": "password123",
        "role": "teacher",
    }, headers=auth_headers(admin_token))
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "newteacher@test.com"
    assert data["role"] == "teacher"


def test_create_user_duplicate(client, admin_token):
    payload = {"email": "dup@test.com", "full_name": "D", "password": "password123", "role": "teacher"}
    client.post("/auth/users", json=payload, headers=auth_headers(admin_token))
    res = client.post("/auth/users", json=payload, headers=auth_headers(admin_token))
    assert res.status_code == 409


def test_teacher_cannot_create_user(client, teacher_token):
    res = client.post("/auth/users", json={
        "email": "x@test.com", "full_name": "X", "password": "password123", "role": "teacher"
    }, headers=auth_headers(teacher_token))
    assert res.status_code == 403


def test_list_users(client, admin_token):
    res = client.get("/auth/users", headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_update_user(client, admin_token, db):
    # Create a user to update
    res = client.post("/auth/users", json={
        "email": "upd@test.com", "full_name": "Before", "password": "password123", "role": "teacher"
    }, headers=auth_headers(admin_token))
    user_id = res.json()["id"]
    res = client.patch(f"/auth/users/{user_id}", json={"full_name": "After"}, headers=auth_headers(admin_token))
    assert res.status_code == 200
    assert res.json()["full_name"] == "After"


def test_deactivate_user(client, admin_token):
    res = client.post("/auth/users", json={
        "email": "bye@test.com", "full_name": "Bye", "password": "password123", "role": "teacher"
    }, headers=auth_headers(admin_token))
    user_id = res.json()["id"]
    res = client.delete(f"/auth/users/{user_id}", headers=auth_headers(admin_token))
    assert res.status_code == 204
    # Verify can no longer log in
    res = client.post("/auth/login", data={"username": "bye@test.com", "password": "password123"})
    assert res.status_code == 403
