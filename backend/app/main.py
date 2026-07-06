"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .models import Role, User
from .retention import start_retention_loop
from .routes import auth, courses, sessions, students
from .security import hash_password

logger = logging.getLogger("attendance")
logging.basicConfig(level=logging.INFO)

FRONTEND_DIR = "/app/frontend"


def _bootstrap_admin() -> None:
    """Create the first admin from env vars if no admin exists yet."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == Role.admin).first():
            return
        db.add(
            User(
                email=settings.bootstrap_admin_email,
                full_name="Administrator",
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=Role.admin,
            )
        )
        db.commit()
        logger.info("Bootstrapped admin user %s", settings.bootstrap_admin_email)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _bootstrap_admin()
    start_retention_loop()
    yield


app = FastAPI(title="Attendance DTU", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(students.router)
app.include_router(courses.router)
app.include_router(sessions.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


# Serve the minimal teacher web app if it's present in the image.
import os  # noqa: E402

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
