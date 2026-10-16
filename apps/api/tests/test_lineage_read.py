"""M004 Slice D: the internal lineage read service against a real PostgreSQL database.

Every run is produced by the real workflow. The service is exercised directly here. The
lineage HTTP routes are covered in `test_lineage_api.py`. Fixtures are labeled synthetic test
data, never operational metrics.
"""

import ast
import base64
import inspect
import os
import sys
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, event, text
from sqlalchemy.exc import DBAPIError
from test_database_integration import (
    TicketProvider,
    awaiting_review,
    decide,
    provision,
    submission,
)
from test_ingestion_pipeline import _accept, _workspace

from vetoq import (
    action_guard,
    cli,
    lineage_assemble,
    lineage_graph,
    lineage_model,
    lineage_read,
    visibility,
    workflow,
)
from vetoq.config import Settings
from vetoq.db import engine_for, execute, one
from vetoq.lineage_model import LineageBounds, RunLineage
from vetoq.lineage_read import build_action_lineage, build_node_lineage, build_run_lineage
from vetoq.workflow import DomainError, submit, tick

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
pytestmark = pytest.mark.integration

SOURCE_SENTINEL = "Synthetic customer cannot sign in after a password reset."
TICKET_SENTINEL = "Synthetic sign-in issue"


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
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


def settle(database: Engine, provider: TicketProvider, limit: int = 12) -> None:
    for _ in range(limit):
        if not tick(database, provider):
            return
    raise AssertionError("the run did not settle")


def legacy_run(database: Engine, source: str = SOURCE_SENTINEL) -> tuple[str, str, UUID]:
    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    request = submission(workspace).model_copy(update={"source": source})
    run_id = submit(database, principal, request, "lineage-" + uuid4().hex)
    return principal, run_id, workspace


def completed(database: Engine, source: str = SOURCE_SENTINEL) -> tuple[str, str]:
    principal, run_id, workspace = legacy_run(database, source)
    settle(database, TicketProvider(workspace))
    return principal, run_id


def snapshot_of_state(database: Engine, run_id: str) -> dict[str, Any]:
    """Everything a lineage read must leave untouched."""

    with database.connect() as connection:
        found = one(
            connection,
            """
            SELECT
              (SELECT state FROM runs WHERE id=:r) AS state,
              (SELECT failure FROM runs WHERE id=:r) AS failure,
              (SELECT writes FROM runs WHERE id=:r) AS writes,
              (SELECT count(*) FROM audit_events WHERE run_id=:r) AS audit,
              (SELECT count(*) FROM content_nodes WHERE run_id=:r) AS nodes,
              (SELECT count(*) FROM content_edges WHERE run_id=:r) AS edges,
              (SELECT count(*) FROM findings WHERE run_id=:r) AS findings,
              (SELECT count(*) FROM actions WHERE run_id=:r) AS actions,
              (SELECT count(*) FROM guard_decisions WHERE run_id=:r) AS decisions,
              (SELECT count(*) FROM reviews WHERE run_id=:r) AS reviews,
              (SELECT count(*) FROM executions WHERE run_id=:r) AS executions,
              (SELECT count(*) FROM tickets WHERE run_id=:r) AS tickets
            """,
            {"r": run_id},
        )
    assert found is not None
    return found


# ---- real workflow runs ----------------------------------------------------------------


def test_direct_allow_run_is_verified_with_current_writer_lineage(database: Engine) -> None:
    principal, run_id = completed(database)
    lineage = build_run_lineage(database, principal, run_id)
    action = lineage.actions[0]
    assert lineage.run.state == "COMPLETED"
    assert lineage.integrity == ()
    assert action.stage == "verified"
    assert action.path.complete is True
    assert [d.verdict for d in action.decisions] == ["ALLOW"]
    assert action.execution is not None
    assert action.execution.authorization == "consistent"
    assert action.execution.guard_decision_id == action.decisions[0].id.removeprefix(
        "guard_decision:"
    )
    producer = action.proposal.producer
    assert (producer.state, producer.provider, producer.model, producer.prompt_version) == (
        "recorded",
        "fixture",
        "fixture/structured",
        "fixture/1",
    )
    assert action.proposal.digest_check == "consistent"
    assert [e.resolution for e in action.proposal.evidence] == ["resolved"]
    assert lineage.source_binding.status == "consistent"
    assert lineage.retention.state == "available"
    # A legacy source row carries no media metadata and is reported as such.
    source = lineage.contents[0]
    assert (source.is_source, source.representation_kind, source.parser_state) == (
        True,
        None,
        "not_applicable",
    )


def test_lineage_carries_no_content_body_ticket_text_or_model_text(database: Engine) -> None:
    principal, run_id = completed(database)
    dumped = build_run_lineage(database, principal, run_id).model_dump_json()
    assert SOURCE_SENTINEL not in dumped
    assert TICKET_SENTINEL not in dumped
    assert "A synthetic customer cannot sign in" not in dumped


def test_m003_email_run_reports_the_parser_and_the_ordered_transform_steps(
    database: Engine,
) -> None:
    principal, workspace = _workspace(database)
    source = 'Content-Type: application/json\n\n{"b":1,"a":2}\n'
    run_id = _accept(database, principal, workspace, source, "message/rfc822")
    settle(database, TicketProvider(workspace))
    lineage = build_run_lineage(database, principal, run_id)
    assert lineage.integrity == ()
    child = next(
        c for c in lineage.contents if c.parser is not None and c.parser.id == "json_structured"
    )
    # The parser identity is one fact. The ordered edge steps are another.
    assert child.parser is not None and child.parser.id == "json_structured"
    assert child.parser_state == "recorded"
    assert child.representation_kind == "canonical_text"
    edge = next(e for e in lineage.edges if e.child_id == child.id)
    assert edge.steps_state == "recorded"
    assert edge.steps is not None
    assert [(s.index, s.transform, s.version) for s in edge.steps] == [
        (1, "email-part-decode", "1"),
        (2, "json-canonical", "1"),
    ]
    assert {(r.kind, r.basis) for r in lineage.relationships if r.kind == "derived_from"} == {
        ("derived_from", "structural_fk")
    }
    assert lineage.actions[0].path.complete is True


def test_legacy_source_run_derives_recorded_parser_and_steps(database: Engine) -> None:
    """The current pipeline records parser and steps even when the source row is legacy."""

    encoded = base64.b64encode(b"Synthetic decoded text for lineage.").decode()
    principal, run_id = completed(database, encoded)
    lineage = build_run_lineage(database, principal, run_id)
    child = next(c for c in lineage.contents if not c.is_source)
    assert child.origin == "derived" and child.parser_state == "recorded"
    assert child.parser is not None and child.parser.id == "bounded-decoder"
    assert [(e.steps_state, [s.transform for s in e.steps or ()]) for e in lineage.edges] == [
        ("recorded", ["base64"])
    ]
    assert lineage.integrity == ()


def test_review_run_reports_pending_then_approved_review_timeline(database: Engine) -> None:
    opened = awaiting_review(database)
    pending = build_run_lineage(database, opened["owner"], opened["run_id"])
    action = pending.actions[0]
    assert action.stage == "review_pending"
    assert action.review is not None
    assert action.review.requested_at is not None
    assert (action.review.decided_at, action.review.consumed_at) == (None, None)
    assert action.review.not_recorded == ()
    assert [d.verdict for d in action.decisions] == ["REVIEW"]
    assert action.decisions[0].review_id == action.review.id.removeprefix("review:")
    assert action.execution is None and action.ticket is None
    assert pending.integrity == ()

    assert decide(opened["reviewer"], opened["review_id"], opened["digest"])[0] == 200
    settle(database, TicketProvider(UUID(opened["workspace"])))
    done = build_run_lineage(database, opened["owner"], opened["run_id"])
    final = done.actions[0]
    assert final.stage == "verified"
    assert [d.ordinal for d in final.decisions] == [1, 2]
    assert [d.verdict for d in final.decisions] == ["REVIEW", "ALLOW"]
    assert {d.review_id for d in final.decisions} == {opened["review_id"]}
    review = final.review
    assert review is not None and review.consumed
    assert review.requested_at and review.decided_at and review.consumed_at
    assert review.requested_at <= review.decided_at <= review.consumed_at
    assert final.execution is not None and final.execution.authorization == "consistent"
    assert done.integrity == ()
    assert final.path.complete is True


def test_rejected_review_is_blocked_with_no_execution(database: Engine) -> None:
    opened = awaiting_review(database)
    assert decide(opened["reviewer"], opened["review_id"], opened["digest"], "reject")[0] == 200
    lineage = build_run_lineage(database, opened["owner"], opened["run_id"])
    action = lineage.actions[0]
    assert action.stage == "blocked"
    assert action.execution is None and action.ticket is None
    assert action.review is not None and action.review.decision == "reject"
    assert lineage.integrity == ()


def test_expired_undecided_review_is_reported_expired(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = awaiting_review(
        database, monkeypatch=monkeypatch, authorize_clock_lag=timedelta(minutes=30)
    )
    lineage = build_run_lineage(database, opened["owner"], opened["run_id"])
    assert lineage.actions[0].stage == "expired"


def test_same_tool_goal_lock_decisions_are_reported_and_authority_is_unchanged(
    database: Engine,
) -> None:
    principal = "user_" + uuid4().hex
    workspace_a, workspace_b = provision(database, principal)
    allowed = submit(database, principal, submission(workspace_a), "same-tool-a-" + uuid4().hex)
    settle(database, TicketProvider(workspace_a))
    denied = submit(database, principal, submission(workspace_a), "same-tool-b-" + uuid4().hex)
    settle(database, TicketProvider(workspace_b))

    ok = build_run_lineage(database, principal, allowed)
    assert [a.stage for a in ok.actions] == ["verified"]

    blocked = build_run_lineage(database, principal, denied)
    assert blocked.run.state == "BLOCKED"
    assert blocked.actions, "every evaluated action is reported"
    for action in blocked.actions:
        assert action.stage == "blocked"
        assert [d.verdict for d in action.decisions] == ["BLOCK"]
        assert "GOAL_SCOPE_MISMATCH" in action.decisions[0].reasons
        assert action.execution is None and action.ticket is None
    with database.connect() as connection:
        written = one(
            connection,
            "SELECT count(*) AS n FROM tickets WHERE workspace_id=:w",
            {"w": str(workspace_b)},
        )
    assert written == {"n": 0}


# ---- visibility and tenant isolation ----------------------------------------------------


def foreign_principal(database: Engine) -> str:
    outsider = "user_" + uuid4().hex
    provision(database, outsider)
    return outsider


def test_every_lookup_is_non_enumerating_for_a_foreign_principal(database: Engine) -> None:
    owner, run_id = completed(database)
    outsider = foreign_principal(database)
    lineage = build_run_lineage(database, owner, run_id)
    action_id = lineage.actions[0].action_id
    node_id = lineage.contents[0].id.removeprefix("content:")
    for call in (
        lambda: build_run_lineage(database, outsider, run_id),
        lambda: build_action_lineage(database, outsider, run_id, action_id),
        lambda: build_node_lineage(database, outsider, run_id, node_id),
        lambda: build_run_lineage(database, owner, str(uuid4())),
    ):
        with pytest.raises(DomainError) as refused:
            call()
        assert (refused.value.code, refused.value.status) == ("not_found", 404)


def test_inactive_membership_and_inactive_workspace_hide_the_run(database: Engine) -> None:
    owner, run_id = completed(database)
    workspace = str(
        fetch_scalar(database, "SELECT workspace_id FROM runs WHERE id=:r", {"r": run_id})
    )
    assert build_run_lineage(database, owner, run_id).run.run_id == run_id

    with database.begin() as connection:
        execute(
            connection,
            "UPDATE workspaces SET active=false WHERE id=:w",
            {"w": workspace},
        )
    with pytest.raises(DomainError, match="not_found"):
        build_run_lineage(database, owner, run_id)

    with database.begin() as connection:
        execute(connection, "UPDATE workspaces SET active=true WHERE id=:w", {"w": workspace})
        execute(
            connection,
            "UPDATE memberships SET active=false WHERE workspace_id=:w AND principal=:p",
            {"w": workspace, "p": owner},
        )
    with pytest.raises(DomainError, match="not_found"):
        build_run_lineage(database, owner, run_id)


def fetch_scalar(database: Engine, sql: str, params: dict[str, Any]) -> Any:
    with database.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def test_lineage_never_mixes_two_runs_and_lookups_stay_inside_the_trusted_run(
    database: Engine,
) -> None:
    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    first = submit(database, principal, submission(workspace), "iso-1-" + uuid4().hex)
    second = submit(database, principal, submission(workspace), "iso-2-" + uuid4().hex)
    settle(database, TicketProvider(workspace))
    one_lineage = build_run_lineage(database, principal, first)
    two_lineage = build_run_lineage(database, principal, second)

    def ids(lineage: RunLineage) -> set[str]:
        found = {c.id for c in lineage.contents}
        for action in lineage.actions:
            found |= {action.proposal.id}
            found |= {d.id for d in action.decisions}
            found |= {e.id for e in (action.execution, action.ticket, action.review) if e}
        return found

    assert ids(one_lineage).isdisjoint(ids(two_lineage))
    assert one_lineage.run.run_id == first and two_lineage.run.run_id == second

    foreign_node = two_lineage.contents[0].id.removeprefix("content:")
    foreign_action = two_lineage.actions[0].action_id
    for call in (
        lambda: build_node_lineage(database, principal, first, foreign_node),
        lambda: build_action_lineage(database, principal, first, foreign_action),
    ):
        with pytest.raises(DomainError, match="not_found"):
            call()


def test_node_lineage_is_bounded_and_scoped(database: Engine) -> None:
    principal, workspace = _workspace(database)
    source = "Content-Type: text/html\n\n<p>shown</p><script>hidden</script>\n"
    run_id = _accept(database, principal, workspace, source, "message/rfc822")
    settle(database, TicketProvider(workspace))
    lineage = build_run_lineage(database, principal, run_id)
    root = next(c for c in lineage.contents if c.is_source)
    leaf = next(c for c in lineage.contents if not c.is_source)
    top = build_node_lineage(database, principal, run_id, root.id.removeprefix("content:"))
    assert top.ancestors.nodes == ()
    assert {n for n, _ in top.descendants.nodes} == {
        c.id for c in lineage.contents if c is not root
    }
    assert top.citing_proposals == (lineage.actions[0].proposal.id,)
    bottom = build_node_lineage(database, principal, run_id, leaf.id.removeprefix("content:"))
    assert [n for n, _ in bottom.ancestors.nodes] == [root.id]
    assert bottom.citing_proposals == ()


# ---- bounds and retention against the real database ---------------------------------------


def test_caps_report_truncation_instead_of_silently_clipping(database: Engine) -> None:
    principal, workspace = _workspace(database)
    source = "Content-Type: text/html\n\n<p>shown</p><script>hidden</script>\n"
    run_id = _accept(database, principal, workspace, source, "message/rfc822")
    settle(database, TicketProvider(workspace))
    full = build_run_lineage(database, principal, run_id)
    assert full.bounds.truncated is False
    assert len(full.contents) >= 3

    small = build_run_lineage(
        database, principal, run_id, LineageBounds(max_nodes=1, max_edges=1, max_steps=1)
    )
    assert small.bounds.truncated is True
    assert set(small.bounds.truncated_sets) == {
        "content_nodes",
        "content_edges",
        "content_edge_steps",
    }
    assert len(small.contents) == 1
    assert {f.code for f in small.integrity} >= {"bound_exceeded"}
    assert small.retention.state == "unverifiable"
    assert small.bounds.caps.max_nodes == 1
    # Checks that need the whole graph are unverifiable, never falsely inconsistent.
    assert {f.status for f in small.integrity} == {"unverifiable"}


def test_documented_caps_cover_the_frozen_ingestion_budgets() -> None:
    from vetoq.ingestion.limits import BUDGETS

    caps = lineage_model.DEFAULT_BOUNDS
    assert caps.max_evidence_ids == BUDGETS.proposal_evidence_ids
    assert caps.max_actions >= 3  # a run permits at most three proposals
    assert caps.max_steps >= caps.max_edges * 4  # an edge records at most four steps


def lagged_run(database: Engine, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """A run whose original expired an hour ago by the retention clock, never touched."""

    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    real_now = workflow.now
    with monkeypatch.context() as patch:
        patch.setattr(workflow, "now", lambda: real_now() - timedelta(hours=25))
        run_id = submit(database, principal, submission(workspace), "lag-" + uuid4().hex)
    return principal, run_id


def immutability_trigger_enabled(database: Engine) -> bool:
    """`tgenabled = O` is origin/enabled. The production trigger must stay in that state."""

    with database.connect() as connection:
        state = connection.execute(
            text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'immutable_run'")
        ).scalar_one()
    return str(state) == "O"


def insert_aged_expired_source(database: Engine, *, hours: int = 25) -> tuple[str, str]:
    """A historical run whose `created_at` is already past eligibility, with an expired original.

    `created_at` is set on INSERT. `immutable_run` is an UPDATE/DELETE trigger and is not
    touched. The production immutability trigger stays enabled.
    """

    from datetime import UTC, datetime

    from vetoq.contracts import GoalLock
    from vetoq.inspection import content_digest

    assert immutability_trigger_enabled(database)
    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    run_id, source_id = str(uuid4()), str(uuid4())
    body = "Synthetic aged source for retention eligibility."
    envelope = GoalLock(
        principal=principal,
        workspace_id=workspace,
        source_id=UUID(source_id),
        source_digest=content_digest(body),
        goal="Synthetic aged goal.",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    with database.begin() as connection:
        execute(
            connection,
            """
            INSERT INTO runs(
              id,workspace_id,principal,submission_key,submission_digest,envelope,state,
              created_at,expires_at,complete
            ) VALUES(
              :id,:w,:p,:k,:d,CAST(:e AS jsonb),'COMPLETED',
              now()-make_interval(hours => :h),now()+interval '1 hour',true
            )
            """,
            {
                "id": run_id,
                "w": str(workspace),
                "p": principal,
                "k": "aged-" + uuid4().hex,
                "d": "a" * 64,
                "e": envelope.model_dump_json(),
                "h": hours,
            },
        )
        execute(
            connection,
            """
            INSERT INTO content_nodes(
              id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
            ) VALUES(
              :id,:w,:r,'pasted-email','synthetic',:digest,:content,'untrusted',true,
              now()-interval '1 hour'
            )
            """,
            {
                "id": source_id,
                "w": str(workspace),
                "r": run_id,
                "digest": content_digest(body),
                "content": body,
            },
        )
    assert immutability_trigger_enabled(database)
    return principal, run_id


def run_retain(database: Engine, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Run the real `vetoq retain` command and return every statement it executed."""

    settings = Settings(
        _env_file=None, environment="test", database_url=SecretStr(str(DATABASE_URL))
    )
    monkeypatch.setattr(sys, "argv", ["vetoq", "retain"])
    monkeypatch.setattr("vetoq.cli.Settings", lambda: settings)
    monkeypatch.setattr("vetoq.cli.engine_for", lambda _settings: database)
    return captured(database, cli.main)


def test_source_present_is_available_and_after_expiry_pending_deletion(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    assert build_run_lineage(database, principal, run_id).retention.state == "available"

    principal, run_id = lagged_run(database, monkeypatch)
    pending = build_run_lineage(database, principal, run_id)
    assert pending.retention.state == "expired_body_pending_deletion"
    assert pending.retention.source_present is True
    assert pending.contents[0].body_state == "expired_body_pending_deletion"
    assert pending.integrity == ()


def test_source_absent_before_it_could_be_eligible_is_inconsistent_after_real_retain(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The original expired by the retention clock, but the run is minutes old.
    principal, run_id = lagged_run(database, monkeypatch)
    before = snapshot_of_state(database, run_id)
    run_retain(database, monkeypatch)
    after = build_run_lineage(database, principal, run_id)
    assert snapshot_of_state(database, run_id)["nodes"] == 0 < before["nodes"]
    assert after.retention.state == "inconsistent"
    found = {(f.code, f.status) for f in after.integrity}
    assert ("source_missing_before_retention", "inconsistent") in found
    assert not any(f.code == "source_missing_retention_unverifiable" for f in after.integrity)


def test_eligible_source_absent_after_real_retain_is_unverifiable_not_removed_by_retention(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = insert_aged_expired_source(database)
    before = snapshot_of_state(database, run_id)
    assert build_run_lineage(database, principal, run_id).retention.state == (
        "expired_body_pending_deletion"
    )
    assert immutability_trigger_enabled(database)

    statements = run_retain(database, monkeypatch)

    # `retain` leaves nothing durable: it only deletes. Its statements never write a marker,
    # and no audit row, run field, or other table changes except through the delete cascade.
    assert statements and all(s.lstrip().upper().startswith("DELETE") for s in statements)
    after_state = snapshot_of_state(database, run_id)
    assert after_state["nodes"] == 0 < before["nodes"]
    assert {
        key: after_state[key] for key in after_state if key not in {"nodes", "edges", "findings"}
    } == {key: before[key] for key in before if key not in {"nodes", "edges", "findings"}}

    lineage = build_run_lineage(database, principal, run_id)
    assert lineage.retention.state == "unverifiable"
    assert str(lineage.retention.state) != "removed_by_retention"
    found = {(f.code, f.status) for f in lineage.integrity}
    assert found == {("source_missing_retention_unverifiable", "unverifiable")}
    # No deleted graph is invented. The Goal Lock facts remain and are presented as stored.
    assert (lineage.contents, lineage.edges, lineage.findings) == ((), (), ())
    assert lineage.goal_lock.valid and lineage.goal_lock.source_id is not None
    assert lineage.source_binding.status == "unverifiable"
    assert immutability_trigger_enabled(database)


# ---- snapshot, read-only, independence ----------------------------------------------------


def test_read_is_one_repeatable_read_only_snapshot(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id, _ = legacy_run(database)
    real = visibility.visible_run

    def with_concurrent_change(connection: Connection, run: str, who: str) -> dict[str, Any]:
        found = real(connection, run, who)
        # Another connection commits after this snapshot was taken.
        with database.begin() as other:
            execute(other, "UPDATE runs SET state='CANCELLED' WHERE id=:r", {"r": run})
        return found

    monkeypatch.setattr("vetoq.lineage_read.visible_run", with_concurrent_change)
    seen = build_run_lineage(database, principal, run_id)
    monkeypatch.setattr("vetoq.lineage_read.visible_run", real)
    assert seen.run.state == "QUEUED"
    assert build_run_lineage(database, principal, run_id).run.state == "CANCELLED"


def test_the_snapshot_transaction_is_read_only(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id, _ = legacy_run(database)
    before = snapshot_of_state(database, run_id)

    def attempt_write(connection: Connection, *_: Any) -> Any:
        execute(connection, "UPDATE runs SET state='CANCELLED' WHERE id=:r", {"r": run_id})

    monkeypatch.setattr(lineage_read, "read_snapshot", attempt_write)
    with pytest.raises(DBAPIError, match="read-only"):
        build_run_lineage(database, principal, run_id)
    assert snapshot_of_state(database, run_id) == before


def test_a_failed_read_changes_no_state_and_adds_no_failure_code(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, run_id = completed(database)
    before = snapshot_of_state(database, run_id)

    def explode(*_: Any) -> Any:
        raise RuntimeError("synthetic read failure")

    monkeypatch.setattr(lineage_read, "read_snapshot", explode)
    with pytest.raises(RuntimeError, match="synthetic read failure"):
        build_run_lineage(database, principal, run_id)
    assert snapshot_of_state(database, run_id) == before
    assert before["failure"] is None


def test_a_successful_read_writes_nothing(database: Engine) -> None:
    principal, run_id = completed(database)
    before = snapshot_of_state(database, run_id)
    build_run_lineage(database, principal, run_id)
    assert snapshot_of_state(database, run_id) == before


def captured(database: Engine, call: Callable[[], object]) -> list[str]:
    statements: list[str] = []

    def record(_c: Any, _cur: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(database, "before_cursor_execute", record)
    try:
        call()
    finally:
        event.remove(database, "before_cursor_execute", record)
    return statements


def test_lineage_never_reads_audit_events(database: Engine) -> None:
    principal, run_id = completed(database)
    statements = captured(database, lambda: build_run_lineage(database, principal, run_id))
    assert statements and not any("audit_events" in s for s in statements)
    for module in (lineage_read, lineage_assemble, lineage_graph, lineage_model):
        source = inspect.getsource(module)
        assert "audit_events" not in source.replace("audit events", "")


def test_query_count_is_fixed_and_independent_of_run_size(database: Engine) -> None:
    small_principal, small_run = completed(database)
    principal, workspace = _workspace(database)
    source = "Content-Type: text/html\n\n<p>shown</p><script>hidden</script>\n"
    big_run = _accept(database, principal, workspace, source, "message/rfc822")
    settle(database, TicketProvider(workspace))
    few = captured(database, lambda: build_run_lineage(database, small_principal, small_run))
    many = captured(database, lambda: build_run_lineage(database, principal, big_run))
    assert len(few) == len(many)
    # transaction mode, run visibility, read time, and nine capped sets
    assert len(few) == 12
    assert not any("WITH RECURSIVE" in s.upper() for s in few)
    assert all("run_id" in s or "runs" in s or "now()" in s or "TRANSACTION" in s for s in few)


# ---- authority boundary ---------------------------------------------------------------


def imported_modules(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_authority_code_never_imports_the_lineage_read_side() -> None:
    lineage_modules = {
        "vetoq.lineage_read",
        "vetoq.lineage_assemble",
        "vetoq.lineage_graph",
        "vetoq.lineage_model",
        "vetoq.lineage_views",
        "vetoq.lineage_routes",
        "vetoq.lineage_observe",
    }
    for module in (action_guard, workflow):
        assert not imported_modules(module) & lineage_modules


def test_model_is_never_an_input_to_the_guard() -> None:
    fields = set(action_guard.GuardInput.__dataclass_fields__)
    assert not {name for name in fields if "lineage" in name or "integrity" in name}
