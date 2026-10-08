"""Application factory exposing only liveness and PostgreSQL readiness."""

from collections.abc import Callable
from typing import Literal

import psycopg
from fastapi import FastAPI, Response, status
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from vetoq.config import Settings


class HealthResponse(BaseModel):
    status: Literal["ok", "ready", "not_ready"]
    reason: Literal["database_not_configured", "database_unavailable"] | None = None


def database_available(dsn: str) -> bool:
    """Use a bounded read-only probe; do not create schema or mutate data."""
    try:
        with psycopg.connect(
            dsn, connect_timeout=2, autocommit=True, options="-c statement_timeout=2000"
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
    except psycopg.Error:
        return False


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probe: Callable[[str], bool] = database_available,
) -> FastAPI:
    config = settings if settings is not None else Settings()
    app = FastAPI(
        title="VETOQ Foundation API",
        version="0.1.0",
        debug=False,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.trusted_hosts)

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
