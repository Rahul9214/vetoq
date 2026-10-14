"""Mounted POST /runs uses the M003 path. Legacy rows stay on the old worker."""

import base64
import hashlib
import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

from vetoq.auth import principal as require_principal
from vetoq.config import Settings
from vetoq.contracts import Analysis, LegacySubmission, Proposal, TicketArguments
from vetoq.db import engine_for, execute, one, rows
from vetoq.inspection import content_digest
from vetoq.main import create_app
from vetoq.providers.base import InferenceRequest, InferenceResult
from vetoq.workflow import submit, tick

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
pytestmark = pytest.mark.integration
GOAL = "Review this support request and create one ticket."
SENTINEL = "SENTINEL_LIVE_SOURCE"


class QuietProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.sources: dict[str, str] = {}

    def analyze(self, request: InferenceRequest) -> InferenceResult:
        self.calls += 1
        self.sources = dict(request.sources)
        return InferenceResult(
            analysis=Analysis(
                findings=[],
                uncertain=False,
                summary="Synthetic inspection completed without a proposal.",
                proposal=None,
            ),
            provider="fixture",
            model="fixture/structured",
            request_id=str(uuid4()),
            elapsed_ms=1,
            prompt_version="fixture/1",
        )


class TicketProvider(QuietProvider):
    def __init__(self, target: UUID) -> None:
        super().__init__()
        self.target = target

    def analyze(self, request: InferenceRequest) -> InferenceResult:
        self.calls += 1
        self.sources = dict(request.sources)
        proposal = Proposal(
            tool="tickets.create",
            tool_version=1,
            arguments=TicketArguments(
                workspace_id=self.target,
                title="Synthetic sign-in issue",
                body="A synthetic customer cannot sign in after a password reset.",
            ),
            evidence_ids=[request.envelope.source_id],
        )
        return InferenceResult(
            analysis=Analysis(
                findings=[],
                uncertain=False,
                summary="Synthetic support issue ready for deterministic authorization.",
                proposal=proposal,
            ),
            provider="fixture",
            model="fixture/structured",
            request_id=str(uuid4()),
            elapsed_ms=1,
            prompt_version="fixture/1",
        )


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    except UnsafeTestDatabase as error:
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    database = engine_for(
        Settings(
            _env_file=None,
            environment="test",
            database_url=SecretStr(DATABASE_URL),
        )
    )
    try:
        require_disposable_engine(database)
    except UnsafeTestDatabase as error:
        database.dispose()
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL
            WHERE state IN ('QUEUED','PROPOSING','AUTHORIZING','VERIFYING','AWAITING_REVIEW')
            """,
        )
    yield database
    database.dispose()


def _workspace(database: Engine, principal: str) -> UUID:
    workspace = uuid4()
    with database.begin() as connection:
        execute(
            connection,
            "INSERT INTO workspaces(id,name) VALUES(:id,:name)",
            {"id": str(workspace), "name": "Live"},
        )
        execute(
            connection,
            """
            INSERT INTO memberships(workspace_id,principal,role)
            VALUES(:workspace,:principal,'operator')
            """,
            {"workspace": str(workspace), "principal": principal},
        )
    return workspace


def _app(actor: str) -> FastAPI:
    assert DATABASE_URL is not None
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            trusted_hosts=["testserver"],
            database_url=SecretStr(DATABASE_URL),
        )
    )
    app.dependency_overrides[require_principal] = lambda: actor
    return app


def _body(workspace: UUID, media_type: str, source: str) -> dict[str, object]:
    return {
        "workspace_id": str(workspace),
        "goal": GOAL,
        "source": source,
        "media_type": media_type,
        "confirmed": True,
    }


def _counts(database: Engine, workspace: UUID) -> tuple[int, int, int]:
    with database.connect() as connection:
        runs = connection.execute(
            text("SELECT count(*) FROM runs WHERE workspace_id=:w"),
            {"w": str(workspace)},
        ).scalar_one()
        nodes = connection.execute(
            text("SELECT count(*) FROM content_nodes WHERE workspace_id=:w"),
            {"w": str(workspace)},
        ).scalar_one()
        audits = connection.execute(
            text("SELECT count(*) FROM audit_events WHERE workspace_id=:w"),
            {"w": str(workspace)},
        ).scalar_one()
    assert isinstance(runs, int) and isinstance(nodes, int) and isinstance(audits, int)
    return runs, nodes, audits


def _one(database: Engine, statement: str, params: dict[str, Any]) -> dict[str, Any] | None:
    with database.connect() as connection:
        found = one(connection, statement, params)
    return found


def _table(database: Engine, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    with database.connect() as connection:
        return rows(connection, statement, params)


def _stop(database: Engine, run_id: str) -> None:
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL
            WHERE id=:run
            """,
            {"run": run_id},
        )


def _post(actor: str, payload: dict[str, object], key: str) -> Any:
    app = _app(actor)
    try:
        with TestClient(app) as client:
            return client.post(
                "/api/v1/runs",
                json=payload,
                headers={"Idempotency-Key": key},
            )
    finally:
        app.state.engine.dispose()


def _get(actor: str, path: str) -> tuple[int, dict[str, Any], dict[str, str]]:
    app = _app(actor)
    try:
        with TestClient(app) as client:
            response = client.get(path)
            body = response.json()
            assert isinstance(body, dict)
            return response.status_code, body, dict(response.headers)
    finally:
        app.state.engine.dispose()


def _reject(
    database: Engine,
    principal: str,
    workspace: UUID,
    payload: dict[str, object],
    code: str,
    status: int = 422,
) -> None:
    before = _counts(database, workspace)
    response = _post(principal, payload, uuid4().hex)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert SENTINEL not in response.text
    assert _counts(database, workspace) == before


@pytest.mark.parametrize(
    ("media_type", "source", "expected"),
    [
        ("text/plain", "Customer cannot sign in.", {}),
        ("text/markdown", "# Request\n\nCannot sign in.", {}),
        (
            "application/json",
            '{"b":1,"a":2}',
            {
                "json-canonical": (
                    True,
                    [{"transform": "json-canonical", "version": "1"}],
                )
            },
        ),
        (
            "text/html",
            "<p>visible words</p><script>TOKEN_SCRIPT</script>",
            {
                "html-visible-text": (
                    True,
                    [{"transform": "html-visible-text", "version": "1"}],
                ),
                "html-active-content": (
                    True,
                    [{"transform": "html-active-content", "version": "1"}],
                ),
            },
        ),
        (
            "message/rfc822",
            'Content-Type: application/json\n\n{"b":1,"a":2}\n',
            {
                "email-headers": (
                    True,
                    [{"transform": "email-headers", "version": "1"}],
                ),
                "email-part-json": (
                    True,
                    [
                        {"transform": "email-part-decode", "version": "1"},
                        {"transform": "json-canonical", "version": "1"},
                    ],
                ),
            },
        ),
    ],
)
def test_live_route_processes_each_declared_format(
    database: Engine,
    media_type: str,
    source: str,
    expected: dict[str, tuple[bool, list[dict[str, str]]]],
) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    response = _post(principal, _body(workspace, media_type, source), uuid4().hex)
    assert response.status_code == 202
    run_id = str(response.json()["id"])
    provider = QuietProvider()
    try:
        assert tick(database, provider)
        status, body, _headers = _get(principal, f"/api/v1/runs/{run_id}")
        assert status == 200
        stored = _one(
            database,
            "SELECT state,complete,failure FROM runs WHERE id=:run",
            {"run": run_id},
        )
        assert stored is not None
        assert stored["state"] == "NO_ACTION"
        assert stored["complete"] is True
        assert stored["failure"] is None
        assert body["goal_lock"]["source_digest"] == hashlib.sha256(source.encode()).hexdigest()
        original = next(
            item for item in body["sources"] if item["representation_kind"] == "original"
        )
        assert original["declared_media_type"] == media_type
        assert original["parser_id"] is None
        assert original["parser_version"] is None
        assert original["byte_size"] == len(source.encode())
        assert original["trust"] == "untrusted"
        by_transform = {edge["transform"]: edge for edge in body["edges"]}
        assert set(by_transform) == set(expected)
        for transform, (lossy, steps) in expected.items():
            assert by_transform[transform]["lossy"] is lossy
            assert by_transform[transform]["version"] == "1"
            assert by_transform[transform]["transform_steps"] == steps
            assert "edge_id" not in by_transform[transform]
            assert "step_index" not in by_transform[transform]
        nodes = _table(
            database,
            "SELECT id,content FROM content_nodes WHERE run_id=:run",
            {"run": run_id},
        )
        assert provider.calls == 1
        assert set(provider.sources) == {str(node["id"]) for node in nodes}
        for node in nodes:
            assert provider.sources[str(node["id"])] == node["content"]
        audits = _table(
            database,
            "SELECT type FROM audit_events WHERE run_id=:run",
            {"run": run_id},
        )
        assert "INSPECTION_COMPLETED" in {str(item["type"]) for item in audits}
        assert "RUN_ACCEPTED" in {str(item["type"]) for item in audits}
        hidden, outsider, _outsider_headers = _get("user_" + uuid4().hex, f"/api/v1/runs/{run_id}")
        assert hidden == 404
        assert outsider["code"] == "not_found"
        content_status, content_body, _content_headers = _get(
            "user_" + uuid4().hex,
            f"/api/v1/runs/{run_id}/content/{original['id']}",
        )
        assert content_status == 404
        assert source not in str(content_body)
    finally:
        _stop(database, run_id)


def test_live_html_content_stays_json(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    source = "<p>shown</p><script>TOKEN_SCRIPT</script>"
    response = _post(principal, _body(workspace, "text/html", source), uuid4().hex)
    assert response.status_code == 202
    run_id = str(response.json()["id"])
    try:
        status, body, _headers = _get(principal, f"/api/v1/runs/{run_id}")
        assert status == 200
        original = body["sources"][0]["id"]
        content_status, content_body, headers = _get(
            principal, f"/api/v1/runs/{run_id}/content/{original}"
        )
        assert content_status == 200
        assert content_body["content"] == source
        assert "application/json" in headers["content-type"]
        assert headers["content-type"].split(";")[0] != "text/html"
        assert headers["x-content-type-options"] == "nosniff"
        assert "no-store" in headers["cache-control"]
    finally:
        _stop(database, run_id)


def test_live_base64_edge_records_one_step(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    encoded = base64.b64encode(b"Please reset the portal password.").decode()
    source = f"Payload: {encoded}"
    response = _post(principal, _body(workspace, "text/plain", source), uuid4().hex)
    assert response.status_code == 202
    run_id = str(response.json()["id"])
    try:
        assert tick(database, QuietProvider())
        status, body, _headers = _get(principal, f"/api/v1/runs/{run_id}")
        assert status == 200
        edge = next(item for item in body["edges"] if item["transform"] == "base64")
        assert edge["version"] == "1"
        assert edge["lossy"] is False
        assert edge["transform_steps"] == [{"transform": "base64", "version": "1"}]
        child = next(
            item for item in body["sources"] if item["representation_kind"] == "decoded_text"
        )
        assert child["parser_id"] == "bounded-decoder"
        assert child["parser_version"] == "1"
        assert child["declared_media_type"] is None
    finally:
        _stop(database, run_id)


def test_live_route_reaches_action_guard(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    response = _post(
        principal,
        _body(workspace, "text/plain", "Customer cannot sign in."),
        uuid4().hex,
    )
    assert response.status_code == 202
    run_id = str(response.json()["id"])
    provider = TicketProvider(workspace)
    try:
        assert tick(database, provider)
        assert tick(database, provider)
        stored = _one(
            database,
            "SELECT state,failure FROM runs WHERE id=:run",
            {"run": run_id},
        )
        assert stored is not None
        assert stored["failure"] is None
        assert stored["state"] in {"COMPLETED", "AWAITING_REVIEW", "BLOCKED", "VERIFYING"}
        assert provider.calls == 1
    finally:
        _stop(database, run_id)


def test_same_normalized_identity_replays_and_a_new_type_conflicts(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    source = "Customer cannot sign in."
    key = uuid4().hex
    first = _post(principal, _body(workspace, "text/plain; charset=UTF-8", source), key)
    second = _post(principal, _body(workspace, "text/plain; charset=utf-8", source), key)
    changed = _post(principal, _body(workspace, "text/html", source), key)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"
    assert _counts(database, workspace)[0] == 1
    _stop(database, str(first.json()["id"]))
    status, body, _headers = _get(principal, f"/api/v1/runs/{first.json()['id']}")
    assert status == 200
    original = body["sources"][0]
    assert original["declared_media_type"] == "text/plain"
    assert original["charset"] == "utf-8"
    assert body["goal_lock"]["source_digest"] == content_digest(source)


def test_missing_media_type_and_forbidden_fields_create_nothing(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    missing = {
        "workspace_id": str(workspace),
        "goal": GOAL,
        "source": SENTINEL,
        "confirmed": True,
    }
    _reject(database, principal, workspace, missing, "invalid_input")
    for extra in (
        {"sanitized": True},
        {"source_class": "trusted"},
        {"trust": "trusted"},
        {"parser_id": "text_plain"},
        {"parser_version": "1"},
    ):
        _reject(
            database,
            principal,
            workspace,
            {**_body(workspace, "text/plain", SENTINEL), **extra},
            "invalid_input",
        )


def test_unsupported_malformed_and_over_budget_inputs_create_nothing(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    _reject(
        database,
        principal,
        workspace,
        _body(workspace, "application/pdf", SENTINEL),
        "unsupported_media_type",
    )
    _reject(
        database,
        principal,
        workspace,
        _body(workspace, "application/json", '{"a": "' + SENTINEL),
        "malformed_content",
    )
    _reject(
        database,
        principal,
        workspace,
        _body(workspace, "message/rfc822", "Content-Type: application/pdf\n\n" + SENTINEL),
        "unsupported_embedded_content",
    )
    _reject(
        database,
        principal,
        workspace,
        _body(workspace, "text/plain; charset=utf-16", SENTINEL),
        "malformed_content",
    )
    _reject(
        database,
        principal,
        workspace,
        _body(workspace, "application/json", "[" * 4000 + "0" + "]" * 4000),
        "input_limit",
    )


def test_non_member_workspace_is_not_found(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    own = _workspace(database, principal)
    other = uuid4()
    with database.begin() as connection:
        execute(
            connection,
            "INSERT INTO workspaces(id,name) VALUES(:id,:name)",
            {"id": str(other), "name": "Other"},
        )
    response = _post(principal, _body(other, "text/plain", SENTINEL), uuid4().hex)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert SENTINEL not in response.text
    assert _counts(database, other) == (0, 0, 0)
    assert _counts(database, own) == (0, 0, 0)


def test_legacy_queued_run_still_processes_with_null_metadata(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    run_id = submit(
        database,
        principal,
        LegacySubmission(
            workspace_id=workspace,
            template="support-triage/1",
            goal=GOAL,
            source="Historical paste without a declared type.",
            confirmed=True,
            sanitized=True,
        ),
        uuid4().hex,
    )
    try:
        assert tick(database, QuietProvider())
        status, body, _headers = _get(principal, f"/api/v1/runs/{run_id}")
        assert status == 200
        assert body["edges"] == []
        source = body["sources"][0]
        assert source["declared_media_type"] is None
        assert source["representation_kind"] is None
        assert source["charset"] is None
        assert source["byte_size"] is None
        assert source["parser_id"] is None
        assert source["parser_version"] is None
        stored = _one(
            database,
            "SELECT state,failure FROM runs WHERE id=:run",
            {"run": run_id},
        )
        assert stored is not None
        assert stored["state"] == "NO_ACTION"
        assert stored["failure"] is None
    finally:
        _stop(database, run_id)
