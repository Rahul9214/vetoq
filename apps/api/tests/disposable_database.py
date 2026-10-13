"""Refuse destructive test setup unless the target is a disposable test database."""

import os
from urllib.parse import urlsplit

from sqlalchemy import Engine, text

from vetoq.config import Settings

SUFFIX = "_test"


class UnsafeTestDatabase(RuntimeError):
    pass


def target(url: str) -> tuple[str, int, str]:
    parsed = urlsplit(url)
    return (parsed.hostname or "", parsed.port or 5432, parsed.path.strip("/"))


def development_urls() -> list[str]:
    """The normal database from the shell environment and from the local .env files."""
    configured = Settings().database_url
    candidates = [
        os.environ.get("VETOQ_DATABASE_URL"),
        configured and configured.get_secret_value(),
    ]
    return [url for url in candidates if url]


def require_disposable_url(url: str, development: list[str]) -> None:
    host, _, name = target(url)
    if not host or not name.endswith(SUFFIX) or name == SUFFIX:
        raise UnsafeTestDatabase(f"test database name must end with {SUFFIX}")
    if any(target(url) == target(other) for other in development):
        raise UnsafeTestDatabase("test database must differ from VETOQ_DATABASE_URL")


def require_disposable_engine(engine: Engine) -> None:
    with engine.connect() as connection:
        name = connection.execute(text("SELECT current_database()")).scalar_one()
    if not isinstance(name, str) or not name.endswith(SUFFIX):
        raise UnsafeTestDatabase(f"connected database does not end with {SUFFIX}")
