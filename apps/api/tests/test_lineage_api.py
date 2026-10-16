"""M004 Slice E: the typed, authenticated, read-only lineage HTTP APIs.

Every run is produced by the real workflow and every request goes through the real FastAPI
application, the real authentication dependency seam, and a real PostgreSQL database. States
the schema forbids, and legacy states no current writer produces, are reached by mutating the
rows of one real read snapshot, so the routes, visibility rule and serialization stay real.
Fixtures are labeled synthetic test data, never operational metrics.
"""

import ast
import copy
import dataclasses
import inspect
import json
import logging
import os
from collections.abc import Callable, Iterator
from typing import Any, cast
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
from sqlalchemy import Connection, Engine, event
from test_database_integration import (
    TicketProvider,
    awaiting_review,
    decide,
    provision,
    submission,
)
from test_ingestion_pipeline import _accept, _workspace
from test_lineage_read import (
    completed,
    fetch_scalar,
    insert_aged_expired_source,
    lagged_run,
    run_retain,
    settle,
    snapshot_of_state,
)

from vetoq import action_guard, lineage_read, lineage_routes, lineage_views, workflow
from vetoq.auth import principal as require_principal
from vetoq.config import Settings
from vetoq.contracts import Analysis, ModelFinding, TicketArguments
from vetoq.db import engine_for, execute
from vetoq.lineage_model import LineageBounds
from vetoq.lineage_read import build_node_lineage, build_run_lineage
from vetoq.main import create_app
from vetoq.providers.base import InferenceRequest, InferenceResult
from vetoq.workflow import event as audit_event
from vetoq.workflow import locked_run, submit

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration

NOT_FOUND = (404, "not_found", "Request could not be completed.", False)
SETS = (
    "nodes",
    "edges",
    "steps",
    "findings",
    "actions",
    "decisions",
    "reviews",
    "executions",
    "tickets",
)
HTML_EMAIL = "Content-Type: text/html\n\n<p>shown</p><script>hidden</script>\n"


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


# ---- request helpers -----------------------------------------------------------------


def make_app(*, configured: bool = True) -> FastAPI:
    assert DATABASE_URL is not None
    return create_app(
        Settings(
            _env_file=None,
            environment="test",
            trusted_hosts=["testserver"],
            database_url=SecretStr(DATABASE_URL) if configured else None,
        )
    )


def fetch(
    actor: str | None,
    path: str,
    *,
    statements: list[str] | None = None,
    headers: dict[str, str] | None = None,
    configured: bool = True,
) -> Any:
    """One GET through the real application. `actor=None` sends no credentials at all."""

    app = make_app(configured=configured)
    if actor is not None:
        app.dependency_overrides[require_principal] = lambda: actor
    if statements is not None:
        event.listen(
            app.state.engine,
            "before_cursor_execute",
            lambda _c, _cur, statement, *_: statements.append(statement),
        )
    try:
        with TestClient(app) as client:
            return client.get(path, headers=headers)
    finally:
        if app.state.engine is not None:
            app.state.engine.dispose()


def get(actor: str | None, path: str) -> tuple[int, dict[str, Any]]:
    response = fetch(actor, path)
    body: dict[str, Any] = response.json()
    return response.status_code, body


def refused(actor: str | None, path: str) -> tuple[int, object, object, object]:
    status, body = get(actor, path)
    return status, body.get("code"), body.get("message"), body.get("retryable")


def run_path(run_id: str) -> str:
    return f"/api/v1/runs/{run_id}/lineage"


def node_path(run_id: str, node_id: str, direction: str | None = None) -> str:
    base = f"{run_path(run_id)}/nodes/{node_id}"
    return base if direction is None else f"{base}?direction={direction}"


def action_path(run_id: str, action_id: str) -> str:
    return f"{run_path(run_id)}/actions/{action_id}"


def stable(body: dict[str, Any]) -> dict[str, Any]:
    """A body without the database read time, which differs on every read."""

    return {key: value for key, value in body.items() if key != "read_time"}


def raw_id(entity: str) -> str:
    return entity.split(":", 1)[1]


def mutated(
    monkeypatch: pytest.MonkeyPatch, change: Callable[[dict[str, list[dict[str, Any]]]], None]
) -> None:
    """Alter the rows of one real read snapshot, leaving the route and visibility real."""

    real = lineage_read.read_snapshot

    def patched(connection: Connection, run: dict[str, Any], bounds: LineageBounds) -> Any:
        snapshot = real(connection, run, bounds)
        parts = {name: copy.deepcopy(list(getattr(snapshot, name))) for name in SETS}
        change(parts)
        return dataclasses.replace(snapshot, **cast(dict[str, Any], parts))

    monkeypatch.setattr(lineage_read, "read_snapshot", patched)


def derived_run(database: Engine) -> tuple[str, str]:
    """A completed M003 run whose source has one derived representation."""

    principal, workspace = _workspace(database)
    run_id = _accept(database, principal, workspace, HTML_EMAIL, "message/rfc822")
    settle(database, TicketProvider(workspace))
    return principal, run_id


def block_run(database: Engine) -> tuple[str, str, str, str]:
    """Allowed run in workspace A and a same-principal, same-tool run aimed at workspace B."""

    principal = "user_" + uuid4().hex
    workspace_a, workspace_b = provision(database, principal)
    allowed = submit(database, principal, submission(workspace_a), "api-a-" + uuid4().hex)
    settle(database, TicketProvider(workspace_a))
    denied = submit(database, principal, submission(workspace_a), "api-b-" + uuid4().hex)
    settle(database, TicketProvider(workspace_b))
    return principal, allowed, denied, str(workspace_b)


def first_action(database: Engine, principal: str, run_id: str) -> str:
    return build_run_lineage(database, principal, run_id).actions[0].action_id


# ---- the run route -------------------------------------------------------------------


def test_run_lineage_is_the_service_output_with_the_public_structure(database: Engine) -> None:
    principal, run_id = completed(database)
    response = fetch(principal, run_path(run_id), headers={"X-Request-ID": str(uuid4())})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"] == response.request.headers["x-request-id"]

    body = response.json()
    assert set(body) == {
        "run",
        "read_time",
        "goal_lock",
        "source_binding",
        "contents",
        "edges",
        "findings",
        "actions",
        "relationships",
        "integrity",
        "retention",
        "bounds",
    }
    # One source of lineage meaning: the route body is the service model, nothing else.
    expected = lineage_views.canonical(build_run_lineage(database, principal, run_id))
    assert stable(body) == stable(expected.model_dump(mode="json"))
    assert body["run"]["run_id"] == run_id
    assert body["goal_lock"]["id"] == f"goal_lock:{run_id}"
    assert body["retention"]["state"] == "available"
    assert body["bounds"]["truncated"] is False and body["bounds"]["truncated_sets"] == []
    action = body["actions"][0]
    assert action["stage"] == "verified" and action["path"]["complete"] is True
    assert {r["kind"] for r in body["relationships"]} >= {
        "goal_lock_binds_source",
        "goal_lock_binds_proposal",
        "proposal_cites_content",
        "guard_decision_evaluates",
        "execution_of_proposal",
        "execution_authorized_by",
        "execution_produced_ticket",
    }
    assert all(r["basis"] for r in body["relationships"])


def test_unauthenticated_requests_are_401_and_reach_no_data(database: Engine) -> None:
    principal, run_id = completed(database)
    action_id = first_action(database, principal, run_id)
    node_id = raw_id(build_run_lineage(database, principal, run_id).contents[0].id)
    statements: list[str] = []
    for path in (
        run_path(run_id),
        node_path(run_id, node_id),
        action_path(run_id, action_id),
    ):
        response = fetch(None, path, statements=statements)
        assert response.status_code == 401
        assert response.json()["code"] == "authentication_required"
        assert response.headers["cache-control"] == "no-store"
    assert statements == []


def test_every_refusal_is_the_same_non_enumerating_404_on_all_three_routes(
    database: Engine,
) -> None:
    owner, run_id = completed(database)
    lineage = build_run_lineage(database, owner, run_id)
    node_id, action_id = raw_id(lineage.contents[0].id), lineage.actions[0].action_id
    paths = [
        run_path(run_id),
        node_path(run_id, node_id),
        action_path(run_id, action_id),
    ]
    outsider = "user_" + uuid4().hex
    provision(database, outsider)
    for path in paths:
        assert refused(outsider, path) == NOT_FOUND, path

    workspace = str(
        fetch_scalar(database, "SELECT workspace_id FROM runs WHERE id=:r", {"r": run_id})
    )
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE memberships SET active=false WHERE workspace_id=:w AND principal=:p",
            {"w": workspace, "p": owner},
        )
    for path in paths:
        assert refused(owner, path) == NOT_FOUND, path
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE memberships SET active=true WHERE workspace_id=:w AND principal=:p",
            {"w": workspace, "p": owner},
        )
        execute(connection, "UPDATE workspaces SET active=false WHERE id=:w", {"w": workspace})
    for path in paths:
        assert refused(owner, path) == NOT_FOUND, path
    with database.begin() as connection:
        execute(connection, "UPDATE workspaces SET active=true WHERE id=:w", {"w": workspace})
    for path in paths:
        assert get(owner, path)[0] == 200, path

    missing = str(uuid4())
    for path in (
        run_path(missing),
        node_path(missing, node_id),
        action_path(missing, action_id),
        run_path("not-a-run-id"),
    ):
        assert refused(owner, path) == NOT_FOUND, path


def test_a_client_supplied_workspace_never_participates_in_authorization(
    database: Engine,
) -> None:
    owner, run_id = completed(database)
    outsider = "user_" + uuid4().hex
    foreign_workspace, _ = provision(database, outsider)
    own = get(owner, run_path(run_id))
    assert own[0] == 200
    spoofed = get(owner, f"{run_path(run_id)}?workspace_id={foreign_workspace}")
    assert spoofed[0] == 200 and stable(spoofed[1]) == stable(own[1])
    denied = fetch(outsider, f"{run_path(run_id)}?workspace_id={foreign_workspace}")
    assert denied.status_code == 404
    header_denied = fetch(
        outsider, run_path(run_id), headers={"X-Workspace-Id": str(foreign_workspace)}
    )
    assert header_denied.status_code == 404


def test_a_truncated_lineage_is_a_200_that_says_so(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = derived_run(database)
    monkeypatch.setattr(
        lineage_routes, "SERVER_BOUNDS", LineageBounds(max_nodes=1, max_edges=1, max_steps=1)
    )
    status, body = get(principal, run_path(run_id))
    assert status == 200
    assert body["bounds"]["truncated"] is True
    assert body["bounds"]["truncated_sets"] == [
        "content_edge_steps",
        "content_edges",
        "content_nodes",
    ]
    assert body["bounds"]["caps"]["max_nodes"] == 1
    assert len(body["contents"]) == 1
    assert {i["code"] for i in body["integrity"]} >= {"bound_exceeded"}
    assert {i["status"] for i in body["integrity"]} == {"unverifiable"}
    # The focused views carry the same bounds report, so a clipped run is never complete.
    action_id = body["actions"][0]["action_id"]
    node_id = raw_id(body["contents"][0]["id"])
    for path in (node_path(run_id, node_id), action_path(run_id, action_id)):
        status, focused = get(principal, path)
        assert status == 200 and focused["bounds"]["truncated"] is True, path
        assert any(i["code"] == "bound_exceeded" for i in focused["integrity"]), path


def test_an_integrity_anomaly_is_reported_in_a_200_never_a_500(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    first = build_run_lineage(database, principal, run_id)
    node_id, action_id = raw_id(first.contents[0].id), first.actions[0].action_id

    def corrupt(parts: dict[str, list[dict[str, Any]]]) -> None:
        parts["nodes"][0]["digest_ok"] = False
        parts["actions"][0]["digest"] = "0" * 64
        parts["decisions"][0]["ordinal"] = 3

    mutated(monkeypatch, corrupt)
    status, body = get(principal, run_path(run_id))
    assert status == 200
    found = {(i["code"], i["status"]) for i in body["integrity"]}
    assert ("content_digest_mismatch", "inconsistent") in found
    assert ("proposal_digest_mismatch", "inconsistent") in found
    assert ("decision_ordinal_gap", "inconsistent") in found
    assert body["actions"][0]["path"]["complete"] is False
    for path in (node_path(run_id, node_id), action_path(run_id, action_id)):
        status, focused = get(principal, path)
        assert status == 200, path
        assert focused["integrity"], path
    # The safe shape: a code, a status and an entity reference. No prose, no exception text.
    assert all(set(i) == {"code", "status", "subject"} for i in body["integrity"])


# ---- the node route ------------------------------------------------------------------


def test_node_lineage_honours_the_direction_selector(database: Engine) -> None:
    principal, run_id = derived_run(database)
    lineage = build_run_lineage(database, principal, run_id)
    root = next(c for c in lineage.contents if c.is_source)
    leaf = next(c for c in lineage.contents if c.child_ids == () and not c.is_source)
    root_id, leaf_id = raw_id(root.id), raw_id(leaf.id)

    status, descendants = get(principal, node_path(run_id, root_id, "descendants"))
    assert status == 200
    assert descendants["direction"] == "descendants" and descendants["ancestors"] is None
    assert descendants["descendants"]["start"] == root.id
    reached = {name for name, _ in descendants["descendants"]["nodes"]}
    assert reached == {c.id for c in lineage.contents if c.id != root.id}
    assert {c["id"] for c in descendants["related"]} == reached

    status, ancestors = get(principal, node_path(run_id, leaf_id, "ancestors"))
    assert status == 200
    assert ancestors["direction"] == "ancestors" and ancestors["descendants"] is None
    assert root.id in {name for name, _ in ancestors["ancestors"]["nodes"]}
    assert ancestors["node"]["id"] == leaf.id

    status, both = get(principal, node_path(run_id, leaf_id, "both"))
    assert status == 200
    assert both["ancestors"] is not None and both["descendants"] is not None
    assert both["descendants"]["nodes"] == []
    # The default is both.
    assert stable(get(principal, node_path(run_id, leaf_id))[1]) == stable(both)

    expected = build_node_lineage(database, principal, run_id, leaf_id)
    assert {n for n, _ in both["ancestors"]["nodes"]} == {n for n, _ in expected.ancestors.nodes}
    assert both["citing_proposals"] == list(expected.citing_proposals)
    members = {both["node"]["id"], *(c["id"] for c in both["related"])}
    assert all(e["parent_id"] in members and e["child_id"] in members for e in both["edges"])
    assert {e["child_id"] for e in both["edges"]} >= {leaf.id}
    assert both["source_binding"]["status"] == "consistent"
    assert both["retention"]["state"] == "available"
    assert both["bounds"]["truncated"] is False


def test_an_invalid_direction_is_the_standard_422(database: Engine) -> None:
    principal, run_id = derived_run(database)
    node_id = raw_id(build_run_lineage(database, principal, run_id).contents[0].id)
    for direction in ("sideways", "ANCESTORS", "", "ancestors,descendants", "1"):
        response = fetch(principal, node_path(run_id, node_id, direction))
        assert response.status_code == 422, direction
        body = response.json()
        assert body["code"] == "invalid_input" and body["message"] == "Request input is invalid."
        assert body["retryable"] is False
        assert response.headers["cache-control"] == "no-store"
        assert "direction" not in json.dumps(body)


def test_a_caller_cannot_widen_disable_or_change_the_server_bounds(database: Engine) -> None:
    principal, run_id = derived_run(database)
    node_id = raw_id(build_run_lineage(database, principal, run_id).contents[0].id)
    baseline = get(principal, node_path(run_id, node_id, "both"))
    assert baseline[0] == 200
    for tampering in (
        "depth=1000",
        "max_depth=1000&unlimited=true",
        "page_size=100000&limit=100000",
        "disable_bounds=true&max_nodes=100000",
    ):
        status, body = get(principal, f"{node_path(run_id, node_id, 'both')}&{tampering}")
        assert status == 200, tampering
        assert stable(body) == stable(baseline[1]), tampering
        assert body["bounds"]["caps"]["max_traversal_depth"] == 3
        assert body["bounds"]["caps"]["max_nodes"] == 300
    status, whole = get(principal, f"{run_path(run_id)}?unlimited=true&max_nodes=100000")
    assert status == 200 and whole["bounds"]["caps"]["max_nodes"] == 300


def test_a_node_that_is_missing_or_foreign_is_the_same_404(database: Engine) -> None:
    owner, run_id = derived_run(database)
    other_owner, other_run = derived_run(database)
    sibling_run = _sibling_run(database, owner)
    outsider_node = raw_id(build_run_lineage(database, other_owner, other_run).contents[0].id)
    sibling_node = raw_id(build_run_lineage(database, owner, sibling_run).contents[0].id)
    own_node = raw_id(build_run_lineage(database, owner, run_id).contents[0].id)
    assert get(owner, node_path(run_id, own_node))[0] == 200
    for node_id in (str(uuid4()), outsider_node, sibling_node, "content:" + own_node, "x" * 300):
        assert refused(owner, node_path(run_id, node_id)) == NOT_FOUND, node_id
    # A node resolves only inside the run in the path, even for the principal who owns both.
    assert get(owner, node_path(sibling_run, sibling_node))[0] == 200
    assert refused(owner, node_path(run_id, sibling_node)) == NOT_FOUND


def _sibling_run(database: Engine, principal: str) -> str:
    workspace = UUID(
        str(
            fetch_scalar(
                database,
                "SELECT workspace_id FROM memberships WHERE principal=:p LIMIT 1",
                {"p": principal},
            )
        )
    )
    run_id = _accept(database, principal, workspace, HTML_EMAIL, "message/rfc822")
    settle(database, TicketProvider(workspace))
    return run_id


def test_a_cycle_keeps_the_node_view_finite_and_is_reported(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = derived_run(database)
    lineage = build_run_lineage(database, principal, run_id)
    root = raw_id(next(c for c in lineage.contents if c.is_source).id)

    def close_the_loop(parts: dict[str, list[dict[str, Any]]]) -> None:
        edge = copy.deepcopy(parts["edges"][-1])
        edge.update(id=str(uuid4()), parent_id=edge["child_id"], child_id=root)
        parts["edges"].append(edge)

    mutated(monkeypatch, close_the_loop)
    status, body = get(principal, node_path(run_id, root, "both"))
    assert status == 200
    assert any(i["code"] == "edge_cycle" for i in body["integrity"])
    for walk in (body["ancestors"], body["descendants"]):
        names = [name for name, _ in walk["nodes"]]
        assert len(names) == len(set(names)) and body["node"]["id"] not in names
        assert all(depth <= 3 for _, depth in walk["nodes"])


# ---- the action route ----------------------------------------------------------------


def test_direct_allow_action_has_the_full_causal_path(database: Engine) -> None:
    principal, run_id = completed(database)
    action_id = first_action(database, principal, run_id)
    status, body = get(principal, action_path(run_id, action_id))
    assert status == 200
    assert set(body) == {
        "run",
        "read_time",
        "goal_lock",
        "source_binding",
        "action",
        "evidence",
        "findings",
        "relationships",
        "retention",
        "integrity",
        "bounds",
    }
    action = body["action"]
    assert action["action_id"] == action_id and action["stage"] == "verified"
    assert [d["verdict"] for d in action["decisions"]] == ["ALLOW"]
    assert action["review"] is None
    assert action["execution"]["authorization"] == "consistent"
    assert action["execution"]["verified_at"] is not None
    assert action["execution"]["guard_decision_id"] == raw_id(action["decisions"][0]["id"])
    assert set(action["ticket"]) == {"id", "action_id", "created_at"}
    assert action["path"]["complete"] is True
    assert [s["kind"] for s in action["path"]["steps"]] == [
        "goal_lock",
        "source",
        "evidence",
        "proposal",
        "guard_decision",
        "execution",
        "ticket",
    ]
    assert [r["resolution"] for r in action["proposal"]["evidence"]] == ["resolved"]
    assert [c["id"] for c in body["evidence"]] == [
        f"content:{action['proposal']['evidence'][0]['node_id']}"
    ]
    assert body["goal_lock"]["valid"] is True and body["source_binding"]["status"] == "consistent"
    producer = action["proposal"]["producer"]
    assert (producer["state"], producer["provider"], producer["model"]) == (
        "recorded",
        "fixture",
        "fixture/structured",
    )
    assert producer["prompt_version"] == "fixture/1" and producer["response_id"]
    assert body["integrity"] == []
    assert body["bounds"]["truncated"] is False


def test_same_tool_destination_a_allows_and_destination_b_blocks_and_the_api_only_reports(
    database: Engine,
) -> None:
    principal, allowed, denied, workspace_b = block_run(database)
    with_tickets = "SELECT count(*) FROM tickets WHERE workspace_id=:w"
    before = fetch_scalar(database, with_tickets, {"w": workspace_b})
    assert before == 0

    ok = build_run_lineage(database, principal, allowed).actions[0]
    status, body = get(principal, action_path(allowed, ok.action_id))
    assert status == 200 and body["action"]["stage"] == "verified"
    assert [d["verdict"] for d in body["action"]["decisions"]] == ["ALLOW"]

    blocked_run = get(principal, run_path(denied))[1]
    assert blocked_run["run"]["state"] == "BLOCKED" and blocked_run["actions"]
    for action in blocked_run["actions"]:
        status, view = get(principal, action_path(denied, action["action_id"]))
        assert status == 200
        assert view["action"]["stage"] == "blocked"
        assert [d["verdict"] for d in view["action"]["decisions"]] == ["BLOCK"]
        assert "GOAL_SCOPE_MISMATCH" in view["action"]["decisions"][0]["reasons"]
        assert view["action"]["execution"] is None and view["action"]["ticket"] is None
        # Only this action appears. The other proposals of the run are not in the view.
        others = {a["proposal"]["id"] for a in blocked_run["actions"]} - {
            view["action"]["proposal"]["id"]
        }
        assert not any(
            r["source"] in others or r["target"] in others for r in view["relationships"]
        )
    assert fetch_scalar(database, with_tickets, {"w": workspace_b}) == 0


def test_review_then_allow_and_review_then_block_are_reported_in_order(database: Engine) -> None:
    approved = awaiting_review(database)
    pending = get(approved["owner"], run_path(approved["run_id"]))[1]["actions"][0]
    assert pending["stage"] == "review_pending"
    assert decide(approved["reviewer"], approved["review_id"], approved["digest"])[0] == 200
    settle(database, TicketProvider(UUID(approved["workspace"])))
    action_id = first_action(database, approved["owner"], approved["run_id"])
    status, body = get(approved["owner"], action_path(approved["run_id"], action_id))
    assert status == 200
    action = body["action"]
    assert action["stage"] == "verified"
    assert [(d["ordinal"], d["verdict"]) for d in action["decisions"]] == [
        (1, "REVIEW"),
        (2, "ALLOW"),
    ]
    assert {d["review_id"] for d in action["decisions"]} == {approved["review_id"]}
    review = action["review"]
    assert review["decision"] == "approve" and review["consumed"] is True
    assert review["requested_at"] <= review["decided_at"] <= review["consumed_at"]
    assert action["execution"]["authorization"] == "consistent"
    assert action["path"]["complete"] is True
    assert body["integrity"] == []

    rejected = awaiting_review(database)
    assert (
        decide(rejected["reviewer"], rejected["review_id"], rejected["digest"], "reject")[0] == 200
    )
    action_id = first_action(database, rejected["owner"], rejected["run_id"])
    status, body = get(rejected["owner"], action_path(rejected["run_id"], action_id))
    assert status == 200
    action = body["action"]
    assert action["stage"] == "blocked" and action["review"]["decision"] == "reject"
    assert action["execution"] is None and action["ticket"] is None
    assert body["integrity"] == []


def test_a_missing_or_foreign_action_is_the_same_404(database: Engine) -> None:
    owner, run_id = completed(database)
    sibling_owner, sibling_run = completed(database)
    own = first_action(database, owner, run_id)
    foreign_run_action = first_action(database, sibling_owner, sibling_run)
    assert get(owner, action_path(run_id, own))[0] == 200
    for action_id in (str(uuid4()), foreign_run_action, "proposal:" + own, "x" * 300):
        assert refused(owner, action_path(run_id, action_id)) == NOT_FOUND, action_id
    # Same workspace, different run: the action resolves only inside the run in the path.
    twin = _sibling_completed(database, owner)
    twin_action = first_action(database, owner, twin)
    assert get(owner, action_path(twin, twin_action))[0] == 200
    assert refused(owner, action_path(run_id, twin_action)) == NOT_FOUND


def _sibling_completed(database: Engine, principal: str) -> str:
    workspace = UUID(
        str(
            fetch_scalar(
                database,
                "SELECT workspace_id FROM memberships WHERE principal=:p LIMIT 1",
                {"p": principal},
            )
        )
    )
    run_id = submit(database, principal, submission(workspace), "twin-" + uuid4().hex)
    settle(database, TicketProvider(workspace))
    return run_id


# ---- retention, legacy, producer ---------------------------------------------------


def test_retention_states_are_exact_and_never_removed_by_retention(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def state_of(principal: str, run_id: str) -> tuple[str, dict[str, Any]]:
        response = fetch(principal, run_path(run_id))
        assert response.status_code == 200
        assert "removed_by_retention" not in response.text
        body = response.json()
        seen.append(body["retention"]["state"])
        return body["retention"]["state"], body

    principal, run_id = completed(database)
    assert state_of(principal, run_id)[0] == "available"

    principal, run_id = lagged_run(database, monkeypatch)
    state, body = state_of(principal, run_id)
    assert state == "expired_body_pending_deletion" and body["retention"]["source_present"] is True
    assert body["contents"][0]["body_state"] == "expired_body_pending_deletion"

    run_retain(database, monkeypatch)
    state, body = state_of(principal, run_id)
    assert state == "inconsistent"
    assert {(i["code"], i["status"]) for i in body["integrity"]} >= {
        ("source_missing_before_retention", "inconsistent")
    }

    principal, run_id = insert_aged_expired_source(database)
    assert state_of(principal, run_id)[0] == "expired_body_pending_deletion"
    run_retain(database, monkeypatch)
    state, body = state_of(principal, run_id)
    assert state == "unverifiable"
    assert {(i["code"], i["status"]) for i in body["integrity"]} == {
        ("source_missing_retention_unverifiable", "unverifiable")
    }
    # No deleted graph is invented, and the Goal Lock facts stay as stored.
    assert (body["contents"], body["edges"], body["findings"]) == ([], [], [])
    assert body["goal_lock"]["valid"] is True and body["goal_lock"]["source_id"]
    assert body["source_binding"]["status"] == "unverifiable"
    # The node and action views of the missing graph are the ordinary 404.
    assert refused(principal, node_path(run_id, body["goal_lock"]["source_id"])) == NOT_FOUND
    assert set(seen) == {
        "available",
        "expired_body_pending_deletion",
        "inconsistent",
        "unverifiable",
    }


def test_legacy_history_is_not_recorded_and_never_a_500(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    action_id = first_action(database, principal, run_id)

    def legacy(parts: dict[str, list[dict[str, Any]]]) -> None:
        for name in ("provider", "model", "prompt_version", "response_id"):
            parts["actions"][0][f"producer_{name}"] = None
        parts["decisions"].clear()
        parts["executions"][0]["guard_decision_id"] = None

    mutated(monkeypatch, legacy)
    status, body = get(principal, action_path(run_id, action_id))
    assert status == 200
    action = body["action"]
    assert action["proposal"]["producer"] == {
        "state": "not_recorded",
        "provider": None,
        "model": None,
        "prompt_version": None,
        "response_id": None,
    }
    assert action["decisions"] == []
    assert action["execution"]["authorization"] == "not_recorded"
    assert action["stage"] == "verified" and action["path"]["complete"] is False
    assert body["integrity"] == []
    assert any(
        r["kind"] == "execution_authorized_by"
        and r["target"] is None
        and r["basis"] == "not_recorded"
        for r in body["relationships"]
    )
    assert get(principal, run_path(run_id))[0] == 200


def test_legacy_review_timestamps_are_not_recorded(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = awaiting_review(database)
    assert decide(opened["reviewer"], opened["review_id"], opened["digest"])[0] == 200
    settle(database, TicketProvider(UUID(opened["workspace"])))
    action_id = first_action(database, opened["owner"], opened["run_id"])

    def legacy(parts: dict[str, list[dict[str, Any]]]) -> None:
        for name in ("requested_at", "decided_at", "consumed_at"):
            parts["reviews"][0][name] = None
        parts["decisions"].clear()
        parts["executions"][0]["guard_decision_id"] = None
        for name in ("provider", "model", "prompt_version", "response_id"):
            parts["actions"][0][f"producer_{name}"] = None

    mutated(monkeypatch, legacy)
    status, body = get(opened["owner"], action_path(opened["run_id"], action_id))
    assert status == 200
    review = body["action"]["review"]
    assert review["not_recorded"] == ["requested_at", "decided_at", "consumed_at"]
    assert (review["requested_at"], review["decided_at"], review["consumed_at"]) == (
        None,
        None,
        None,
    )
    assert body["integrity"] == []


class MarkupProvider(TicketProvider):
    """A provider whose opaque response id is hostile if it were ever rendered as markup."""

    response_id = "<img src=x onerror=alert(1)>\"&amp;'</script>{{7*7}}"

    def analyze(self, request: InferenceRequest) -> InferenceResult:
        return dataclasses.replace(super().analyze(request), request_id=self.response_id)


def test_a_hostile_response_id_is_returned_only_as_an_inert_json_string(
    database: Engine,
) -> None:
    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    run_id = submit(database, principal, submission(workspace), "markup-" + uuid4().hex)
    settle(database, MarkupProvider(workspace))
    action_id = first_action(database, principal, run_id)
    response = fetch(principal, action_path(run_id, action_id))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["action"]["proposal"]["producer"]["response_id"] == (
        MarkupProvider.response_id
    )
    # The stored text is not altered, escaped into HTML, or wrapped in markup by the API.
    assert not response.text.lstrip().startswith("<")
    run = fetch(principal, run_path(run_id)).json()
    assert run["actions"][0]["proposal"]["producer"]["response_id"] == MarkupProvider.response_id


# ---- no free text, no side effects, no audit -----------------------------------------

BODY_SENTINEL = "SENTINEL-SOURCE-BODY-91c3"
TITLE_SENTINEL = "SENTINEL-TICKET-TITLE-5d7e"
TICKET_BODY_SENTINEL = "SENTINEL-TICKET-BODY-2b8f"
EXPLANATION_SENTINEL = "SENTINEL-FINDING-EXPLANATION-6a40"
SUMMARY_SENTINEL = "SENTINEL-MODEL-SUMMARY-c19d"
AUDIT_SENTINEL = "SENTINEL-AUDIT-DETAIL-84e2"
SENTINELS = (
    BODY_SENTINEL,
    TITLE_SENTINEL,
    TICKET_BODY_SENTINEL,
    EXPLANATION_SENTINEL,
    SUMMARY_SENTINEL,
    AUDIT_SENTINEL,
)


class SentinelProvider(TicketProvider):
    def analyze(self, request: InferenceRequest) -> InferenceResult:
        base = super().analyze(request)
        assert base.analysis.proposal is not None
        proposal = base.analysis.proposal.model_copy(
            update={
                "arguments": TicketArguments(
                    workspace_id=self.target, title=TITLE_SENTINEL, body=TICKET_BODY_SENTINEL
                )
            }
        )
        analysis = Analysis(
            findings=[
                ModelFinding(
                    family="Tool Abuse",
                    evidence_id=request.envelope.source_id,
                    quote=BODY_SENTINEL,
                    explanation=EXPLANATION_SENTINEL,
                )
            ],
            uncertain=False,
            summary=SUMMARY_SENTINEL,
            proposal=proposal,
        )
        return dataclasses.replace(base, analysis=analysis)


FORBIDDEN_KEYS = {
    "content",
    "body",
    "title",
    "explanation",
    "quote",
    "summary",
    "analysis",
    "reasoning",
    "prompt",
    "raw_response",
    "sql",
    "detail",
}


def keys_of(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for item in value.values() for k in keys_of(item)}
    if isinstance(value, list):
        return {k for item in value for k in keys_of(item)}
    return set()


def test_no_free_text_reaches_any_lineage_response_header_or_log(
    database: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    principal, workspace = _workspace(database)
    source = f"Synthetic customer needs help. {BODY_SENTINEL} Please open one ticket."
    run_id = _accept(database, principal, workspace, source, "text/plain")
    settle(database, SentinelProvider(workspace))
    with database.begin() as connection:
        run = locked_run(connection, run_id)
        audit_event(connection, run, "SYNTHETIC_NOTE", {"note": AUDIT_SENTINEL}, principal)
    with database.connect() as connection:
        stored = connection.exec_driver_sql(
            "SELECT count(*) FROM findings WHERE run_id=%s AND explanation=%s",
            (run_id, EXPLANATION_SENTINEL),
        ).scalar_one()
    assert stored == 1, "the fixture must really store the finding explanation it forbids"

    caplog.set_level(logging.DEBUG)
    lineage = build_run_lineage(database, principal, run_id)
    assert lineage.actions, "the fixture must reach a stored action"
    paths = [
        run_path(run_id),
        node_path(run_id, raw_id(lineage.contents[0].id)),
        action_path(run_id, lineage.actions[0].action_id),
    ]
    for path in paths:
        response = fetch(principal, path)
        assert response.status_code == 200, path
        surface = response.text + json.dumps(dict(response.headers))
        for sentinel in SENTINELS:
            assert sentinel not in surface, (path, sentinel)
        assert not keys_of(response.json()) & FORBIDDEN_KEYS, path
    assert not any(sentinel in caplog.text for sentinel in SENTINELS)


def test_reads_have_no_side_effects_and_never_touch_audit_events(database: Engine) -> None:
    principal, run_id = completed(database)
    lineage = build_run_lineage(database, principal, run_id)
    before = snapshot_of_state(database, run_id)
    statements: list[str] = []
    for path in (
        run_path(run_id),
        node_path(run_id, raw_id(lineage.contents[0].id), "both"),
        action_path(run_id, lineage.actions[0].action_id),
    ):
        assert fetch(principal, path, statements=statements).status_code == 200
    assert snapshot_of_state(database, run_id) == before
    assert statements
    verbs = {statement.lstrip().split(None, 1)[0].upper() for statement in statements}
    assert verbs <= {"SELECT", "SET"}, verbs
    assert not any("audit_events" in statement for statement in statements)


def test_lineage_is_served_even_when_the_run_has_no_audit_events(database: Engine) -> None:
    principal, run_id = completed(database)
    lineage = build_run_lineage(database, principal, run_id)
    with database.begin() as connection:
        execute(connection, "ALTER TABLE audit_events DISABLE TRIGGER append_only_audit")
        execute(connection, "DELETE FROM audit_events WHERE run_id=:r", {"r": run_id})
        execute(connection, "ALTER TABLE audit_events ENABLE TRIGGER append_only_audit")
    assert (
        fetch_scalar(database, "SELECT count(*) FROM audit_events WHERE run_id=:r", {"r": run_id})
        == 0
    )
    status, body = get(principal, run_path(run_id))
    assert status == 200 and body["actions"][0]["stage"] == "verified"
    assert body["integrity"] == []
    assert get(principal, node_path(run_id, raw_id(lineage.contents[0].id)))[0] == 200
    assert get(principal, action_path(run_id, lineage.actions[0].action_id))[0] == 200


# ---- ordering and determinism -----------------------------------------------------------


def test_serialization_order_is_explicit_and_repeatable(database: Engine) -> None:
    opened = awaiting_review(database)
    assert decide(opened["reviewer"], opened["review_id"], opened["digest"])[0] == 200
    settle(database, TicketProvider(UUID(opened["workspace"])))
    first = get(opened["owner"], run_path(opened["run_id"]))[1]
    second = get(opened["owner"], run_path(opened["run_id"]))[1]
    assert stable(first) == stable(second)
    assert [d["ordinal"] for d in first["actions"][0]["decisions"]] == [1, 2]
    relationships = [
        (r["kind"], r["source"], r["target"] or "", r["basis"]) for r in first["relationships"]
    ]
    assert relationships == sorted(relationships)
    integrity = [(i["code"], i["subject"], i["status"]) for i in first["integrity"]]
    assert integrity == sorted(integrity)

    principal, run_id = derived_run(database)
    chain = get(principal, run_path(run_id))[1]
    contents = [(c["created_at"], c["id"]) for c in chain["contents"]]
    assert contents == sorted(contents)
    for edge in chain["edges"]:
        assert [s["index"] for s in edge["steps"]] == list(range(1, len(edge["steps"]) + 1))
    leaf = next(c for c in chain["contents"] if not c["is_source"])
    walk = get(principal, node_path(run_id, raw_id(leaf["id"]), "ancestors"))[1]["ancestors"]
    assert walk["nodes"] == sorted(walk["nodes"], key=lambda item: (item[1], item[0]))


# ---- OpenAPI, application wiring, authority boundary --------------------------------


def test_openapi_describes_the_typed_inputs_and_responses_without_a_second_schema() -> None:
    schema = make_app().openapi()
    base = "/api/v1/runs/{run_id}/lineage"
    expected = {
        base: "RunLineage",
        base + "/nodes/{node_id}": "NodeLineageView",
        base + "/actions/{action_id}": "ActionLineageView",
    }
    for path, model in expected.items():
        assert set(schema["paths"][path]) == {"get"}, path
        operation = schema["paths"][path]["get"]
        reference = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert reference.endswith(f"/{model}"), path
        assert model in schema["components"]["schemas"]
    node = schema["paths"][base + "/nodes/{node_id}"]["get"]
    query = [p for p in node["parameters"] if p["in"] == "query"]
    assert [p["name"] for p in query] == ["direction"]
    assert query[0]["schema"]["enum"] == ["ancestors", "descendants", "both"]
    for path in (base, base + "/actions/{action_id}"):
        operation = schema["paths"][path]["get"]
        assert [p for p in operation["parameters"] if p["in"] == "query"] == []
    # No route accepts any depth, limit, page size or bound switch.
    names = {p["name"] for path in expected for p in schema["paths"][path]["get"]["parameters"]}
    assert names == {"run_id", "node_id", "action_id", "direction"}
    codes = schema["components"]["schemas"]["IntegrityFinding"]["properties"]["code"]["enum"]
    assert "bound_exceeded" in codes and "source_missing_retention_unverifiable" in codes


def test_the_lineage_routes_are_exactly_three_gets_with_no_write_methods() -> None:
    routes = {
        (method, route.path)  # type: ignore[attr-defined]
        for route in lineage_routes.router.routes
        for method in route.methods  # type: ignore[attr-defined]
    }
    assert routes == {
        ("GET", "/api/v1/runs/{run_id}/lineage"),
        ("GET", "/api/v1/runs/{run_id}/lineage/nodes/{node_id}"),
        ("GET", "/api/v1/runs/{run_id}/lineage/actions/{action_id}"),
    }


def test_an_unconfigured_database_is_the_existing_503() -> None:
    response = fetch("user_" + uuid4().hex, run_path(str(uuid4())), configured=False)
    assert response.status_code == 503
    body = response.json()
    assert (body["code"], body["retryable"]) == ("database_not_configured", True)
    assert response.headers["cache-control"] == "no-store"


def imports_of(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_the_routes_decide_nothing_and_hold_no_lineage_semantics() -> None:
    source = inspect.getsource(lineage_routes)
    for forbidden in ("SELECT", "audit_events", "retention", "visible_run", "traverse"):
        assert forbidden not in source, forbidden
    assert not imports_of(lineage_routes) & {"vetoq.lineage_assemble", "vetoq.lineage_graph"}
    assert "visible_run(" in inspect.getsource(lineage_read.build_run_lineage)
    views = inspect.getsource(lineage_views)
    assert "audit_events" not in views and "SELECT" not in views


def test_authority_code_never_depends_on_the_lineage_api_or_views() -> None:
    read_side = {
        "vetoq.lineage_read",
        "vetoq.lineage_views",
        "vetoq.lineage_routes",
        "vetoq.lineage_assemble",
        "vetoq.lineage_graph",
        "vetoq.lineage_model",
        "vetoq.routes",
        "vetoq.main",
    }
    for module in (action_guard, workflow):
        assert not imports_of(module) & read_side, module.__name__
    assert not {name for name in action_guard.GuardInput.__dataclass_fields__ if "lineage" in name}
    assert "lineage" not in inspect.getsource(action_guard)
    assert "lineage_routes" not in inspect.getsource(workflow)
