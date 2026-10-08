"""Validated server configuration. Never expose credentials in errors or repr."""

from pathlib import Path
from typing import Literal, Self
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VETOQ_",
        env_file=ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "[::1]"])
    database_url: SecretStr | None = Field(default=None, repr=False)

    @field_validator("trusted_hosts")
    @classmethod
    def validate_hosts(cls, hosts: list[str]) -> list[str]:
        if not hosts or any(
            not host
            or host != host.strip()
            or "*" in host
            or "/" in host
            or "://" in host
            or any(char.isspace() for char in host)
            for host in hosts
        ):
            raise ValueError("trusted_hosts must contain explicit hostnames without wildcards")
        return hosts

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        try:
            parsed = urlsplit(value.get_secret_value())
            port = parsed.port
        except ValueError:
            raise ValueError("database_url must be a valid PostgreSQL URL") from None
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.hostname
            or not parsed.username
            or not parsed.path.strip("/")
            or parsed.fragment
            or (port is not None and port <= 0)
        ):
            raise ValueError("database_url must identify a PostgreSQL host, user, and database")
        return value

    @model_validator(mode="after")
    def validate_production(self) -> Self:
        if self.environment != "production":
            return self
        if self.database_url is None:
            raise ValueError("production requires database_url")
        if "trusted_hosts" not in self.model_fields_set:
            raise ValueError("production requires explicitly configured trusted_hosts")
        parsed = urlsplit(self.database_url.get_secret_value())
        if not parsed.password or parsed.password in {
            "password",
            "postgres",
            "changeme",
            "replace-with-local-password",
        }:
            raise ValueError("production requires a non-placeholder database password")
        if parse_qs(parsed.query).get("sslmode") != ["verify-full"]:
            raise ValueError("production database_url requires sslmode=verify-full")
        return self
