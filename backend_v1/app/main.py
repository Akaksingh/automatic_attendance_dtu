"""FastAPI entrypoint for the enhanced attendance backend."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .database import engine
from .middleware import authentication_context, csrf_protection, security_headers
from .redis_client import redis_client
from .routes import admin, auth, groups, imports, sessions, students
from .models import User, UserRole
from .security import hash_password
from .config import settings

app = FastAPI(title="ClassLens API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.middleware("http")(security_headers)
app.middleware("http")(csrf_protection)
app.middleware("http")(authentication_context)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(groups.router)
app.include_router(students.router)
app.include_router(sessions.router)
app.include_router(imports.router)


@app.on_event("startup")
def startup() -> None:
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        from .database import SessionLocal
        with SessionLocal() as db:
            email = settings.bootstrap_admin_email.lower()
            if db.query(User).filter(User.email == email).first() is None:
                db.add(User(email=email, full_name="System Administrator", password_hash=hash_password(settings.bootstrap_admin_password), role=UserRole.admin))
                db.commit()


@app.get("/api/hello")
def hello() -> dict[str, str]:
    return {"message": "Hello, World!"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/dependencies")
def dependency_health() -> dict[str, str]:
    """Check direct connectivity to the configured PostgreSQL and Redis services."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    redis_client.ping()
    return {"database": "ok", "redis": "ok"}


_repo_frontend = Path(__file__).resolve().parents[2] / "frontend_v1" / "dist"
_image_frontend = Path("/app/frontend")
FRONTEND_DIST = _image_frontend if _image_frontend.is_dir() else _repo_frontend

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        """Serve the built React SPA, preserving client-side routes on refresh."""
        requested_file = FRONTEND_DIST / path
        if path and requested_file.is_file():
            return FileResponse(requested_file)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def development_hello() -> dict[str, str]:
        """Keep the original smoke-test endpoint before the frontend is built."""
        return {"message": "Hello, World!"}
