import base64
import binascii
import os
import secrets

from fastapi import Request
from starlette.responses import Response


ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def validate_auth_config() -> None:
    """Fail fast if admin authentication is not configured."""
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise RuntimeError(
            "ADMIN_USERNAME and ADMIN_PASSWORD must be set in the environment."
        )


def _unauthorized() -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Appointment Bot"'},
    )


def _credentials_are_valid(request: Request) -> bool:
    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Basic "):
        return False

    encoded = authorization.removeprefix("Basic ").strip()

    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False

    return (
        secrets.compare_digest(username, ADMIN_USERNAME or "")
        and secrets.compare_digest(password, ADMIN_PASSWORD or "")
    )


async def admin_auth_middleware(request: Request, call_next):
    """
    Protect the UI and management API with HTTP Basic Auth.

    Mailgun's inbound webhook and static assets stay public.
    """
    path = request.url.path

    if path == "/email/incoming" or path.startswith("/static/"):
        return await call_next(request)

    if not _credentials_are_valid(request):
        return _unauthorized()

    return await call_next(request)
