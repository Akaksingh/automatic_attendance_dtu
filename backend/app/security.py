"""Authentication, password hashing, RBAC dependencies, and audit helper."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuditLog, Role, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "role": user.role.value, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise cred_exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise cred_exc
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def audit(
    db: Session,
    action: str,
    entity: str,
    entity_id: int | None = None,
    actor_id: int | None = None,
    detail: str = "",
) -> None:
    """Append an audit record. Caller is responsible for the surrounding commit."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
        )
    )
