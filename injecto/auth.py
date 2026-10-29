#!/usr/bin/env python3
"""Service-to-service authentication for the Injecto API.

Injecto clones arbitrary git repos and processes templates, so it must only be
callable by the OpenPrime backend. A shared service token (sent as the
``X-Service-Token`` header) is validated on every mutating endpoint.

Fails closed (OP-260): without ``SERVICE_TOKEN`` the API refuses to start, and
any request that still arrives is refused. The only way to run without a token
is the explicit local-development flag ``INJECTO_AUTH_DISABLED=true``.
NetworkPolicy remains a second, independent layer.
"""

import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

from .logs import logger, yellow


def flag_is_set(value: Optional[str]) -> bool:
    """Parse a boolean setting the way TRIM_DECORATOR_ATTRS is parsed."""
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


SERVICE_TOKEN = os.getenv("SERVICE_TOKEN")
AUTH_DISABLED = flag_is_set(os.getenv("INJECTO_AUTH_DISABLED"))


def check_auth_configured():
    """Refuse to start without a token unless auth is explicitly disabled.

    Called from the API lifespan, so a missing secret is a pod that fails to
    start, visible to the operator, rather than one that silently serves
    every caller in the cluster.
    """
    if SERVICE_TOKEN:
        return
    if not AUTH_DISABLED:
        raise RuntimeError(
            "SERVICE_TOKEN is not set. Configure it, or set INJECTO_AUTH_DISABLED=true "
            "for local development only."
        )
    logger.warning(
        yellow("INJECTO_AUTH_DISABLED is set and SERVICE_TOKEN is not — request authentication is DISABLED (dev only)")
    )


def token_is_authorized(provided: Optional[str], expected: Optional[str], auth_disabled: bool = False) -> bool:
    """Return True if the request is authorized.

    A configured token must match in constant time. Without one, only the
    explicit dev flag authorizes; a missing or empty token never means "allow".
    """
    if not expected:
        return auth_disabled
    return bool(provided) and secrets.compare_digest(provided, expected)


async def require_service_token(x_service_token: Optional[str] = Header(default=None)):
    """FastAPI dependency that rejects requests lacking a valid service token."""
    if not token_is_authorized(x_service_token, SERVICE_TOKEN, AUTH_DISABLED):
        raise HTTPException(status_code=401, detail="Invalid or missing service token")
