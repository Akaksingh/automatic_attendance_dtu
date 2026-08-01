"""Small regression tests for contracts that are easy to break during refactors."""
from fastapi.routing import APIRoute

from app.main import app


def _route(path: str, method: str) -> APIRoute:
    return next(
        route for route in app.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


def test_delete_session_is_bodyless_204() -> None:
    route = _route("/api/sessions/{session_id}", "DELETE")
    assert route.status_code == 204
    assert route.response_model is None


def test_cleanup_tasks_are_registered() -> None:
    from app.celery_app import celery_app

    assert "app.tasks.cleanup_expired_session_photos" in celery_app.tasks
    assert "app.tasks.cleanup_expired_refresh_tokens" in celery_app.tasks
