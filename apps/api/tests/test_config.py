import pytest
from pydantic import SecretStr, ValidationError

from vetoq.config import Settings


def test_development_can_start_without_database() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.database_url is None


@pytest.mark.parametrize(
    "hosts", [[], ["*"], ["*.example.com"], ["https://example.com"], [" bad "]]
)
def test_unsafe_hosts_are_rejected(hosts: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_hosts=hosts)


@pytest.mark.parametrize(
    "dsn", ["sqlite:///local.db", "postgresql:///db", "postgresql://user@host"]
)
def test_invalid_database_configuration_is_rejected(dsn: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=SecretStr(dsn))


def test_missing_production_database_fails() -> None:
    with pytest.raises(ValidationError, match="production requires database_url"):
        Settings(_env_file=None, environment="production", trusted_hosts=["api.example.com"])


def test_missing_explicit_production_hosts_fails() -> None:
    with pytest.raises(ValidationError, match="explicitly configured trusted_hosts"):
        Settings(
            _env_file=None,
            environment="production",
            database_url=SecretStr(
                "postgresql://user:fixture-only@db.example.com/vetoq?sslmode=verify-full"
            ),
        )


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://user:password@db.example.com/vetoq?sslmode=verify-full",
        "postgresql://user@db.example.com/vetoq?sslmode=verify-full",
        "postgresql://user:fixture-only@db.example.com/vetoq",
        "postgresql://user:fixture-only@db.example.com/vetoq?sslmode=require",
    ],
)
def test_unsafe_production_database_fails(dsn: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            trusted_hosts=["api.example.com"],
            database_url=SecretStr(dsn),
        )


def test_explicit_production_settings_and_secret_redaction() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        trusted_hosts=["api.example.com"],
        database_url=SecretStr(
            "postgresql://user:fixture-only@db.example.com/vetoq?sslmode=verify-full"
        ),
    )
    assert "fixture-only" not in repr(settings)
    assert "fixture-only" not in settings.model_dump_json()


def test_environment_variables_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VETOQ_ENVIRONMENT", "production")
    monkeypatch.setenv("VETOQ_TRUSTED_HOSTS", '["api.example.com"]')
    monkeypatch.setenv(
        "VETOQ_DATABASE_URL",
        "postgresql://user:fixture-only@db.example.com/vetoq?sslmode=verify-full",
    )
    assert Settings(_env_file=None).environment == "production"


def test_invalid_secret_is_not_in_rendered_error() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=SecretStr("invalid-fixture-secret"))
    assert "invalid-fixture-secret" not in str(error.value)
