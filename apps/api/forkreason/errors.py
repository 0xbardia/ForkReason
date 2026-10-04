"""Stable error codes and the API error envelope.

Users see a code and a sentence; operators see the detail in the logs. Stack
traces and absolute paths never cross the API boundary (spec FR-I-008,
FR-M-001 "error leakage").
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .repos.github_url import InvalidRepositoryInput

log = logging.getLogger(__name__)


class InputValidationError(ValueError):
    """Repository input rejected before any network call.

    A dedicated type so it can be mapped to 400 without the generic handler
    treating it as a server fault (which would return 500 and hide the reason).
    """

    def __init__(self, reason: str, code: str = "invalid_repository_input") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


class ApiError(HTTPException):
    """An error with a stable, branchable code and a user-safe message."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
        self.code = code
        self.message = message


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(400, code, message)


def not_found(code: str, message: str) -> ApiError:
    return ApiError(404, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def too_many(code: str, message: str) -> ApiError:
    return ApiError(429, code, message)


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Single place where an exception becomes a response body."""
    if isinstance(exc, ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    if isinstance(exc, InputValidationError) or getattr(exc, "is_input_validation", False):
        # Input validation is a user error, not a server fault. The reason is
        # written for a human; the raw input is not echoed back.
        return JSONResponse(
            status_code=400,
            content={"error": {"code": exc.code, "message": exc.reason}},
        )

    log.exception("unhandled API error", extra={"path": str(_request.url.path)})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong on ForkReason's side. The error was logged.",
            }
        },
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
            headers=getattr(exc, "headers", None),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
        headers=getattr(exc, "headers", None),
    )