"""Short transactions and explicit SQL; no connection is held over model calls."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from vetoq.config import Settings


def engine_for(settings: Settings) -> Engine:
    if settings.database_url is None:
        raise RuntimeError("database_not_configured")
    url = (
        settings.database_url.get_secret_value()
        .replace("postgresql://", "postgresql+psycopg://", 1)
        .replace("postgres://", "postgresql+psycopg://", 1)
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=5000 -c lock_timeout=3000",
        },
    )


def one(c: Connection, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    row = c.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def rows(c: Connection, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(r) for r in c.execute(text(sql), params or {}).mappings()]


def execute(c: Connection, sql: str, params: Mapping[str, Any] | None = None) -> None:
    c.execute(text(sql), params or {})
