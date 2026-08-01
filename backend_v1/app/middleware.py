"""HTTP middleware for safe browser integration and lightweight auth context."""
import secrets
from collections.abc import Awaitable, Callable

import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from uuid import UUID

from .config import settings


async def authentication_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Decode a valid access cookie without rejecting public routes.

    Route dependencies remain responsible for requiring authentication and
    loading an active user from the database.
    """
    request.state.user_id = None
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else None
    token = token or request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            if payload.get("type") == "access" and payload.get("sub"):
                request.state.user_id = UUID(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            pass
    return await call_next(request)


async def csrf_protection(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Protect cookie-authenticated browser mutations with a double-submit token.

    Bearer-token clients are not subject to this check because they do not send
    credentials automatically cross-site. Public authentication endpoints are
    excluded; logout is protected when an authenticated cookie is present.
    """
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    public = request.url.path in {"/api/auth/login", "/api/auth/register", "/api/auth/refresh"}
    has_cookie_auth = bool(request.cookies.get("access_token") or request.cookies.get("refresh_token"))
    if unsafe and has_cookie_auth and not public:
        expected = request.cookies.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            return JSONResponse(status_code=403, content={"detail": "CSRF token is missing or invalid"})
    return await call_next(request)


async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    return response
