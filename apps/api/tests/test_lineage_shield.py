"""M004 Slice F: security, retention, query-plan, and observability shield.

This is a proof suite, not a product expansion. Fixtures are labeled synthetic test data.
"""

import ast
import inspect
import json
import logging
import os
import time
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
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from starlette.responses import Response
from test_database_integration import TicketProvider, awaiting_review, decide, provision, submission
from test_lineage_api import (
    NOT_FOUND,
    SENTINELS,
    MarkupProvider,
    SentinelProvider,
    action_path,
    block_run,
    derived_run,
    fetch,
    first_action,
    get,
    make_app,
    mutated,
    node_path,
    raw_id,
    refused,
    run_path,
)
from test_lineage_assemble import baseline, read
from test_lineage_read import (
    captured,
    completed,
    fetch_scalar,
    immutability_trigger_enabled,
    insert_aged_expired_source,
    run_retain,
    settle,
    snapshot_of_state,
)
from test_lineage_schema import HEAD

from vetoq import (
    action_guard,
    inspection,
    lineage_model,
    lineage_read,
    lineage_routes,
    visibility,
    workflow,
)
from vetoq.auth import principal as require_principal
from vetoq.config import Settings
from vetoq.contracts import Analysis
from vetoq.db import engine_for, execute
from vetoq.ingestion.limits import BUDGETS
from vetoq.lineage_model import DEFAULT_BOUNDS, LEGAL_MAXIMA
from vetoq.lineage_read import build_action_lineage, build_node_lineage, build_run_lineage
from vetoq.lineage_routes import SERVER_BOUNDS
from vetoq.main import SCHEMA_REVISION
from vetoq.workflow import submit, tick

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration

VISIBLE_RUN = """
    SELECT r.* FROM runs r
    JOIN workspaces w ON w.id=r.workspace_id
    JOIN memberships m ON m.workspace_id=r.workspace_id
    WHERE r.id=:id AND m.principal=:principal AND m.active AND w.active
"""
LINEAGE_SQL = (
    ("content_nodes", lineage_read._NODES),
    ("content_edges", lineage_read._EDGES),
    ("content_edge_steps", lineage_read._STEPS),
    ("findings", lineage_read._FINDINGS),
    ("actions", lineage_read._ACTIONS),
    ("guard_decisions", lineage_read._DECISIONS),
    ("reviews", lineage_read._REVIEWS),
    ("executions", lineage_read._EXECUTIONS),
    ("tickets", lineage_read._TICKETS),
)


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, development_urls())
    except UnsafeTestDatabase as error:
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    engine = engine_for(
        Settings(_env_file=None, environment="test", database_url=SecretStr(DATABASE_URL))
    )
    try:
        require_disposable_engine(engine)
    except UnsafeTestDatabase as error:
        engine.dispose()
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    with engine.begin() as connection:
        execute(
            connection,
            """
            UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL
            WHERE state IN ('QUEUED','PROPOSING','AUTHORIZING','VERIFYING','AWAITING_REVIEW')
            """,
        )
    yield engine
    engine.dispose()


def internal_error_envelope(error: Exception) -> dict[str, Any]:
    """The global Exception handler's public JSON, without going through TestClient."""

    import asyncio

    from starlette.requests import Request

    from vetoq.main import create_app

    app = create_app(Settings(_env_file=None, environment="test", trusted_hosts=["testserver"]))
    handler = app.exception_handlers[Exception]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/runs/x/lineage",
        "raw_path": b"/api/v1/runs/x/lineage",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    request = Request(scope)
    request.state.correlation_id = str(uuid4())

    async def invoke() -> Response:
        maybe = handler(request, error)
        resolved = await maybe if inspect.isawaitable(maybe) else maybe
        assert isinstance(resolved, Response)
        return resolved

    response = asyncio.run(invoke())
    payload: dict[str, Any] = json.loads(bytes(response.body))
    return payload


def imported_modules(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


# ---- bound derivations -------------------------------------------------------------


def test_server_bounds_cover_every_still_supported_write_path() -> None:
    """Case A: a valid node or action cannot be hidden by the cap, so focused 404 stays."""

    assert LEGAL_MAXIMA.nodes == 1 + 16 * (1 + 16)
    assert LEGAL_MAXIMA.nodes == 273
    assert LEGAL_MAXIMA.edges == 272
    assert LEGAL_MAXIMA.steps == 1088
    assert LEGAL_MAXIMA.findings == 9 * 273 + 30
    assert LEGAL_MAXIMA.actions == 3
    assert LEGAL_MAXIMA.decisions == 12
    assert LEGAL_MAXIMA.tickets == 1
    assert LEGAL_MAXIMA.evidence_ids == BUDGETS.proposal_evidence_ids
    assert LEGAL_MAXIMA.traversal_depth == BUDGETS.derivation_depth
    assert len(inspection.RULES) == lineage_model.HEURISTIC_FAMILY_COUNT
    assert "max_length=30" in inspect.getsource(Analysis)
    inspect_source = inspect.getsource(inspection.inspect)
    assert "enforce_count=False" in inspect_source
    assert BUDGETS.derived_representations_per_run + BUDGETS.originals_per_run < (
        LEGAL_MAXIMA.nodes
    )
    caps = SERVER_BOUNDS
    assert caps is DEFAULT_BOUNDS
    assert caps.max_nodes >= LEGAL_MAXIMA.nodes
    assert caps.max_edges >= LEGAL_MAXIMA.edges
    assert caps.max_steps >= LEGAL_MAXIMA.steps
    assert caps.max_findings >= LEGAL_MAXIMA.findings
    assert caps.max_actions >= LEGAL_MAXIMA.actions
    assert caps.max_decisions >= LEGAL_MAXIMA.decisions
    assert caps.max_reviews >= LEGAL_MAXIMA.reviews
    assert caps.max_executions >= LEGAL_MAXIMA.executions
    assert caps.max_tickets >= LEGAL_MAXIMA.tickets
    assert caps.max_evidence_ids >= LEGAL_MAXIMA.evidence_ids
    assert caps.max_traversal_depth >= LEGAL_MAXIMA.traversal_depth


def test_m002_legacy_inspection_is_the_node_cardinality_maximum() -> None:
    """M003 is count-capped at 33. M002 fans out without that cap, still under 300."""

    assert BUDGETS.originals_per_run + BUDGETS.derived_representations_per_run == 33
    branching = BUDGETS.base64_matches_per_representation
    m002 = BUDGETS.originals_per_run + branching * (1 + branching)
    assert m002 == LEGAL_MAXIMA.nodes == 273
    assert DEFAULT_BOUNDS.max_nodes >= m002


# ---- authority and lookup shape ----------------------------------------------------


def test_authority_and_guard_input_are_independent_of_the_read_side() -> None:
    read_side = {
        "vetoq.lineage_read",
        "vetoq.lineage_assemble",
        "vetoq.lineage_graph",
        "vetoq.lineage_model",
        "vetoq.lineage_views",
        "vetoq.lineage_routes",
        "vetoq.lineage_observe",
    }
    assert "guard_decisions" not in inspect.getsource(action_guard)
    for module in (action_guard, workflow):
        assert not imported_modules(module) & read_side
        source = inspect.getsource(module)
        assert "build_run_lineage" not in source
        assert "lineage_routes" not in source
        assert "lineage_observe" not in source
    # The writer inserts output evidence and allocates the next ordinal. It does not
    # read decision history to decide ALLOW, REVIEW, or execution.
    writer = inspect.getsource(workflow)
    assert writer.count("INSERT INTO guard_decisions") == 1
    assert "FROM guard_decisions" in writer
    assert "build_action_lineage" not in writer
    assert not {
        name
        for name in action_guard.GuardInput.__dataclass_fields__
        if "lineage" in name or "integrity" in name
    }


def test_every_lineage_query_is_run_scoped_and_never_a_global_id_lookup() -> None:
    for name, sql in LINEAGE_SQL:
        compact = " ".join(sql.split())
        assert "workspace_id=:workspace" in compact, name
        assert "run_id=:run" in compact or "e.run_id=:run" in compact, name
        assert "FOR UPDATE" not in sql.upper(), name
        assert "audit_events" not in sql, name
    helper = inspect.getsource(visibility.visible_run)
    assert "JOIN workspaces" in helper and "m.active" in helper and "w.active" in helper
    focus = inspect.getsource(lineage_read.focus_node) + inspect.getsource(
        lineage_read.focus_action
    )
    assert "SELECT" not in focus
    assert "build_run_lineage" in inspect.getsource(lineage_read.build_node_lineage)
    assert "build_run_lineage" in inspect.getsource(lineage_read.build_action_lineage)


def test_d1_retention_fixture_never_disables_the_immutability_trigger() -> None:
    import test_lineage_read as module

    source = inspect.getsource(module)
    assert "DISABLE TRIGGER" not in source
    assert "ENABLE TRIGGER" not in source
    assert "DISABLE TRIGGER" not in inspect.getsource(lineage_read)


# ---- tenancy, tampering, methods ---------------------------------------------------


def test_same_tool_lineage_reports_allow_and_block_and_writes_nothing_in_b(
    database: Engine,
) -> None:
    principal, allowed, denied, workspace_b = block_run(database)
    before = snapshot_of_state(database, denied)
    with database.connect() as connection:
        tickets = connection.execute(
            text("SELECT count(*) FROM tickets WHERE workspace_id=:w"),
            {"w": workspace_b},
        ).scalar_one()
    assert tickets == 0
    ok = get(principal, action_path(allowed, first_action(database, principal, allowed)))
    assert ok[0] == 200 and ok[1]["action"]["stage"] == "verified"
    blocked = get(principal, run_path(denied))[1]
    assert blocked["run"]["state"] == "BLOCKED"
    for action in blocked["actions"]:
        status, view = get(principal, action_path(denied, action["action_id"]))
        assert status == 200
        assert view["action"]["stage"] == "blocked"
        assert "GOAL_SCOPE_MISMATCH" in view["action"]["decisions"][0]["reasons"]
        assert view["action"]["execution"] is None
    assert snapshot_of_state(database, denied) == before
    with database.connect() as connection:
        still = connection.execute(
            text("SELECT count(*) FROM tickets WHERE workspace_id=:w"),
            {"w": workspace_b},
        ).scalar_one()
    assert still == 0


def test_non_enumeration_covers_every_selector_shape(database: Engine) -> None:
    owner, run_id = completed(database)
    lineage = build_run_lineage(database, owner, run_id)
    node_id = raw_id(lineage.contents[0].id)
    action_id = lineage.actions[0].action_id
    outsider = "user_" + uuid4().hex
    provision(database, outsider)
    paths = [run_path(run_id), node_path(run_id, node_id), action_path(run_id, action_id)]
    for path in paths:
        assert refused(None, path)[0] == 401
        assert refused(outsider, path) == NOT_FOUND
        assert refused(owner, path.replace(run_id, str(uuid4()))) == NOT_FOUND
    for node in (str(uuid4()), "not-a-uuid", "content:" + node_id, node_id + "0"):
        assert refused(owner, node_path(run_id, node)) == NOT_FOUND
    for action in (str(uuid4()), "proposal:" + action_id, "x"):
        assert refused(owner, action_path(run_id, action)) == NOT_FOUND
    other_owner, other_run = completed(database)
    other = build_run_lineage(database, other_owner, other_run)
    assert refused(owner, run_path(other_run)) == NOT_FOUND
    assert refused(owner, node_path(run_id, raw_id(other.contents[0].id))) == NOT_FOUND
    assert refused(owner, action_path(run_id, other.actions[0].action_id)) == NOT_FOUND
    allowed_owner, allowed, denied, _ = block_run(database)
    allowed_node = raw_id(build_run_lineage(database, allowed_owner, allowed).contents[0].id)
    allowed_action = first_action(database, allowed_owner, allowed)
    for path in (
        node_path(denied, allowed_node),
        action_path(denied, allowed_action),
    ):
        assert refused(allowed_owner, path) == NOT_FOUND
    workspace = str(
        fetch_scalar(database, "SELECT workspace_id FROM runs WHERE id=:r", {"r": run_id})
    )
    with database.begin() as connection:
        execute(connection, "UPDATE workspaces SET active=false WHERE id=:w", {"w": workspace})
    for path in paths:
        assert refused(owner, path) == NOT_FOUND
    with database.begin() as connection:
        execute(connection, "UPDATE workspaces SET active=true WHERE id=:w", {"w": workspace})
        execute(
            connection,
            "UPDATE memberships SET active=false WHERE workspace_id=:w AND principal=:p",
            {"w": workspace, "p": owner},
        )
    for path in paths:
        assert refused(owner, path) == NOT_FOUND


def test_unknown_query_parameters_cannot_change_authorization_bounds_or_bodies(
    database: Engine,
) -> None:
    principal, run_id = derived_run(database)
    lineage = build_run_lineage(database, principal, run_id)
    node_id = raw_id(lineage.contents[0].id)
    action_id = lineage.actions[0].action_id
    extras = (
        "workspace_id="
        + str(uuid4())
        + "&depth=99999&limit=999999&unlimited=true&disable_bounds=true"
        + "&include_body=true&include_audit=true&max_nodes=1"
    )
    baseline_run = get(principal, run_path(run_id))
    spoofed = get(principal, f"{run_path(run_id)}?{extras}")
    assert spoofed[0] == 200
    assert {k: spoofed[1][k] for k in spoofed[1] if k != "read_time"} == {
        k: baseline_run[1][k] for k in baseline_run[1] if k != "read_time"
    }
    assert spoofed[1]["bounds"]["caps"]["max_nodes"] == 300
    dumped = json.dumps(spoofed[1])
    assert "include_body" not in dumped
    node = get(principal, f"{node_path(run_id, node_id, 'both')}&{extras}")
    assert node[0] == 200 and node[1]["bounds"]["caps"]["max_traversal_depth"] == 3
    action = get(principal, f"{action_path(run_id, action_id)}?{extras}")
    assert action[0] == 200 and action[1]["action"]["stage"] in {"verified", "blocked"}


def test_lineage_routes_reject_every_write_method(database: Engine) -> None:
    principal, run_id = completed(database)
    app = make_app()
    app.dependency_overrides[require_principal] = lambda: principal
    paths = [
        run_path(run_id),
        node_path(run_id, "n"),
        action_path(run_id, "a"),
    ]
    try:
        with TestClient(app) as client:
            for path in paths:
                for method in ("post", "put", "patch", "delete"):
                    response = getattr(client, method)(path)
                    assert response.status_code == 405, (method, path)
                    assert response.headers.get("cache-control") == "no-store"
    finally:
        if app.state.engine is not None:
            app.state.engine.dispose()


def test_openapi_exposes_only_direction_as_a_lineage_query_parameter() -> None:
    schema = make_app(configured=False).openapi()
    paths = {
        "/api/v1/runs/{run_id}/lineage",
        "/api/v1/runs/{run_id}/lineage/nodes/{node_id}",
        "/api/v1/runs/{run_id}/lineage/actions/{action_id}",
    }
    names: set[str] = set()
    for path in paths:
        assert set(schema["paths"][path]) == {"get"}
        for parameter in schema["paths"][path]["get"]["parameters"]:
            names.add(parameter["name"])
    assert names == {"run_id", "node_id", "action_id", "direction"}
    assert "workspace_id" not in names
    assert not {"depth", "limit", "unlimited", "include_body", "include_audit"} & names


# ---- retention hygiene, leaks, errors ----------------------------------------------


def test_aged_insert_keeps_immutable_run_enabled_and_retain_is_unverifiable(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert immutability_trigger_enabled(database)
    principal, run_id = insert_aged_expired_source(database)
    assert immutability_trigger_enabled(database)
    status, body = get(principal, run_path(run_id))
    assert status == 200 and body["retention"]["state"] == "expired_body_pending_deletion"
    run_retain(database, monkeypatch)
    status, body = get(principal, run_path(run_id))
    assert status == 200 and body["retention"]["state"] == "unverifiable"
    assert "removed_by_retention" not in json.dumps(body)
    assert immutability_trigger_enabled(database)


def test_observability_and_responses_never_carry_sentinels_or_response_ids(
    database: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    from test_ingestion_pipeline import _accept, _workspace

    principal, workspace = _workspace(database)
    source = f"Synthetic customer needs help. {SENTINELS[0]} Please open one ticket."
    run_id = _accept(database, principal, workspace, source, "text/plain")
    settle(database, SentinelProvider(workspace))
    lineage = build_run_lineage(database, principal, run_id)
    correlation_id = str(uuid4())
    caplog.set_level(logging.DEBUG, logger="vetoq.api")
    response = fetch(
        principal,
        run_path(run_id),
        headers={"X-Request-ID": correlation_id},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == correlation_id
    logged = caplog.text
    assert "lineage_read_completed" in logged
    assert f"correlation_id={correlation_id}" in logged
    assert f"run_id={run_id}" in logged
    assert "kind=run" in logged
    for sentinel in SENTINELS:
        assert sentinel not in response.text
        assert sentinel not in logged
        assert sentinel not in json.dumps(dict(response.headers))
    assert "producer_response_id" not in logged
    node = fetch(principal, node_path(run_id, raw_id(lineage.contents[0].id)))
    action = fetch(principal, action_path(run_id, lineage.actions[0].action_id))
    assert node.status_code == 200 and action.status_code == 200
    assert "kind=node" in caplog.text and "kind=action" in caplog.text
    guessed = str(uuid4())
    missing = fetch(principal, run_path(guessed), headers={"X-Request-ID": str(uuid4())})
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    assert f"run_id={guessed}" not in caplog.text


def test_hostile_response_id_is_json_only_and_absent_from_logs(
    database: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    run_id = submit(database, principal, submission(workspace), "shield-" + uuid4().hex)
    tick_limit = 12
    for _ in range(tick_limit):
        if not tick(database, MarkupProvider(workspace)):
            break
    caplog.set_level(logging.DEBUG)
    response = fetch(principal, run_path(run_id))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-content-type-options"] == "nosniff"
    stored = response.json()["actions"][0]["proposal"]["producer"]["response_id"]
    assert stored == MarkupProvider.response_id
    assert MarkupProvider.response_id not in caplog.text
    assert not response.text.lstrip().startswith("<")


def test_public_errors_never_include_sql_hosts_or_constraint_names(
    database: Engine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    principal, run_id = completed(database)
    secret = "postgresql://vetoq:password@10.0.0.9:5432/vetoq"
    sql = "SELECT * FROM content_nodes WHERE digest='deadbeef'"
    constraint = "guard_decisions_unique_ordinal"

    def explode(*_: Any) -> Any:
        raise RuntimeError(f"{secret} {sql} {constraint} TRACEBACK")

    monkeypatch.setattr(lineage_read, "read_snapshot", explode)
    caplog.set_level(logging.INFO, logger="vetoq.api")
    with pytest.raises(RuntimeError, match="TRACEBACK"):
        fetch(principal, run_path(run_id))
    body = internal_error_envelope(RuntimeError(f"{secret} {sql} {constraint} TRACEBACK"))
    dumped = json.dumps(body)
    for leak in (secret, "10.0.0.9", sql, constraint, "TRACEBACK", "password"):
        assert leak not in dumped
    assert body["code"] == "internal_error"
    assert body["message"] == "Request could not be completed."
    assert body["retryable"] is False
    lineage_logs = [r.message for r in caplog.records if "lineage_read" in r.message]
    assert lineage_logs == []


def test_statement_timeout_during_read_is_a_safe_500_and_changes_no_state(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    before = snapshot_of_state(database, run_id)

    def timeout(connection: Any, *_: Any) -> Any:
        connection.execute(text("SET LOCAL statement_timeout = '1ms'"))
        connection.execute(text("SELECT pg_sleep(1)"))

    monkeypatch.setattr(lineage_read, "read_snapshot", timeout)
    with pytest.raises(DBAPIError):
        fetch(principal, run_path(run_id))
    envelope = internal_error_envelope(RuntimeError("SELECT pg_sleep statement_timeout TRACEBACK"))
    dumped = json.dumps(envelope).lower()
    assert "pg_sleep" not in dumped
    assert "statement_timeout" not in dumped
    assert "traceback" not in dumped
    assert snapshot_of_state(database, run_id) == before
    assert before["failure"] is None


def test_configured_but_unreachable_database_stays_500_like_every_other_route(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)

    class Closed:
        def connect(self) -> Any:
            raise RuntimeError("could not connect to server at 10.0.0.9")

        def dispose(self) -> None:
            return None

    app = make_app()
    app.dependency_overrides[require_principal] = lambda: principal
    original = app.state.engine
    app.state.engine = Closed()
    try:
        with TestClient(app) as client:
            with pytest.raises(RuntimeError, match="10.0.0.9"):
                client.get(run_path(run_id))
            with pytest.raises(RuntimeError, match="10.0.0.9"):
                client.get(f"/api/v1/runs/{run_id}")
    finally:
        if original is not None:
            original.dispose()
    envelope = internal_error_envelope(RuntimeError("could not connect to server at 10.0.0.9"))
    assert envelope["code"] == "internal_error"
    assert "10.0.0.9" not in json.dumps(envelope)
    unconfigured = fetch(principal, run_path(run_id), configured=False)
    assert unconfigured.status_code == 503
    assert unconfigured.json()["code"] == "database_not_configured"


# ---- query count, plans, snapshot, payload -----------------------------------------


def test_run_node_and_action_reads_use_the_same_fixed_query_group(
    database: Engine,
) -> None:
    principal, run_id = derived_run(database)
    lineage = build_run_lineage(database, principal, run_id)
    node_id = raw_id(lineage.contents[0].id)
    action_id = lineage.actions[0].action_id
    run_sql = captured(database, lambda: build_run_lineage(database, principal, run_id))
    node_sql = captured(database, lambda: build_node_lineage(database, principal, run_id, node_id))
    action_sql = captured(
        database, lambda: build_action_lineage(database, principal, run_id, action_id)
    )
    assert len(run_sql) == len(node_sql) == len(action_sql) == 12
    assert not any("WITH RECURSIVE" in s.upper() for s in run_sql)
    verbs = {s.lstrip().split(None, 1)[0].upper() for s in run_sql}
    assert verbs <= {"SELECT", "SET"}
    assert sum("TRANSACTION" in s.upper() for s in run_sql) == 1


def _explain(connection: Any, sql: str, params: dict[str, Any]) -> str:
    rows = connection.execute(text("EXPLAIN " + sql), params).fetchall()
    return "\n".join(str(row[0]) for row in rows)


def test_run_scoped_queries_have_an_index_path(database: Engine) -> None:
    principal, run_id = completed(database)
    workspace = str(
        fetch_scalar(database, "SELECT workspace_id FROM runs WHERE id=:r", {"r": run_id})
    )
    params = {
        "workspace": workspace,
        "run": run_id,
        "limit": 8,
        "id": run_id,
        "principal": principal,
    }
    plans: dict[str, str] = {}
    with database.begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plans["visible_run"] = _explain(
            connection, VISIBLE_RUN, {"id": run_id, "principal": principal}
        )
        for name, sql in LINEAGE_SQL:
            plans[name] = _explain(connection, sql, params)
    with database.begin() as connection:
        ordinary_executions = _explain(connection, lineage_read._EXECUTIONS, params)
    indexed = {
        name
        for name, plan in plans.items()
        if "Index Scan" in plan or "Index Only Scan" in plan or "Bitmap Index Scan" in plan
    }
    required = {
        "visible_run",
        "content_nodes",
        "content_edges",
        "content_edge_steps",
        "findings",
        "actions",
        "guard_decisions",
        "reviews",
        "tickets",
        "executions",
    }
    assert required <= indexed, {name: plans[name] for name in required - indexed}
    assert "executions_workspace_run_idx" in plans["executions"]
    # Tiny tables may still seq-scan without enable_seqscan=off. That is not a failure.
    assert (
        "Seq Scan" in ordinary_executions or "executions_workspace_run_idx" in ordinary_executions
    )


def test_execution_index_does_not_change_lineage_semantics(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    status, allowed = get(principal, run_path(run_id))
    assert status == 200
    assert allowed["actions"][0]["stage"] == "verified"
    assert allowed["actions"][0]["execution"]["authorization"] == "consistent"
    sql = captured(database, lambda: build_run_lineage(database, principal, run_id))
    assert len(sql) == 12

    owner, _allowed, denied, _workspace = block_run(database)
    blocked = get(owner, run_path(denied))[1]["actions"][0]
    assert blocked["stage"] == "blocked" and blocked["execution"] is None

    opened = awaiting_review(database)
    pending = get(opened["owner"], run_path(opened["run_id"]))[1]["actions"][0]
    assert pending["stage"] == "review_pending" and pending["execution"] is None
    assert decide(opened["reviewer"], opened["review_id"], opened["digest"])[0] == 200
    settle(database, TicketProvider(UUID(opened["workspace"])))
    approved = get(opened["owner"], run_path(opened["run_id"]))[1]["actions"][0]
    assert approved["stage"] == "verified"
    assert [(d["ordinal"], d["verdict"]) for d in approved["decisions"]] == [
        (1, "REVIEW"),
        (2, "ALLOW"),
    ]
    assert approved["execution"]["authorization"] == "consistent"

    def drop_link(parts: dict[str, list[dict[str, Any]]]) -> None:
        parts["decisions"].clear()
        parts["executions"][0]["guard_decision_id"] = None

    mutated(monkeypatch, drop_link)
    legacy = get(principal, run_path(run_id))[1]["actions"][0]
    assert legacy["execution"]["authorization"] == "not_recorded"
    assert legacy["decisions"] == []
    assert get(principal, run_path(run_id))[0] == 200


def test_read_only_snapshot_and_read_failure_do_not_change_authority(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    before = snapshot_of_state(database, run_id)
    statements = captured(database, lambda: build_run_lineage(database, principal, run_id))
    assert any("REPEATABLE READ" in s.upper() and "READ ONLY" in s.upper() for s in statements)
    assert statements[0].lstrip().upper().startswith("SET TRANSACTION")
    assert not any("FOR UPDATE" in s.upper() for s in statements)
    get(principal, run_path(run_id))
    assert snapshot_of_state(database, run_id) == before

    def explode(*_: Any) -> Any:
        raise RuntimeError("synthetic shield failure")

    monkeypatch.setattr(lineage_read, "read_snapshot", explode)
    with pytest.raises(RuntimeError, match="synthetic shield failure"):
        fetch(principal, run_path(run_id))
    assert snapshot_of_state(database, run_id) == before


def test_truncated_read_is_200_with_one_aggregate_log(
    database: Engine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    principal, run_id = derived_run(database)
    monkeypatch.setattr(
        lineage_routes, "SERVER_BOUNDS", lineage_model.LineageBounds(max_nodes=1, max_edges=1)
    )
    caplog.set_level(logging.INFO, logger="vetoq.api")
    status, body = get(principal, run_path(run_id))
    assert status == 200 and body["bounds"]["truncated"] is True
    assert any(i["code"] == "bound_exceeded" for i in body["integrity"])
    completed_logs = [r for r in caplog.records if "lineage_read_completed" in r.message]
    assert len(completed_logs) == 1
    assert "truncated=True" in completed_logs[0].message
    assert "anomaly_count=" in completed_logs[0].message


def test_legal_maximum_metadata_payload_is_structurally_bounded() -> None:
    parts = baseline()
    scope = {
        "workspace_id": parts["run"]["workspace_id"],
        "run_id": parts["run"]["id"],
    }
    root = parts["nodes"][0]
    generation = [str(root["id"])]
    branching = BUDGETS.base64_matches_per_representation
    steps_per_edge = BUDGETS.transform_steps_per_edge
    for _depth in range(BUDGETS.derivation_depth):
        nxt: list[str] = []
        for parent_id in generation:
            for _child in range(branching):
                child_id = str(uuid4())
                child = dict(root)
                child.update(id=child_id, origin="derived", **scope)
                parts["nodes"].append(child)
                edge_id = str(uuid4())
                parts["edges"].append(
                    {
                        **scope,
                        "id": edge_id,
                        "parent_id": parent_id,
                        "child_id": child_id,
                        "transform": "base64",
                        "version": "1",
                        "lossy": False,
                        "transform_step_count": steps_per_edge,
                    }
                )
                for index in range(1, steps_per_edge + 1):
                    parts["steps"].append(
                        {
                            "edge_id": edge_id,
                            "step_index": index,
                            "transform": "base64",
                            "version": "1",
                        }
                    )
                nxt.append(child_id)
        generation = nxt
    started = time.perf_counter()
    lineage = read(parts)
    duration_ms = (time.perf_counter() - started) * 1000
    payload = lineage.model_dump_json()
    size = len(payload.encode())
    assert lineage.bounds.truncated is False
    assert len(lineage.contents) == LEGAL_MAXIMA.nodes
    assert len(lineage.edges) == LEGAL_MAXIMA.edges
    assert sum(len(edge.steps or ()) for edge in lineage.edges) == LEGAL_MAXIMA.steps
    assert "Synthetic test source." not in payload
    # Diagnostic only. Not an SLA. Generous hang detector, not a performance claim.
    assert duration_ms < 60_000
    assert size < 2_000_000
    assert size > 1_000


def test_schema_revision_is_0007() -> None:
    assert SCHEMA_REVISION == HEAD == "0007_lineage_execution_lookup"
    assert "0008" not in inspect.getsource(lineage_model)


def test_integrity_anomaly_is_one_aggregate_event_not_one_log_per_finding(
    database: Engine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    principal, run_id = completed(database)

    def corrupt(parts: dict[str, list[dict[str, Any]]]) -> None:
        parts["nodes"][0]["digest_ok"] = False
        parts["actions"][0]["digest"] = "0" * 64
        parts["decisions"][0]["ordinal"] = 3

    mutated(monkeypatch, corrupt)
    caplog.set_level(logging.INFO, logger="vetoq.api")
    status, body = get(principal, run_path(run_id))
    assert status == 200 and body["integrity"]
    events = [r.message for r in caplog.records if "lineage_read_completed" in r.message]
    assert len(events) == 1
    assert "anomaly_count=" in events[0]
    assert events[0].count("lineage_read_completed") == 1
    assert "content_digest_mismatch" in events[0]
