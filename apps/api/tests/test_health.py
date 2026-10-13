from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vetoq.auth import principal
from vetoq.config import Settings
from vetoq.main import SCHEMA_REVISION, create_app, database_available


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


def test_product_routes_exist_but_require_identity(client: TestClient) -> None:
    for path in ["/", "/docs", "/openapi.json", "/tickets"]:
        assert client.get(path).status_code == 404
    response = client.get("/api/v1/runs")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_framework_errors_use_the_json_error_contract(client: TestClient) -> None:
    for method, path, status, code in [
        ("GET", "/tickets", 404, "not_found"),
        ("DELETE", "/api/v1/me", 405, "method_not_allowed"),
        ("GET", "/api/v1/me", 401, "authentication_required"),
    ]:
        response = client.request(method, path)
        assert response.status_code == status
        assert response.headers["content-type"] == "application/json"
        body = response.json()
        assert body["code"] == code
        assert set(body) == {"code", "message", "correlation_id", "retryable"}


def test_correlation_id_is_preserved_only_when_well_formed(client: TestClient) -> None:
    supplied = "4f6c1d2e-7a8b-4c9d-8e0f-1a2b3c4d5e6f"
    response = client.get("/api/v1/me", headers={"x-request-id": supplied})
    assert response.json()["correlation_id"] == supplied
    assert response.headers["x-request-id"] == supplied
    forged = client.get("/api/v1/me", headers={"x-request-id": "<script>alert(1)</script>"})
    assert forged.json()["correlation_id"] != "<script>alert(1)</script>"
    assert len(forged.json()["correlation_id"]) == 36


def test_product_routes_fail_closed_when_database_is_not_configured() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        trusted_hosts=["testserver"],
    )
    app = create_app(settings)
    app.dependency_overrides[principal] = lambda: "user_operator"
    with TestClient(app) as client:
        response = client.get("/api/v1/me")
    assert response.status_code == 503
    assert response.json()["code"] == "database_not_configured"


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
        cursor.fetchone.return_value = (SCHEMA_REVISION,)
        assert database_available("fixture-dsn") is True
        connect.assert_called_once_with(
            "fixture-dsn", connect_timeout=2, autocommit=True, options="-c statement_timeout=2000"
        )
        cursor.execute.assert_called_once_with(
            "SELECT version_num FROM alembic_version WHERE version_num=%s",
            (SCHEMA_REVISION,),
        )


def test_connection_failure_is_not_readiness() -> None:
    with patch(
        "vetoq.main.psycopg.connect", side_effect=psycopg.OperationalError("private detail")
    ):
        assert database_available("fixture-dsn") is False
