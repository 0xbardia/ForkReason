"""FastAPI application.

Route modules stay thin: validate, call a domain function, shape a response.
No business logic lives here (constitution VI.23).
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .errors import api_error_handler, http_exception_handler
from .logging_setup import configure_logging

log = logging.getLogger("forkreason.api")

# Correlation id for the lifetime of one request (spec FR-I-009).
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="ForkReason API",
        version="1.0.0",
        description="Software lineage and provenance, verified by GenLayer consensus.",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        """Attach a request id and log the outcome of every request."""
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception(
                "request failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            log.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
        request_id_ctx.reset(token)
        return response

    # Registration order matters. Starlette dispatches on the *exact* class of
    # the raised exception via ExceptionMiddleware's lookup, walking the MRO and
    # picking the first registered match. Registering the Starlette base class
    # would shadow FastAPI's subclass, and an unmatched route's 404 is raised as
    # a Starlette HTTPException. So: base first, subclass second.
    from fastapi import HTTPException as FastAPIHTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from .errors import InputValidationError
    from .repos.github_url import InvalidRepositoryInput

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    app.add_exception_handler(InvalidRepositoryInput, api_error_handler)
    app.add_exception_handler(InputValidationError, api_error_handler)
    app.add_exception_handler(Exception, api_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        """Field-level validation errors, without echoing input values."""
        fields = sorted({str(e.get("loc", ["body"])[-1]) for e in exc.errors()})
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "Check the highlighted fields and try again.",
                    "fields": fields[:12],
                }
            },
        )

    # --- routes ----------------------------------------------------------
    from .routes import analyses, cases, chain, health, repositories, search

    app.include_router(health.router)
    app.include_router(repositories.router, prefix="/api/v1")
    app.include_router(analyses.router, prefix="/api/v1")
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(search.chain_read_router, prefix="/api/v1")
    app.include_router(chain.router, prefix="/api/v1")

    @app.get("/api/v1/config", tags=["meta"])
    async def public_config():
        """Frontend configuration. Contains no secrets, by construction."""
        return {
            "version": app.version,
            "network": settings.genlayer_network,
            "contract_address": settings.genlayer_contract_address,
            "analysis_limits": {
                "max_repo_mb": settings.analysis_max_repo_mb,
                "max_files": settings.analysis_max_files,
                "max_commits": settings.analysis_max_commits,
            },
        }

    return app


app = create_app()