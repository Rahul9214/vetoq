"""Declared-format acceptance. The live POST /runs route uses this path."""

import os
from collections.abc import Iterator
from threading import Barrier, Thread
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
from vetoq.contracts import LegacySubmission
from vetoq.db import engine_for, execute, one
from vetoq.ingestion.registry import new_registry
from vetoq.inspection import content_digest
from vetoq.main import create_app
from vetoq.workflow import (
    DomainError,
    accept_declared_submission,
    load_declared_submission,
    submit,
)

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
pytestmark = pytest.mark.integration

GOAL = "Review this support request and create one ticket."
SENTINEL = "SENTINEL_SOURCE_TEXT"


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
            {"id": str(workspace), "name": "Declared"},
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


def _payload(workspace: UUID, media_type: str, source: str) -> dict[str, object]:
    return {
        "workspace_id": str(workspace),
        "template": "support-triage/1",
        "goal": GOAL,
        "source": source,
        "media_type": media_type,
        "confirmed": True,
    }


def _accept(database: Engine, principal: str, payload: dict[str, object], key: str) -> str:
    return accept_declared_submission(database, principal, load_declared_submission(payload), key)


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


def _counts(database: Engine, workspace: UUID) -> tuple[int, int]:
    with database.connect() as connection:
        runs = connection.execute(
            text("SELECT count(*) FROM runs WHERE workspace_id=:w"),
            {"w": str(workspace)},
        ).scalar_one()
        nodes = connection.execute(
            text("SELECT count(*) FROM content_nodes WHERE workspace_id=:w"),
            {"w": str(workspace)},
        ).scalar_one()
    assert isinstance(runs, int)
    assert isinstance(nodes, int)
    return runs, nodes


def _refuse(database: Engine, principal: str, payload: dict[str, object], code: str) -> None:
    before = _counts(database, UUID(str(payload["workspace_id"])))
    with pytest.raises(DomainError, match=code) as caught:
        _accept(database, principal, payload, "rejected-" + uuid4().hex)
    assert caught.value.code == code
    assert SENTINEL not in str(caught.value)
    assert _counts(database, UUID(str(payload["workspace_id"]))) == before


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


def _get(actor: str, path: str) -> tuple[int, dict[str, Any]]:
    app = _app(actor)
    with TestClient(app) as client:
        response = client.get(path)
    app.state.engine.dispose()
    body: dict[str, Any] = response.json()
    return response.status_code, body


@pytest.mark.parametrize(
    ("media_type", "source", "stored_type"),
    [
        ("text/plain; charset=utf-8", "hello", "text/plain"),
        ("application/json", '{"b":1,"a":2}', "application/json"),
        ("text/markdown", "# title\n", "text/markdown"),
        ("text/html", "<p>shown</p>", "text/html"),
        ("message/rfc822", "From: a@b.invalid\n\nhello\n", "message/rfc822"),
    ],
)
def test_each_declared_type_stores_one_original(
    database: Engine, media_type: str, source: str, stored_type: str
) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    run_id = _accept(database, principal, _payload(workspace, media_type, source), uuid4().hex)
    try:
        with database.connect() as connection:
            run = one(
                connection,
                "SELECT state,complete,envelope FROM runs WHERE id=:id",
                {"id": run_id},
            )
            node = one(
                connection,
                """
                SELECT content,trust,declared_media_type,representation_kind,charset,
                       byte_size,parser_id,parser_version,digest
                FROM content_nodes WHERE run_id=:run
                """,
                {"run": run_id},
            )
            edges = connection.execute(
                text("SELECT count(*) FROM content_edges WHERE run_id=:run"),
                {"run": run_id},
            ).scalar_one()
            actions = connection.execute(
                text("SELECT count(*) FROM actions WHERE run_id=:run"),
                {"run": run_id},
            ).scalar_one()
        assert run is not None and node is not None
        assert run["state"] == "QUEUED"
        assert run["complete"] is False
        assert run["envelope"]["source_digest"] == content_digest(source)
        assert run["envelope"]["source_digest"] == node["digest"]
        assert "declared_media_type" not in run["envelope"]
        assert node["content"] == source
        assert node["trust"] == "untrusted"
        assert node["declared_media_type"] == stored_type
        assert node["representation_kind"] == "original"
        assert node["parser_id"] is None
        assert node["parser_version"] is None
        assert node["byte_size"] == len(source.encode("utf-8"))
        assert edges == 0
        assert actions == 0
        if media_type.startswith("text/plain"):
            assert node["charset"] == "utf-8"
        else:
            assert node["charset"] is None
    finally:
        _stop(database, run_id)


def test_pre_accept_failures_write_nothing(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    plain = _payload(workspace, "text/plain", f"kept {SENTINEL}")
    _refuse(
        database,
        principal,
        {**plain, "media_type": "application/pdf"},
        "unsupported_media_type",
    )
    _refuse(
        database,
        principal,
        {**plain, "media_type": "text/plain; charset=latin-1"},
        "malformed_content",
    )
    _refuse(
        database,
        principal,
        _payload(workspace, "application/json", "{" + SENTINEL),
        "malformed_content",
    )
    pdf = (
        "Content-Type: multipart/mixed; boundary=b\n\n"
        "--b\nContent-Type: text/plain\n\nok\n"
        f"--b\nContent-Type: application/pdf\n\n{SENTINEL}\n"
        "--b--\n"
    )
    _refuse(
        database,
        principal,
        _payload(workspace, "message/rfc822", pdf),
        "unsupported_embedded_content",
    )
    _refuse(
        database,
        principal,
        _payload(workspace, "text/html", "<b>" * 2001),
        "input_limit",
    )
    parts = ["Content-Type: multipart/mixed; boundary=b\n\n"]
    for index in range(32):
        parts.append(f"--b\nContent-Type: text/plain\n\npart-{index}\n")
    parts.append("--b--\n")
    _refuse(
        database,
        principal,
        _payload(workspace, "message/rfc822", "".join(parts)),
        "input_limit",
    )
    assert _counts(database, workspace) == (0, 0)


def test_m003_shape_rejects_security_fields_without_echoing_source() -> None:
    payload = {
        "workspace_id": str(uuid4()),
        "template": "support-triage/1",
        "goal": GOAL,
        "source": SENTINEL,
        "confirmed": True,
    }
    for extra in (
        {"sanitized": True},
        {"source_class": "email"},
        {"trust": "trusted"},
        {"parser_id": "text_plain"},
        {"parser_version": "1"},
        {"channel": "api_submission"},
        {"principal": "user_override"},
    ):
        with pytest.raises(DomainError, match="invalid_input") as caught:
            load_declared_submission({**payload, "media_type": "text/plain", **extra})
        assert caught.value.status == 422
        assert SENTINEL not in str(caught.value)
    with pytest.raises(DomainError, match="invalid_input") as missing:
        load_declared_submission(payload)
    assert missing.value.status == 422
    assert SENTINEL not in str(missing.value)


def test_media_type_spelling_shares_identity_and_type_does_not(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    source = "same text"
    key = uuid4().hex
    first = _accept(database, principal, _payload(workspace, "TEXT/PLAIN", source), key)
    other: str | None = None
    try:
        again = _accept(
            database,
            principal,
            _payload(workspace, "text/plain; charset=UTF-8", source),
            key,
        )
        assert again == first
        with pytest.raises(DomainError, match="idempotency_conflict") as caught:
            _accept(database, principal, _payload(workspace, "text/html", source), key)
        assert caught.value.status == 409
        assert SENTINEL not in str(caught.value)
        other = _accept(
            database,
            principal,
            _payload(workspace, "text/html", source),
            uuid4().hex,
        )
        with database.connect() as connection:
            digests = (
                connection.execute(
                    text("SELECT submission_digest,envelope FROM runs WHERE id IN (:a,:b)"),
                    {"a": first, "b": other},
                )
                .mappings()
                .all()
            )
        submission_digests = {row["submission_digest"] for row in digests}
        source_digests = {row["envelope"]["source_digest"] for row in digests}
        assert len(submission_digests) == 2
        assert source_digests == {content_digest(source)}
        assert _counts(database, workspace) == (2, 2)
    finally:
        _stop(database, first)
        if other is not None:
            _stop(database, other)


def test_rejected_request_does_not_consume_the_idempotency_key(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    key = uuid4().hex
    with pytest.raises(DomainError, match="malformed_content"):
        _accept(database, principal, _payload(workspace, "application/json", "{"), key)
    assert _counts(database, workspace) == (0, 0)
    run_id = _accept(database, principal, _payload(workspace, "application/json", '{"ok":1}'), key)
    try:
        assert _counts(database, workspace) == (1, 1)
    finally:
        _stop(database, run_id)


def test_broken_registry_is_internal_and_writes_nothing(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    with pytest.raises(DomainError, match="internal_error") as caught:
        accept_declared_submission(
            database,
            principal,
            load_declared_submission(_payload(workspace, "text/plain", "hello")),
            uuid4().hex,
            registry=new_registry(),
        )
    assert caught.value.status == 500
    assert caught.value.code != "unsupported_media_type"
    assert _counts(database, workspace) == (0, 0)


def test_concurrent_same_identity_creates_one_run(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    key = uuid4().hex
    payload = _payload(workspace, "text/plain", "concurrent")
    start = Barrier(2)
    found: list[str] = []
    errors: list[BaseException] = []

    def once() -> None:
        start.wait(timeout=5)
        try:
            found.append(_accept(database, principal, payload, key))
        except BaseException as error:
            errors.append(error)

    threads = [Thread(target=once), Thread(target=once)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    try:
        assert errors == []
        assert found[0] == found[1]
        assert _counts(database, workspace) == (1, 1)
    finally:
        if found:
            _stop(database, found[0])


def test_live_route_rejects_template_and_sanitized(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    app = _app(principal)
    with TestClient(app) as client:
        templated = client.post(
            "/api/v1/runs",
            json={
                "workspace_id": str(workspace),
                "template": "support-triage/1",
                "goal": GOAL,
                "source": SENTINEL,
                "media_type": "text/plain",
                "confirmed": True,
            },
            headers={"Idempotency-Key": uuid4().hex},
        )
        sanitized = client.post(
            "/api/v1/runs",
            json={
                "workspace_id": str(workspace),
                "goal": GOAL,
                "source": SENTINEL,
                "media_type": "text/plain",
                "confirmed": True,
                "sanitized": True,
            },
            headers={"Idempotency-Key": uuid4().hex},
        )
    app.state.engine.dispose()
    assert templated.status_code == 422
    assert templated.json()["code"] == "invalid_input"
    assert sanitized.status_code == 422
    assert sanitized.json()["code"] == "invalid_input"
    assert SENTINEL not in templated.text
    assert SENTINEL not in sanitized.text
    assert _counts(database, workspace) == (0, 0)


def test_staged_read_model_and_existing_edge(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    run_id = _accept(
        database,
        principal,
        _payload(workspace, "Text/HTML", "<p>shown</p>"),
        uuid4().hex,
    )
    try:
        with database.connect() as connection:
            original = one(
                connection, "SELECT id FROM content_nodes WHERE run_id=:run", {"run": run_id}
            )
            audit = one(
                connection,
                "SELECT detail FROM audit_events WHERE run_id=:run AND type='RUN_ACCEPTED'",
                {"run": run_id},
            )
        assert original is not None and audit is not None
        assert audit["detail"]["channel"] == "user_paste"
        assert audit["detail"]["declared_media_type"] == "text/html"
        assert audit["detail"]["parser_id"] is None
        assert "source" not in audit["detail"]
        assert "<p>shown</p>" not in str(audit["detail"])
        child = str(uuid4())
        with database.begin() as connection:
            execute(
                connection,
                """
                INSERT INTO content_nodes(
                    id,workspace_id,run_id,origin,supplier,digest,content,
                    trust,complete,expires_at
                ) VALUES(
                    :id,:w,:r,'derived','bounded-decoder/1',:d,'child','untrusted',true,
                    now()+interval '1 hour'
                )
                """,
                {
                    "id": child,
                    "w": str(workspace),
                    "r": run_id,
                    "d": content_digest("child"),
                },
            )
            execute(
                connection,
                """
                INSERT INTO content_edges(
                    id,workspace_id,run_id,parent_id,child_id,transform,version,lossy
                ) VALUES(:id,:w,:r,:parent,:child,'base64','1',false)
                """,
                {
                    "id": str(uuid4()),
                    "w": str(workspace),
                    "r": run_id,
                    "parent": original["id"],
                    "child": child,
                },
            )
        status, body = _get(principal, f"/api/v1/runs/{run_id}")
        assert status == 200
        original_row = next(item for item in body["sources"] if item["id"] == original["id"])
        assert original_row["declared_media_type"] == "text/html"
        assert original_row["representation_kind"] == "original"
        assert original_row["parser_id"] is None
        child_row = next(item for item in body["sources"] if item["id"] == child)
        assert child_row["declared_media_type"] is None
        assert body["edges"] == [
            {
                "parent_id": original["id"],
                "child_id": child,
                "transform": "base64",
                "version": "1",
                "lossy": False,
                "transform_steps": None,
            }
        ]
        hidden, outsider = _get("user_" + uuid4().hex, f"/api/v1/runs/{run_id}")
        assert (hidden, outsider["code"]) == (404, "not_found")
    finally:
        _stop(database, run_id)


def test_module_002_submit_still_omits_ingestion_columns(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace = _workspace(database, principal)
    run_id = submit(
        database,
        principal,
        LegacySubmission(
            workspace_id=workspace,
            template="support-triage/1",
            goal=GOAL,
            source="unchanged paste",
            confirmed=True,
            sanitized=True,
        ),
        uuid4().hex,
    )
    try:
        with database.connect() as connection:
            node = one(
                connection,
                """
                SELECT declared_media_type,representation_kind,charset,byte_size,
                       parser_id,parser_version
                FROM content_nodes WHERE run_id=:run
                """,
                {"run": run_id},
            )
        assert node == {
            "declared_media_type": None,
            "representation_kind": None,
            "charset": None,
            "byte_size": None,
            "parser_id": None,
            "parser_version": None,
        }
    finally:
        _stop(database, run_id)
