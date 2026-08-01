"""Cookie-based JWT authentication and self-service profile routes."""
import secrets
from datetime import UTC, datetime, timedelta

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AuditLog, RefreshToken, User, UserRole
from ..schemas import AuthResponse, LoginRequest, ProfileUpdate, StudentRegistration, UserOut
from ..security import CurrentUser, decode_token, hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
DbSession = Annotated[Session, Depends(get_db)]


def _set_auth_cookies(response: Response, user: User, db: Session) -> None:
    access, _ = make_token(
        user=user,
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_minutes),
    )
    refresh, refresh_jti = make_token(
        user=user,
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_days),
    )
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_days)
    db.add(RefreshToken(jti=refresh_jti, user_id=user.id, expires_at=expires_at))
    db.commit()
    cookie_options = {"httponly": True, "secure": settings.auth_cookie_secure, "samesite": "lax", "path": "/api"}
    response.set_cookie("access_token", access, max_age=settings.jwt_access_token_minutes * 60, **cookie_options)
    response.set_cookie("refresh_token", refresh, max_age=settings.jwt_refresh_token_days * 86400, **cookie_options)
    # The React app is served from `/`, so the readable double-submit cookie
    # must be available there. Authentication cookies remain scoped to `/api`.
    response.set_cookie("csrf_token", secrets.token_urlsafe(32), max_age=settings.jwt_refresh_token_days * 86400, httponly=False, secure=settings.auth_cookie_secure, samesite="lax", path="/")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/api")
    response.delete_cookie("refresh_token", path="/api")
    response.delete_cookie("csrf_token", path="/")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_student(payload: StudentRegistration, db: DbSession) -> User:
    """Public registration intentionally creates student accounts only."""
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    from ..models import Student
    if db.query(Student).filter(Student.roll_no == payload.roll_no).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Roll number is already registered")
    user = User(email=email, full_name=payload.full_name, password_hash=hash_password(payload.password), role=UserRole.student)
    db.add(user)
    db.flush()
    db.add(Student(user_id=user.id, roll_no=payload.roll_no, full_name=payload.full_name))
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> dict[str, User]:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    _set_auth_cookies(response, user, db)
    return {"user": user}


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: Request, response: Response, db: DbSession) -> dict[str, User]:
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")
    payload = decode_token(token, "refresh")
    stored = db.query(RefreshToken).filter(RefreshToken.jti == payload["jti"]).first()
    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is no longer valid")
    from uuid import UUID
    user = db.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active or stored.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    stored.revoked_at = now  # rotate on every use
    db.commit()
    _set_auth_cookies(response, user, db)
    return {"user": user}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> Response:
    token = request.cookies.get("refresh_token")
    if token:
        try:
            payload = decode_token(token, "refresh")
            stored = db.query(RefreshToken).filter(RefreshToken.jti == payload["jti"]).first()
            if stored and stored.revoked_at is None:
                stored.revoked_at = datetime.now(UTC)
                db.commit()
        except HTTPException:
            pass
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> User:
    if user.role == UserRole.student and payload.full_name is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students can only update their image and password")
    if user.role == UserRole.student and payload.profile_image_url is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a verified profile photo instead")
    if payload.new_password:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        user.password_hash = hash_password(payload.new_password)
        now = datetime.now(UTC)
        db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update({RefreshToken.revoked_at: now}, synchronize_session=False)
        db.add(AuditLog(actor_id=user.id, action="user.password_changed", entity_type="user", entity_id=user.id))
    if payload.full_name is not None and user.role != UserRole.student:
        user.full_name = payload.full_name
    if payload.profile_image_url is not None:
        user.profile_image_url = payload.profile_image_url
    db.commit()
    db.refresh(user)
    return user
