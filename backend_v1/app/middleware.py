"""HTTP middleware for safe browser integration and lightweight auth context."""
from collections.abc import Awaitable, Callable

import jwt
from fastapi import Request, Response
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


async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    return response
