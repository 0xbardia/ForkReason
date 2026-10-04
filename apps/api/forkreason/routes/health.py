"""Health and readiness.

Liveness answers "is this process alive". Readiness answers "can it serve
traffic", which for ForkReason means the database is reachable. Both are cheap
and neither leaks internal detail.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from ..db import get_engine, ping
from ..jobs import queue as q
from ..db import session_scope

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness. No dependency checks, so it cannot fail spuriously."""
    return {"status": "ok", "service": "forkreason-api", "version": "1.0.0"}


@router.get("/ready")
async def ready() -> dict:
    """Readiness. Reports whether the service can actually accept work."""
    database_ok = ping()
    payload: dict = {"status": "ready" if database_ok else "degraded", "database": database_ok}
    if database_ok:
        try:
            with session_scope() as session:
                payload["queue"] = q.queue_depth(session)
        except Exception as exc:  # noqa: BLE001 - readiness must not raise
            log.warning("queue depth unavailable", extra={"error": str(exc)[:160]})
            payload["queue"] = None
    return payload


@router.get("/api/v1/health/deep")
async def deep_health() -> dict:
    """Dependency detail for operators. Includes the engine version, no secrets."""
    payload: dict = {"database": False, "database_version": None, "queue": None}
    if ping():
        payload["database"] = True
        try:
            with get_engine().connect() as conn:
                payload["database_version"] = conn.execute(text("SHOW server_version")).scalar()
        except Exception as exc:  # noqa: BLE001
            log.warning("version probe failed", extra={"error": str(exc)[:160]})
    return payload