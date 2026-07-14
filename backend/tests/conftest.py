"""pytest fixtures: in-process SQLite test DB + FastAPI test client.

The app must see test-friendly settings BEFORE any app module is imported:
`app.database` builds its engine at import time from DATABASE_URL, and the
FastAPI lifespan (run by TestClient) calls init_db() against that engine.
"""
import json
import os

# ── Environment must be set before importing anything from `app` ────────────
os.environ["DATABASE_URL"] = "sqlite://"          # throwaway in-memory DB for the app engine
os.environ["JWT_SECRET"] = "test-secret-not-for-production"
os.environ["RETENTION_ENABLED"] = "0"             # no background purge thread in tests

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String, TypeDecorator, create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import FaceEmbedding, Role, User
from app.security import hash_password


class FakeVector(TypeDecorator):
    """SQLite stand-in for pgvector's Vector: stores the vector as JSON text."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


# Patch the Vector column once, before any create_all runs (including the one
# in the app lifespan). SQLite has no pgvector.
FaceEmbedding.__table__.c.vector.type = FakeVector()

# StaticPool: every connection (test thread AND TestClient's worker thread)
# shares the single in-memory database.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Fresh schema per test on the shared in-memory engine."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Test client wired to the test DB."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(client, db):
    """Create an admin user and return a Bearer token."""
    user = User(
        email="admin@test.com",
        full_name="Test Admin",
        password_hash=hash_password("adminpass1"),
        role=Role.admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    res = client.post("/auth/login", data={"username": "admin@test.com", "password": "adminpass1"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
def teacher_token(client, db):
    """Create a teacher user and return a Bearer token."""
    user = User(
        email="teacher@test.com",
        full_name="Test Teacher",
        password_hash=hash_password("teacherpass1"),
        role=Role.teacher,
        is_active=True,
    )
    db.add(user)
    db.commit()
    res = client.post("/auth/login", data={"username": "teacher@test.com", "password": "teacherpass1"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
