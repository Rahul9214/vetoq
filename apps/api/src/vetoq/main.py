"""VETOQ application factory."""

import logging
import re
from collections.abc import Callable
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from vetoq.auth import correlation
from vetoq.config import Settings
from vetoq.db import engine_for
from vetoq.routes import router

logger = logging.getLogger("vetoq.api")
ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
STATUS_CODES = {404: "not_found", 405: "method_not_allowed"}
SCHEMA_REVISION = "0002_worker_claim"


def request_correlation(value: str | None) -> str:
    try:
        return str(UUID(value)) if value and len(value) == 36 else str(uuid4())
    except ValueError:
        return str(uuid4())


class HealthResponse(BaseModel):
    status: Literal["ok", "ready", "not_ready"]
    reason: Literal["database_not_configured", "database_unavailable"] | None = None


def database_available(dsn: str) -> bool:
    """Require PostgreSQL and the exact migrated Module 002 schema."""
    try:
        with psycopg.connect(
            dsn, connect_timeout=2, autocommit=True, options="-c statement_timeout=2000"
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT version_num FROM alembic_version WHERE version_num=%s",
                    (SCHEMA_REVISION,),
                )
                return cursor.fetchone() == (SCHEMA_REVISION,)
    except psycopg.Error:
        return False


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probe: Callable[[str], bool] = database_available,
) -> FastAPI:
    config = settings if settings is not None else Settings()
    app = FastAPI(
        title="VETOQ API",
        version="0.2.0",
        debug=False,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = config
    app.state.engine = engine_for(config) if config.database_url is not None else None
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.trusted_hosts)
    app.include_router(router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.correlation_id = request_correlation(request.headers.get("x-request-id"))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def safe_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        detail = str(error.detail)
        code = detail if ERROR_CODE.match(detail) else STATUS_CODES.get(error.status_code)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "code": code or "request_failed",
                "message": "Request could not be completed.",
                "correlation_id": correlation(request),
                "retryable": error.status_code == 503,
            },
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "invalid_input",
                "message": "Request input is invalid.",
                "correlation_id": correlation(request),
                "retryable": False,
            },
        )

    @app.exception_handler(Exception)
    async def safe_internal_error(request: Request, error: Exception) -> JSONResponse:
        correlation_id = correlation(request)
        logger.error(
            "Unhandled request failure method=%s path=%s correlation_id=%s",
            request.method,
            request.url.path,
            correlation_id,
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Request could not be completed.",
                "correlation_id": correlation_id,
                "retryable": False,
            },
        )

    @app.get("/health/live", response_model=HealthResponse, response_model_exclude_none=True)
    def liveness() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/health/ready", response_model=HealthResponse, response_model_exclude_none=True)
    def readiness(response: Response) -> HealthResponse:
        if config.database_url is None:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(status="not_ready", reason="database_not_configured")
        if not readiness_probe(config.database_url.get_secret_value()):
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(status="not_ready", reason="database_unavailable")
        return HealthResponse(status="ready")

    return app
