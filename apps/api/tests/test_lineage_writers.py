"""M004 Slice C1: runtime lineage writers against schema 0005.

Every test runs the real workflow against a disposable PostgreSQL database. The
database is still tolerant in this slice. These tests prove that the application
writes the structure the strict `0006` rules will later require, and that
lineage never influences an authorization decision.
"""

import ast
import inspect
import os
from collections.abc import Callable, Iterator
from dataclasses import replace
from threading import Event, Thread
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
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import DBAPIError
from test_database_integration import (
    TicketProvider,
    TimeoutProvider,
    awaiting_review,
    decide,
    provision,
    submission,
)

from vetoq import action_guard, workflow
from vetoq.config import Settings
from vetoq.contracts import GUARD_VERSION, POLICY, GoalLock, ModelFinding, Proposal
from vetoq.contracts import action_digest as compute_action_digest
from vetoq.db import engine_for, execute, one, rows
from vetoq.providers.base import InferenceRequest, InferenceResult
from vetoq.workflow import DomainError, submit, tick

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
pytestmark = pytest.mark.integration


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def settle(database: Engine, provider: TicketProvider, limit: int = 12) -> None:
    """Tick until the worker has nothing eligible left."""

    for _ in range(limit):
        if not tick(database, provider):
            return
    raise AssertionError("the run did not settle")


def start(database: Engine, key: str) -> tuple[str, UUID, UUID]:
    principal = "user_" + uuid4().hex
    workspace_a, workspace_b = provision(database, principal)
    run_id = submit(database, principal, submission(workspace_a), key + uuid4().hex)
    return run_id, workspace_a, workspace_b


def decisions(database: Engine, run_id: str) -> list[dict[str, Any]]:
    with database.connect() as connection:
        return rows(
            connection,
            """
            SELECT d.* FROM guard_decisions d JOIN actions a ON a.id=d.action_id
            WHERE d.run_id=:r ORDER BY a.created_at,a.id,d.ordinal
            """,
            {"r": run_id},
        )


def counts(database: Engine, run_id: str) -> dict[str, int]:
    with database.connect() as connection:
        found = one(
            connection,
            """
            SELECT
              (SELECT count(*) FROM actions WHERE run_id=:r) AS actions,
              (SELECT count(*) FROM guard_decisions WHERE run_id=:r) AS decisions,
              (SELECT count(*) FROM reviews WHERE run_id=:r) AS reviews,
              (SELECT count(*) FROM tickets WHERE run_id=:r) AS tickets,
              (SELECT count(*) FROM executions WHERE run_id=:r) AS executions,
              (SELECT count(*) FROM findings WHERE run_id=:r AND origin='model') AS model_findings
            """,
            {"r": run_id},
        )
    assert found is not None
    return {key: int(value) for key, value in found.items()}


def run_state(database: Engine, run_id: str) -> dict[str, Any]:
    with database.connect() as connection:
        found = one(
            connection,
            "SELECT state,failure,writes,analysis FROM runs WHERE id=:r",
            {"r": run_id},
        )
    assert found is not None
    return found


def fetch(database: Engine, sql: str, **params: object) -> dict[str, Any]:
    with database.connect() as connection:
        found = one(connection, sql, params)
    assert found is not None
    return found


def foreign_source(database: Engine, same_workspace: UUID | None) -> str:
    """Return a real content node id that belongs to a different, cancelled run."""

    principal = "user_" + uuid4().hex
    workspace, _ = provision(database, principal)
    target = same_workspace or workspace
    if same_workspace is not None:
        with database.begin() as connection:
            execute(
                connection,
                """
                INSERT INTO memberships(workspace_id,principal,role)
                VALUES(:w,:p,'reviewer')
                """,
                {"w": str(target), "p": principal},
            )
    run_id = submit(database, principal, submission(target), "foreign-" + uuid4().hex)
    with database.begin() as connection:
        node = one(connection, "SELECT id FROM content_nodes WHERE run_id=:r", {"r": run_id})
        execute(
            connection,
            "UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL WHERE id=:r",
            {"r": run_id},
        )
    assert node is not None
    return str(node["id"])


class Variant(TicketProvider):
    """A fixture provider whose result fields or evidence the test controls."""

    def __init__(
        self,
        target: UUID,
        *,
        uncertain: bool = False,
        result: dict[str, Any] | None = None,
        evidence_ids: list[Any] | None = None,
        findings: list[ModelFinding] | None = None,
    ) -> None:
        super().__init__(target, uncertain=uncertain)
        self.result = result or {}
        self.evidence_ids = evidence_ids
        self.findings = findings

    def analyze(self, request: InferenceRequest) -> InferenceResult:
        base = super().analyze(request)
        proposal = base.analysis.proposal
        assert proposal is not None
        update: dict[str, Any] = {}
        if self.evidence_ids is not None:
            update["proposal"] = proposal.model_copy(update={"evidence_ids": self.evidence_ids})
        if self.findings is not None:
            update["findings"] = self.findings
        analysis = base.analysis.model_copy(update=update)
        return replace(base, analysis=analysis, **self.result)


def injecting(match: str, fake: Callable[[Callable[..., None], Any, str, Any], None]) -> Any:
    """Wrap `workflow.execute` so one statement shape is replaced by `fake`."""

    real = execute

    def wrapper(c: Connection, sql: str, params: Any = None) -> None:
        if match in sql:
            fake(real, c, sql, params)
            return
        real(c, sql, params)

    return wrapper


# ---------------------------------------------------------------------------
# Guard decision writer
# ---------------------------------------------------------------------------


def test_guard_version_is_one_server_side_label() -> None:
    assert GUARD_VERSION == "action-guard/1"
    source = inspect.getsource(workflow)
    assert source.count("action-guard/1") == 0
    assert "GUARD_VERSION" in source


def test_direct_allow_records_one_decision_and_links_the_execution(database: Engine) -> None:
    run_id, workspace, _ = start(database, "allow-")
    settle(database, TicketProvider(workspace))
    found = decisions(database, run_id)
    assert len(found) == 1
    decision = found[0]
    action = fetch(
        database, "SELECT id,digest,verdict,reasons FROM actions WHERE run_id=:r", r=run_id
    )
    assert decision["ordinal"] == 1
    assert decision["verdict"] == "ALLOW"
    assert decision["reasons"] == ["WITHIN_CONFIRMED_AUTHORITY"] == action["reasons"]
    assert decision["action_id"] == action["id"]
    assert decision["action_digest"] == action["digest"]
    assert decision["policy_revision_observed"] == POLICY
    assert decision["guard_version"] == GUARD_VERSION
    assert decision["review_id"] is None
    assert decision["evaluated_at"] is not None
    execution = fetch(
        database, "SELECT guard_decision_id,verified_at FROM executions WHERE run_id=:r", r=run_id
    )
    assert execution["guard_decision_id"] == decision["id"]
    assert execution["verified_at"] is not None
    assert counts(database, run_id) == {
        "actions": 1,
        "decisions": 1,
        "reviews": 0,
        "tickets": 1,
        "executions": 1,
        "model_findings": 0,
    }
    assert run_state(database, run_id)["state"] == "COMPLETED"


def test_authorization_and_verification_stay_distinct_steps(database: Engine) -> None:
    run_id, workspace, _ = start(database, "distinct-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)  # proposed
    assert tick(database, provider)  # authorized and executed
    after_authorization = fetch(
        database,
        """
        SELECT r.state,e.guard_decision_id,e.verified_at FROM runs r
        JOIN executions e ON e.run_id=r.id WHERE r.id=:r
        """,
        r=run_id,
    )
    assert after_authorization["state"] == "VERIFYING"
    assert after_authorization["guard_decision_id"] is not None
    assert after_authorization["verified_at"] is None
    assert tick(database, provider)  # verified
    verified = fetch(database, "SELECT verified_at FROM executions WHERE run_id=:r", r=run_id)
    assert verified["verified_at"] is not None


def test_direct_block_records_one_decision_and_no_side_effect(database: Engine) -> None:
    run_id, workspace, _ = start(database, "block-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE workspaces SET policy_revision='other/1' WHERE id=:w",
            {"w": str(workspace)},
        )
    assert tick(database, provider)
    found = decisions(database, run_id)
    assert len(found) == 1
    action = fetch(database, "SELECT digest,verdict,reasons FROM actions WHERE run_id=:r", r=run_id)
    assert found[0]["ordinal"] == 1
    assert found[0]["verdict"] == "BLOCK" == action["verdict"]
    assert found[0]["reasons"] == ["POLICY_UNAVAILABLE_OR_STALE"] == action["reasons"]
    assert found[0]["policy_revision_observed"] == "other/1"
    assert found[0]["action_digest"] == action["digest"]
    assert found[0]["review_id"] is None
    assert found[0]["guard_version"] == GUARD_VERSION
    assert counts(database, run_id) == {
        "actions": 1,
        "decisions": 1,
        "reviews": 0,
        "tickets": 0,
        "executions": 0,
        "model_findings": 0,
    }
    assert run_state(database, run_id)["state"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Review lifecycle
# ---------------------------------------------------------------------------


def test_review_then_approval_then_allow_records_exact_linkage(database: Engine) -> None:
    opened = awaiting_review(database)
    run_id, review_id = opened["run_id"], opened["review_id"]
    first = decisions(database, run_id)
    assert len(first) == 1
    assert (first[0]["ordinal"], first[0]["verdict"]) == (1, "REVIEW")
    assert first[0]["review_id"] == review_id
    assert first[0]["reasons"] == ["MATERIAL_UNCERTAINTY"]
    pending = fetch(
        database,
        "SELECT requested_at,decided_at,consumed,consumed_at FROM reviews WHERE id=:i",
        i=review_id,
    )
    assert pending["requested_at"] is not None
    assert pending["decided_at"] is None
    assert pending["consumed"] is False
    assert pending["consumed_at"] is None

    assert decide(opened["reviewer"], review_id, opened["digest"]) == (200, "AUTHORIZING")
    decided = fetch(
        database,
        "SELECT decision,reviewer,decided_at,consumed_at FROM reviews WHERE id=:i",
        i=review_id,
    )
    assert decided["decision"] == "approve"
    assert decided["reviewer"] == opened["reviewer"]
    assert decided["decided_at"] is not None
    assert decided["consumed_at"] is None
    # A second decision attempt is stale and must not rewrite the timestamp.
    assert decide(opened["reviewer"], review_id, opened["digest"]) == (409, "review_stale")
    assert (
        fetch(database, "SELECT decided_at FROM reviews WHERE id=:i", i=review_id)["decided_at"]
        == decided["decided_at"]
    )

    settle(database, TicketProvider(UUID(opened["workspace"]), uncertain=True))
    both = decisions(database, run_id)
    assert [(d["ordinal"], d["verdict"]) for d in both] == [(1, "REVIEW"), (2, "ALLOW")]
    assert both[1]["review_id"] == review_id
    assert both[1]["reasons"] == ["WITHIN_CONFIRMED_AUTHORITY"]
    assert both[0]["id"] != both[1]["id"]
    review = fetch(
        database,
        """
        SELECT requested_at,decided_at,consumed,consumed_at,
               requested_at<=decided_at AS ordered,decided_at<=consumed_at AS consumed_after
        FROM reviews WHERE id=:i
        """,
        i=review_id,
    )
    assert review["consumed"] is True
    assert review["consumed_at"] is not None
    assert review["ordered"] is True and review["consumed_after"] is True
    execution = fetch(
        database, "SELECT guard_decision_id,verified_at FROM executions WHERE run_id=:r", r=run_id
    )
    assert execution["guard_decision_id"] == both[1]["id"]
    assert execution["guard_decision_id"] != both[0]["id"]
    assert execution["verified_at"] is not None


def test_review_then_approval_then_revalidation_block_records_the_same_review(
    database: Engine,
) -> None:
    opened = awaiting_review(database)
    run_id, review_id = opened["run_id"], opened["review_id"]
    assert decide(opened["reviewer"], review_id, opened["digest"]) == (200, "AUTHORIZING")
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE memberships SET active=false WHERE workspace_id=:w AND principal=:p",
            {"w": opened["workspace"], "p": opened["reviewer"]},
        )
    settle(database, TicketProvider(UUID(opened["workspace"]), uncertain=True))
    both = decisions(database, run_id)
    assert [(d["ordinal"], d["verdict"]) for d in both] == [(1, "REVIEW"), (2, "BLOCK")]
    assert both[0]["review_id"] == both[1]["review_id"] == review_id
    assert both[1]["reasons"] == ["APPROVAL_INVALID_OR_STALE"]
    review = fetch(
        database,
        "SELECT decision,decided_at,consumed,consumed_at FROM reviews WHERE id=:i",
        i=review_id,
    )
    # Existing semantics: only an approval that proceeds to execution is consumed.
    assert review["decision"] == "approve"
    assert review["decided_at"] is not None
    assert review["consumed"] is False
    assert review["consumed_at"] is None
    assert counts(database, run_id)["tickets"] == 0
    assert counts(database, run_id)["executions"] == 0
    assert run_state(database, run_id)["state"] == "BLOCKED"


def test_review_rejection_adds_no_decision_and_no_execution(database: Engine) -> None:
    opened = awaiting_review(database)
    run_id, review_id = opened["run_id"], opened["review_id"]
    assert decide(opened["reviewer"], review_id, opened["digest"], "reject") == (200, "BLOCKED")
    settle(database, TicketProvider(UUID(opened["workspace"]), uncertain=True))
    only = decisions(database, run_id)
    assert [(d["ordinal"], d["verdict"]) for d in only] == [(1, "REVIEW")]
    review = fetch(
        database,
        "SELECT decision,reviewer,requested_at,decided_at,consumed,consumed_at FROM reviews "
        "WHERE id=:i",
        i=review_id,
    )
    assert review["decision"] == "reject"
    assert review["reviewer"] == opened["reviewer"]
    assert review["requested_at"] is not None and review["decided_at"] is not None
    assert review["consumed"] is False and review["consumed_at"] is None
    assert counts(database, run_id) == {
        "actions": 1,
        "decisions": 1,
        "reviews": 1,
        "tickets": 0,
        "executions": 0,
        "model_findings": 0,
    }
    assert run_state(database, run_id)["state"] == "BLOCKED"


def test_expired_review_adds_no_evaluation_and_no_side_effect(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    opened = awaiting_review(
        database, monkeypatch=monkeypatch, authorize_clock_lag=timedelta(minutes=15)
    )
    run_id = opened["run_id"]
    assert decide(opened["reviewer"], opened["review_id"], opened["digest"]) == (
        409,
        "review_stale",
    )
    settle(database, TicketProvider(UUID(opened["workspace"]), uncertain=True))
    only = decisions(database, run_id)
    assert [(d["ordinal"], d["verdict"]) for d in only] == [(1, "REVIEW")]
    review = fetch(
        database,
        "SELECT requested_at,decision,decided_at,consumed_at FROM reviews WHERE id=:i",
        i=opened["review_id"],
    )
    assert review["requested_at"] is not None
    assert review["decision"] is None and review["decided_at"] is None
    assert review["consumed_at"] is None
    assert counts(database, run_id)["tickets"] == 0
    assert counts(database, run_id)["executions"] == 0
    assert run_state(database, run_id)["state"] == "EXPIRED"


def test_new_executions_never_lack_their_authorization_link(database: Engine) -> None:
    created = []
    for key in ("link-a-", "link-b-"):
        run_id, workspace, _ = start(database, key)
        settle(database, TicketProvider(workspace))
        created.append(run_id)
    opened = awaiting_review(database)
    decide(opened["reviewer"], opened["review_id"], opened["digest"])
    settle(database, TicketProvider(UUID(opened["workspace"]), uncertain=True))
    created.append(opened["run_id"])
    for run_id in created:
        link = fetch(
            database,
            """
            SELECT e.guard_decision_id,d.verdict,d.action_digest=e.digest AS same_digest
            FROM executions e LEFT JOIN guard_decisions d ON d.id=e.guard_decision_id
            WHERE e.run_id=:r
            """,
            r=run_id,
        )
        assert link["guard_decision_id"] is not None
        assert link["verdict"] == "ALLOW"
        assert link["same_digest"] is True


# ---------------------------------------------------------------------------
# Producer provenance
# ---------------------------------------------------------------------------


def test_new_action_records_the_producer_that_made_it(database: Engine) -> None:
    run_id, workspace, _ = start(database, "producer-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)
    action = fetch(
        database,
        """
        SELECT proposal,digest,producer_provider,producer_model,producer_prompt_version,
               producer_response_id FROM actions WHERE run_id=:r
        """,
        r=run_id,
    )
    envelope = GoalLock.model_validate(
        fetch(database, "SELECT envelope FROM runs WHERE id=:r", r=run_id)["envelope"]
    )
    assert action["producer_provider"] == "fixture"
    assert action["producer_model"] == "fixture/structured"
    assert action["producer_prompt_version"] == "fixture/1"
    assert UUID(action["producer_response_id"])
    # The digest binds the action contract only; producer metadata is not part of it.
    assert action["digest"] == compute_action_digest(
        run_id, envelope, Proposal.model_validate(action["proposal"])
    )
    for assignment in (
        "producer_provider='changed'",
        "producer_model='changed'",
        "producer_prompt_version='changed'",
        "producer_response_id='changed'",
        "producer_response_id=NULL",
    ):
        with pytest.raises(DBAPIError, match="immutable_action"):
            with database.begin() as connection:
                execute(
                    connection, f"UPDATE actions SET {assignment} WHERE run_id=:r", {"r": run_id}
                )
    settle(database, provider)
    assert run_state(database, run_id)["state"] == "COMPLETED"


@pytest.mark.parametrize(
    ("request_id", "stored"),
    [
        ("resp_abc123", "resp_abc123"),
        ("  resp_padded  ", "resp_padded"),
        ("", None),
        ("   ", None),
        ("x" * 201, None),
        ("x" * 200, "x" * 200),
    ],
)
def test_response_id_is_normalized_and_never_a_meaningless_identifier(
    database: Engine, request_id: str, stored: str | None
) -> None:
    run_id, workspace, _ = start(database, "response-id-")
    assert tick(database, Variant(workspace, result={"request_id": request_id}))
    action = fetch(
        database,
        """
        SELECT producer_provider,producer_model,producer_prompt_version,producer_response_id
        FROM actions WHERE run_id=:r
        """,
        r=run_id,
    )
    assert action["producer_response_id"] == stored
    assert action["producer_provider"] == "fixture"
    assert action["producer_model"] == "fixture/structured"
    assert action["producer_prompt_version"] == "fixture/1"


@pytest.mark.parametrize(
    "override",
    [
        {"provider": ""},
        {"model": "  "},
        {"prompt_version": ""},
        {"model": " padded"},
        {"provider": "p" * 121},
    ],
)
def test_a_missing_producer_trio_fails_closed_without_an_action(
    database: Engine, override: dict[str, Any]
) -> None:
    run_id, workspace, _ = start(database, "trio-")
    assert tick(database, Variant(workspace, result=override))
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "lineage_write_failure")
    assert counts(database, run_id)["actions"] == 0
    assert counts(database, run_id)["decisions"] == 0


# ---------------------------------------------------------------------------
# Model evidence pre-validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind", ["missing", "cross_run", "cross_workspace", "too_many", "malformed", "empty"]
)
def test_invalid_proposal_evidence_fails_the_run_without_persisting_anything(
    database: Engine, kind: str
) -> None:
    run_id, workspace, _ = start(database, "bad-proposal-evidence-")
    with database.begin() as connection:
        source = one(connection, "SELECT id FROM content_nodes WHERE run_id=:r", {"r": run_id})
    assert source is not None
    evidence: list[Any]
    if kind == "missing":
        evidence = [UUID(str(source["id"])), uuid4()]
    elif kind == "cross_run":
        evidence = [UUID(foreign_source(database, workspace))]
    elif kind == "cross_workspace":
        evidence = [UUID(foreign_source(database, None))]
    elif kind == "too_many":
        evidence = [UUID(str(source["id"]))] * 17
    elif kind == "malformed":
        evidence = ["not-a-uuid"]
    else:
        evidence = []
    assert tick(database, Variant(workspace, evidence_ids=evidence))
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "invalid_model_evidence")
    assert state["analysis"] is None
    assert counts(database, run_id) == {
        "actions": 0,
        "decisions": 0,
        "reviews": 0,
        "tickets": 0,
        "executions": 0,
        "model_findings": 0,
    }
    with database.connect() as connection:
        modeled = rows(
            connection,
            "SELECT type FROM audit_events WHERE run_id=:r AND type IN "
            "('MODEL_COMPLETED','ACTION_PROPOSED')",
            {"r": run_id},
        )
    assert modeled == []


def test_duplicate_proposal_evidence_is_tolerated_and_never_rewritten(database: Engine) -> None:
    run_id, workspace, _ = start(database, "duplicate-evidence-")
    with database.begin() as connection:
        source = one(connection, "SELECT id FROM content_nodes WHERE run_id=:r", {"r": run_id})
    assert source is not None
    node = UUID(str(source["id"]))
    assert tick(database, Variant(workspace, evidence_ids=[node, node, node]))
    stored = fetch(database, "SELECT proposal FROM actions WHERE run_id=:r", r=run_id)
    assert stored["proposal"]["evidence_ids"] == [str(node)] * 3


@pytest.mark.parametrize("kind", ["missing", "cross_run", "cross_workspace", "quote_absent"])
def test_invalid_finding_evidence_is_malformed_evidence_not_a_worker_failure(
    database: Engine, kind: str
) -> None:
    run_id, workspace, _ = start(database, "bad-finding-evidence-")
    with database.begin() as connection:
        source = one(connection, "SELECT id FROM content_nodes WHERE run_id=:r", {"r": run_id})
    assert source is not None
    node = UUID(str(source["id"]))
    target = {
        "missing": uuid4(),
        "cross_run": UUID(foreign_source(database, workspace)),
        "cross_workspace": UUID(foreign_source(database, None)),
        "quote_absent": node,
    }[kind]
    quote = "text that the source does not contain" if kind == "quote_absent" else "Synthetic"
    finding = ModelFinding(
        family="Instruction Override",
        evidence_id=target,
        quote=quote,
        explanation="Synthetic finding for the evidence pre-check.",
    )
    assert tick(database, Variant(workspace, findings=[finding]))
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "invalid_model_evidence")
    assert state["analysis"] is None
    assert counts(database, run_id) == {
        "actions": 0,
        "decisions": 0,
        "reviews": 0,
        "tickets": 0,
        "executions": 0,
        "model_findings": 0,
    }


def test_a_valid_model_finding_is_still_persisted_with_its_offsets(database: Engine) -> None:
    run_id, workspace, _ = start(database, "valid-finding-")
    with database.begin() as connection:
        source = one(connection, "SELECT id FROM content_nodes WHERE run_id=:r", {"r": run_id})
    assert source is not None
    finding = ModelFinding(
        family="Instruction Override",
        evidence_id=UUID(str(source["id"])),
        quote="Synthetic customer",
        explanation="Synthetic finding that is anchored in the source.",
    )
    assert tick(database, Variant(workspace, findings=[finding]))
    stored = fetch(
        database,
        "SELECT node_id,start_offset,end_offset,version FROM findings "
        "WHERE run_id=:r AND origin='model'",
        r=run_id,
    )
    assert stored == {
        "node_id": str(source["id"]),
        "start_offset": 0,
        "end_offset": len("Synthetic customer"),
        "version": "fixture/1",
    }
    assert counts(database, run_id)["actions"] == 1


# ---------------------------------------------------------------------------
# Fail-closed transactions
# The failure-boundary tests (which database errors are `lineage_write_failure`) live in
# `test_lineage_failure_boundary.py`.
# ---------------------------------------------------------------------------


def test_provider_and_evidence_failures_are_not_lineage_failures(database: Engine) -> None:
    run_id, workspace, _ = start(database, "vocabulary-")
    assert tick(database, Variant(workspace, evidence_ids=[uuid4()]))
    assert run_state(database, run_id)["failure"] == "invalid_model_evidence"
    other, _, _ = start(database, "vocabulary-timeout-")
    assert tick(database, TimeoutProvider())
    assert run_state(database, other)["failure"] == "provider_timeout"


# ---------------------------------------------------------------------------
# Retry, reclaim, and ordinals
# ---------------------------------------------------------------------------


def test_a_rolled_back_authorization_leaves_no_ordinal_hole_and_retries_cleanly(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, workspace, _ = start(database, "no-hole-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)

    def lost_ownership(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        raise DomainError("stale_worker")

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting("INSERT INTO tickets", lost_ownership))
        assert tick(database, provider) is False
    assert counts(database, run_id)["decisions"] == 0
    assert run_state(database, run_id)["state"] == "AUTHORIZING"
    assert tick(database, provider)
    found = decisions(database, run_id)
    assert [(d["ordinal"], d["verdict"]) for d in found] == [(1, "ALLOW")]
    assert counts(database, run_id)["tickets"] == 1


def test_reclaim_after_a_committed_authorization_adds_no_duplicate_decision(
    database: Engine,
) -> None:
    run_id, workspace, _ = start(database, "reclaim-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)
    assert tick(database, provider)
    first = decisions(database, run_id)
    assert len(first) == 1
    # A new worker reclaims the committed run, verifies it, and finds nothing else to do.
    assert tick(database, provider)
    assert tick(database, provider) is False
    assert tick(database, provider) is False
    assert decisions(database, run_id) == first
    assert counts(database, run_id)["tickets"] == 1


def test_open_review_reclaim_adds_no_duplicate_decision(database: Engine) -> None:
    opened = awaiting_review(database)
    provider = TicketProvider(UUID(opened["workspace"]), uncertain=True)
    before = decisions(database, opened["run_id"])
    assert tick(database, provider) is False
    assert tick(database, provider) is False
    assert decisions(database, opened["run_id"]) == before


def test_a_stale_worker_commits_no_lineage_after_losing_the_run(database: Engine) -> None:
    run_id, workspace, _ = start(database, "stale-lineage-")
    started, release = Event(), Event()

    class Hold(TicketProvider):
        def analyze(self, request: InferenceRequest) -> InferenceResult:
            started.set()
            assert release.wait(5)
            return replace(super().analyze(request), request_id="stale-worker-response")

    worker = Thread(target=tick, args=(database, Hold(workspace)))
    worker.start()
    assert started.wait(5)
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE runs SET lease_until=now()-interval '1 second' WHERE id=:r",
            {"r": run_id},
        )
    assert tick(database, TicketProvider(workspace))  # the new owner proposes first
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    stored = fetch(
        database,
        "SELECT count(*) AS n,max(producer_response_id) AS response FROM actions WHERE run_id=:r",
        r=run_id,
    )
    assert stored["n"] == 1
    assert stored["response"] != "stale-worker-response"
    assert counts(database, run_id)["decisions"] == 0


# ---------------------------------------------------------------------------
# Same-tool Goal Lock regression: lineage records authority, it never grants it
# ---------------------------------------------------------------------------


def test_same_tool_goal_lock_allow_and_block_are_unchanged_and_recorded(database: Engine) -> None:
    principal = "user_" + uuid4().hex
    workspace_a, workspace_b = provision(database, principal)
    with database.connect() as connection:
        member_of = {
            row["workspace_id"]
            for row in rows(
                connection,
                "SELECT workspace_id FROM memberships WHERE principal=:p AND active",
                {"p": principal},
            )
        }
    assert member_of == {str(workspace_a), str(workspace_b)}

    allowed = submit(database, principal, submission(workspace_a), "same-tool-a-" + uuid4().hex)
    settle(database, TicketProvider(workspace_a))
    allow = decisions(database, allowed)
    assert [(d["ordinal"], d["verdict"], d["reasons"]) for d in allow] == [
        (1, "ALLOW", ["WITHIN_CONFIRMED_AUTHORITY"])
    ]
    assert counts(database, allowed)["tickets"] == 1
    assert (
        fetch(
            database, "SELECT count(*) AS n FROM tickets WHERE workspace_id=:w", w=str(workspace_a)
        )["n"]
        >= 1
    )

    denied = submit(database, principal, submission(workspace_a), "same-tool-b-" + uuid4().hex)
    before = fetch(
        database, "SELECT count(*) AS n FROM tickets WHERE workspace_id=:w", w=str(workspace_b)
    )["n"]
    settle(database, TicketProvider(workspace_b))
    block = decisions(database, denied)
    assert block, "every evaluated action records its decision"
    assert all(d["verdict"] == "BLOCK" and d["ordinal"] == 1 for d in block)
    assert all("GOAL_SCOPE_MISMATCH" in d["reasons"] for d in block)
    assert all(d["review_id"] is None for d in block)
    assert len({d["action_id"] for d in block}) == len(block)
    after = fetch(
        database, "SELECT count(*) AS n FROM tickets WHERE workspace_id=:w", w=str(workspace_b)
    )["n"]
    assert after == before == 0
    assert counts(database, denied)["tickets"] == 0
    assert counts(database, denied)["executions"] == 0
    assert run_state(database, denied)["state"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Authority boundary: no lineage input to the guard
# ---------------------------------------------------------------------------


def test_action_guard_neither_imports_nor_reads_lineage() -> None:
    source = inspect.getsource(action_guard)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported <= {"dataclasses", "datetime", "vetoq.contracts"}
    for forbidden in ("guard_decisions", "lineage", "GUARD_VERSION", "sqlalchemy"):
        assert forbidden not in source
    fields = set(action_guard.GuardInput.__dataclass_fields__)
    assert not {name for name in fields if "decision" in name or "lineage" in name}


def test_authorize_writes_decisions_but_never_reads_them() -> None:
    authorize_source = inspect.getsource(workflow.authorize)
    assert "guard_decisions" not in authorize_source
    assert "record_guard_decision" in authorize_source
    writer = inspect.getsource(workflow.record_guard_decision)
    # The only table access is the append, which allocates the next ordinal for the action.
    assert writer.count("guard_decisions") == 2
    assert "INSERT INTO guard_decisions" in writer
    assert "one(" not in writer and "rows(" not in writer
