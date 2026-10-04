"""Structured logging.

JSON in production so logs are machine-parseable and correlated; a readable
format in development. Never logs secrets: only identifiers, codes, and
bounded durations.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# Attributes that must never reach a log line, even accidentally.
_REDACT_KEYS = {
    "token", "github_token", "authorization", "password", "secret", "private_key",
    "privatekey", "api_key", "apikey", "database_url", "cookie", "session",
}


class RedactingFilter(logging.Filter):
    """Replaces sensitive values with a marker before they are serialized."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key.lower() in _REDACT_KEYS:
                record.__dict__[key] = "[redacted]"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Structured extras attached via `extra={...}`.
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_KEYS or key.startswith("_"):
                continue
            if key.lower() in _REDACT_KEYS:
                payload[key] = "[redacted]"
            elif isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            else:
                payload[key] = str(value)[:200]
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)[:2000]
        return json.dumps(payload, ensure_ascii=False)


_LOG_RECORD_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message", "asctime", "taskName",
}


def configure_logging(level: str = "INFO", *, json_output: bool | None = None) -> None:
    """Configure root logging once, idempotently."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for existing in list(root.handlers):
        root.removeHandler(existing)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())

    if json_output is None:
        json_output = _running_in_container()

    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-5s %(name)s %(message)s")
        )

    root.addHandler(handler)

    # These libraries are noisy at INFO and add nothing here.
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _running_in_container() -> bool:
    import os

    return os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST") is not None