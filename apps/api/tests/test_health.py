from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vetoq.config import Settings
from vetoq.main import create_app, database_available


def test_liveness_is_independent_of_database(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_requires_actual_dependency_configuration(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "database_not_configured"}


def test_untrusted_host_is_rejected(client: TestClient) -> None:
    assert client.get("/health/live", headers={"host": "attacker.invalid"}).status_code == 400


def test_only_health_routes_exist(client: TestClient) -> None:
    for path in ["/", "/docs", "/openapi.json", "/api/v1/runs", "/tickets"]:
        assert client.get(path).status_code == 404


def test_readiness_uses_probe_without_exposing_credentials() -> None:
    dsn = "postgresql://test:fixture-only@localhost/vetoq"
    settings = Settings(
        _env_file=None,
        environment="test",
        trusted_hosts=["testserver"],
        database_url=SecretStr(dsn),
    )
    probe = MagicMock(return_value=False)
    client = TestClient(create_app(settings, readiness_probe=probe))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "database_unavailable"}
    assert "fixture-only" not in response.text
    probe.assert_called_once_with(dsn)
    probe.return_value = True
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_probe_uses_a_bounded_read_only_query() -> None:
    with patch("vetoq.main.psycopg.connect") as connect:
        cursor = (
            connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        )
        cursor.fetchone.return_value = (1,)
        assert database_available("fixture-dsn") is True
        connect.assert_called_once_with(
            "fixture-dsn", connect_timeout=2, autocommit=True, options="-c statement_timeout=2000"
        )
        cursor.execute.assert_called_once_with("SELECT 1")


def test_connection_failure_is_not_readiness() -> None:
    with patch(
        "vetoq.main.psycopg.connect", side_effect=psycopg.OperationalError("private detail")
    ):
        assert database_available("fixture-dsn") is False
