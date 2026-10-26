"""Admin authentication for control endpoints (broadcast start/pause/stop, event injection).

Secure default: outside development and test, admin endpoints refuse every request
until SOKOKALI_ADMIN_TOKEN is set. In development, an unset token leaves them open
so the local dashboard works without setup (a warning is logged at startup).
"""

import secrets

from fastapi import HTTPException, Request, status

from app.core.config import Settings


def admin_token_required(settings: Settings) -> bool:
    return settings.admin_token is not None or settings.environment not in ("development", "test")


def token_is_valid(settings: Settings, provided: str | None) -> bool:
    expected = settings.admin_token.get_secret_value() if settings.admin_token else ""
    if not expected:
        return not admin_token_required(settings)
    return provided is not None and secrets.compare_digest(provided.encode(), expected.encode())


def require_admin(request: Request) -> None:
    settings: Settings = request.app.state.container.settings
    if settings.admin_token is None and admin_token_required(settings):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Admin access is disabled: set SOKOKALI_ADMIN_TOKEN")
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if not token_is_valid(settings, token if scheme.lower() == "bearer" else None):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Admin token required", headers={"WWW-Authenticate": "Bearer"}
        )
