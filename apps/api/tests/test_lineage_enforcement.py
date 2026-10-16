"""M004 Slice C2: schema 0006 enforces, for new rows only, what the C1 writers already do.

These tests insert and update lineage rows with plain SQL against a disposable database, so
they prove the database refuses what the writers never produce. They also prove the opposite
side: every historical state that schema 0005 allowed survives the upgrade unchanged, and the
current writers' own statement shapes are accepted. Nothing here grants authority. Lineage
describes what happened and is never read by `guard()` or `authorize()`.
"""

import inspect
import os
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError
from test_lineage_failure_boundary import classified_as, failure_of, sqlstate_of
from test_lineage_schema import (
    HEAD,
    TOLERANT,
    Chain,
    _action,
    _alembic,
    _chain,
    _committed,
    _count,
    _decision,
    _drop,
    _engine,
    _execution,
    _node,
    _recreate,
    _rejects,
    _replace_database,
    _review,
    _reviewed,
    _run,
    _ticket,
    _update,
    _workspace,
)

from vetoq.contracts import action_digest
from vetoq.db import execute, one, rows
from vetoq.lineage_failure import (
    DECISION_WRITE,
    EXECUTION_LINK,
    PRODUCER_WRITE,
    is_lineage_integrity_failure,
)
from vetoq.main import database_available

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
ENFORCEMENT_DATABASE = "vetoq_m004_enforcement_test"
pytestmark = pytest.mark.integration

ALL_TABLES = (
    "workspaces",
    "memberships",
    "runs",
    "content_nodes",
    "content_edges",
    "content_edge_steps",
    "findings",
    "actions",
    "guard_decisions",
    "reviews",
    "tickets",
    "executions",
    "audit_events",
)


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    except UnsafeTestDatabase as error:
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    engine = _engine(DATABASE_URL)
    try:
        require_disposable_engine(engine)
    except UnsafeTestDatabase as error:
        engine.dispose()
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Policy revision shape.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["support-triage/1", "x", "p" * 80])
def test_a_trimmed_policy_revision_of_one_to_eighty_characters_is_accepted(
    database: Engine, value: str
) -> None:
    with database.begin() as connection:
        workspace = str(uuid4())
        execute(
            connection,
            "INSERT INTO workspaces(id,name,policy_revision) VALUES(:id,'Policy',:value)",
            {"id": workspace, "value": value},
        )


@pytest.mark.parametrize("value", ["", " ", " x", "x ", "p" * 81])
def test_a_blank_padded_or_oversize_policy_revision_is_rejected(
    database: Engine, value: str
) -> None:
    _rejects(
        database,
        "workspaces_policy_revision_shape",
        lambda c: execute(
            c,
            "INSERT INTO workspaces(id,name,policy_revision) VALUES(:id,'Policy',:value)",
            {"id": str(uuid4()), "value": value},
        ),
    )


def test_a_policy_revision_cannot_be_updated_into_a_malformed_value(database: Engine) -> None:
    with database.begin() as connection:
        workspace = _workspace(connection)
    _rejects(
        database,
        "workspaces_policy_revision_shape",
        lambda c: execute(
            c,
            "UPDATE workspaces SET policy_revision=' padded ' WHERE id=:id",
            {"id": workspace},
        ),
    )


def test_the_default_policy_revision_still_inserts(database: Engine) -> None:
    with database.begin() as connection:
        workspace = _workspace(connection)
        stored = one(
            connection, "SELECT policy_revision FROM workspaces WHERE id=:id", {"id": workspace}
        )
    assert stored == {"policy_revision": "support-triage/1"}


# ---------------------------------------------------------------------------
# Reviews: creation and the commit-time decision link.
# ---------------------------------------------------------------------------


def test_a_review_with_its_review_decision_commits(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _reviewed(connection, chain)
    with database.connect() as connection:
        stored = one(
            connection,
            """
            SELECT r.requested_at IS NOT NULL AS stamped, d.verdict, d.review_id
            FROM reviews r JOIN guard_decisions d ON d.review_id = r.id WHERE r.id=:id
            """,
            {"id": review},
        )
    assert stored == {"stamped": True, "verdict": "REVIEW", "review_id": review}


def test_a_review_without_a_review_decision_is_rejected_at_commit(database: Engine) -> None:
    chain = _committed(database, _chain)
    with pytest.raises(DBAPIError, match="review_without_review_decision"):
        with database.begin() as connection:
            _review(connection, chain)
    with database.connect() as connection:
        assert (
            _count(connection, "SELECT count(*) FROM reviews WHERE run_id=:r", r=chain.run_id) == 0
        )


@pytest.mark.parametrize("verdict", ["ALLOW", "BLOCK"])
def test_a_decision_of_another_verdict_does_not_satisfy_a_review(
    database: Engine, verdict: str
) -> None:
    chain = _committed(database, _chain)

    def attempt(connection: Connection) -> None:
        review = _review(connection, chain)
        _decision(
            connection,
            chain,
            verdict=verdict,
            reasons=["INVALID_STATE"] if verdict == "BLOCK" else None,
            review_id=review,
        )

    _rejects(database, "review_without_review_decision", attempt)


def test_a_review_decision_of_another_action_cannot_reference_the_review(
    database: Engine,
) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        other_action, other_digest = _action(
            connection, chain.workspace, chain.run_id, evidence=chain.nodes
        )
    other = replace(chain, action_id=other_action, digest=other_digest)

    def attempt(connection: Connection) -> None:
        review = _review(connection, chain)
        _decision(
            connection, other, verdict="REVIEW", reasons=["MATERIAL_UNCERTAINTY"], review_id=review
        )

    _rejects(database, "guard_decisions_review_fk", attempt)


def test_a_review_removed_in_the_same_transaction_is_not_checked(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _review(connection, chain)
        execute(connection, "DELETE FROM actions WHERE id=:a", {"a": chain.action_id})
    with database.connect() as connection:
        assert (
            _count(connection, "SELECT count(*) FROM reviews WHERE run_id=:r", r=chain.run_id) == 0
        )


# ---------------------------------------------------------------------------
# Reviews: the decision transition.
# ---------------------------------------------------------------------------

DECISION_PATTERN = "invalid_review_decision_transition"
CONSUMPTION_PATTERN = "invalid_review_consumption_transition"


def _undecided(database: Engine) -> str:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        return _reviewed(connection, chain)


def _decided(database: Engine, decision: str = "approve") -> str:
    review = _undecided(database)
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE reviews SET decision=:d,reviewer='user_reviewer',decided_at=now() WHERE id=:id
            """,
            {"d": decision, "id": review},
        )
    return review


def test_an_undecided_review_can_stay_undecided_while_other_columns_are_untouched(
    database: Engine,
) -> None:
    review = _undecided(database)
    with database.begin() as connection:
        execute(connection, "UPDATE reviews SET digest=digest WHERE id=:id", {"id": review})
        execute(connection, "UPDATE reviews SET reviewer=NULL WHERE id=:id", {"id": review})


@pytest.mark.parametrize(
    "assignment",
    [
        "decision='approve'",
        "decision='reject'",
        "reviewer='user_reviewer'",
        "decided_at=now()",
        "decision='approve',reviewer='user_reviewer'",
        "decision='approve',decided_at=now()",
        "reviewer='user_reviewer',decided_at=now()",
    ],
)
def test_a_partial_decision_is_rejected(database: Engine, assignment: str) -> None:
    review = _undecided(database)
    _rejects(database, DECISION_PATTERN, _update, "reviews", assignment, review)


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_a_decision_with_reviewer_and_time_together_is_accepted(
    database: Engine, decision: str
) -> None:
    review = _decided(database, decision)
    with database.connect() as connection:
        stored = one(
            connection,
            "SELECT decision,reviewer,decided_at FROM reviews WHERE id=:id",
            {"id": review},
        )
    assert stored is not None
    assert stored["decision"] == decision and stored["decided_at"] is not None


@pytest.mark.parametrize(
    "assignment",
    [
        "decision='reject'",
        "reviewer='someone_else'",
        "decided_at=now()+interval '1 minute'",
        "decision=NULL",
        "reviewer=NULL",
        "decided_at=NULL",
        "decision=NULL,reviewer=NULL,decided_at=NULL",
    ],
)
def test_a_decision_cannot_be_rewritten_or_cleared(database: Engine, assignment: str) -> None:
    review = _decided(database, "approve")
    _rejects(database, DECISION_PATTERN, _update, "reviews", assignment, review)


def test_the_same_decision_values_may_be_written_again_without_change(database: Engine) -> None:
    review = _decided(database)
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE reviews SET decision=decision,reviewer=reviewer,decided_at=decided_at "
            "WHERE id=:id",
            {"id": review},
        )


# ---------------------------------------------------------------------------
# Reviews: the consumption transition.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "assignment",
    ["consumed=true", "consumed_at=now()"],
)
def test_consumption_needs_its_timestamp_and_an_approval(database: Engine, assignment: str) -> None:
    review = _decided(database, "approve")
    _rejects(database, CONSUMPTION_PATTERN, _update, "reviews", assignment, review)


def test_an_undecided_review_cannot_be_consumed(database: Engine) -> None:
    review = _undecided(database)
    _rejects(
        database,
        "invalid_review_decision_transition|invalid_review_consumption_transition",
        _update,
        "reviews",
        "consumed=true,consumed_at=now()",
        review,
    )


def test_a_rejected_review_cannot_be_consumed(database: Engine) -> None:
    review = _decided(database, "reject")
    _rejects(
        database,
        CONSUMPTION_PATTERN,
        _update,
        "reviews",
        "consumed=true,consumed_at=now()",
        review,
    )


def test_an_approved_review_is_consumed_once_with_its_timestamp(database: Engine) -> None:
    review = _decided(database, "approve")
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE reviews SET consumed=true,consumed_at=now() WHERE id=:id",
            {"id": review},
        )
    for assignment in (
        "consumed=false",
        "consumed=false,consumed_at=NULL",
        "consumed_at=NULL",
        "consumed_at=now()+interval '1 minute'",
    ):
        _rejects(database, CONSUMPTION_PATTERN, _update, "reviews", assignment, review)
    with database.connect() as connection:
        stored = one(
            connection,
            "SELECT consumed, consumed_at IS NOT NULL AS stamped FROM reviews WHERE id=:id",
            {"id": review},
        )
    assert stored == {"consumed": True, "stamped": True}


def test_a_decision_and_its_consumption_can_land_in_one_statement(database: Engine) -> None:
    review = _undecided(database)
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE reviews SET decision='approve',reviewer='user_reviewer',decided_at=now(),
              consumed=true,consumed_at=now() WHERE id=:id
            """,
            {"id": review},
        )


# ---------------------------------------------------------------------------
# Executions: required link, exact link, NO ACTION semantics.
# ---------------------------------------------------------------------------


def test_a_new_execution_requires_an_exact_allow_link(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        ticket, _ = _ticket(connection, chain)
        decision = _decision(connection, chain)
        execution = _execution(connection, chain, ticket, guard_decision_id=decision)
    with database.connect() as connection:
        stored = one(
            connection, "SELECT guard_decision_id FROM executions WHERE id=:id", {"id": execution}
        )
    assert stored == {"guard_decision_id": decision}


def test_deleting_a_linked_decision_directly_is_rejected_and_the_execution_survives(
    database: Engine,
) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain)
        ticket, _ = _ticket(connection, chain)
        execution = _execution(connection, chain, ticket, guard_decision_id=decision)
    with pytest.raises(DBAPIError, match="executions_guard_decision_fk"):
        with database.begin() as connection:
            execute(connection, "DELETE FROM guard_decisions WHERE id=:id", {"id": decision})
    with database.connect() as connection:
        assert _count(connection, "SELECT count(*) FROM executions WHERE id=:e", e=execution) == 1
        assert (
            _count(connection, "SELECT count(*) FROM guard_decisions WHERE id=:d", d=decision) == 1
        )


def test_the_link_is_no_action_and_deferred_and_never_cascades(database: Engine) -> None:
    with database.connect() as connection:
        stored = one(
            connection,
            """
            SELECT confdeltype, condeferrable, condeferred, convalidated
            FROM pg_constraint WHERE conname='executions_guard_decision_fk'
            """,
        )
    assert stored == {
        "confdeltype": "a",
        "condeferrable": True,
        "condeferred": True,
        "convalidated": True,
    }


def test_an_aged_run_deletion_cascades_through_decisions_and_executions(
    database: Engine,
) -> None:
    chain = _committed(database, lambda c: _chain(c, aged=True))
    with database.begin() as connection:
        decision = _decision(connection, chain)
        ticket, _ = _ticket(connection, chain)
        _execution(connection, chain, ticket, guard_decision_id=decision)
    with database.begin() as connection:
        execute(connection, "DELETE FROM runs WHERE id=:r", {"r": chain.run_id})
    with database.connect() as connection:
        for table in ("guard_decisions", "executions", "tickets", "actions"):
            assert (
                _count(connection, f"SELECT count(*) FROM {table} WHERE run_id=:r", r=chain.run_id)
                == 0
            )


def test_deleting_an_action_cascades_through_decisions_and_executions(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain)
        ticket, _ = _ticket(connection, chain)
        _execution(connection, chain, ticket, guard_decision_id=decision)
    with database.begin() as connection:
        execute(connection, "DELETE FROM actions WHERE id=:a", {"a": chain.action_id})
    with database.connect() as connection:
        for table in ("guard_decisions", "executions", "tickets"):
            assert (
                _count(
                    connection,
                    f"SELECT count(*) FROM {table} WHERE action_id=:a",
                    a=chain.action_id,
                )
                == 0
            )


def test_retention_still_refuses_to_delete_a_run_that_is_not_due(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain)
        ticket, _ = _ticket(connection, chain)
        _execution(connection, chain, ticket, guard_decision_id=decision)
    _rejects(
        database,
        "retention_not_due",
        lambda c: execute(c, "DELETE FROM runs WHERE id=:r", {"r": chain.run_id}),
    )
    with database.connect() as connection:
        assert (
            _count(connection, "SELECT count(*) FROM executions WHERE run_id=:r", r=chain.run_id)
            == 1
        )


# ---------------------------------------------------------------------------
# Actions: the producer trio, the optional response id, and the digest boundary.
# ---------------------------------------------------------------------------


def test_a_response_id_without_the_trio_is_rejected_by_the_trigger_or_the_check(
    database: Engine,
) -> None:
    chain = _committed(database, _chain)
    none: dict[str, str | None] = {
        "producer_provider": None,
        "producer_model": None,
        "producer_prompt_version": None,
    }
    _rejects(
        database,
        "action_producer_required",
        lambda c: _action(
            c, chain.workspace, chain.run_id, evidence=chain.nodes, producer_response_id="r", **none
        ),
    )


def test_the_response_id_check_is_a_real_validated_constraint(database: Engine) -> None:
    with database.connect() as connection:
        stored = one(
            connection,
            """
            SELECT convalidated, pg_get_constraintdef(oid) AS definition FROM pg_constraint
            WHERE conname='action_producer_response_requires_trio'
            """,
        )
    assert stored is not None and stored["convalidated"] is True
    assert "producer_response_id IS NULL" in str(stored["definition"])


def test_a_response_id_is_optional_when_the_trio_is_present(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _action(connection, chain.workspace, chain.run_id, evidence=chain.nodes)
        _action(
            connection,
            chain.workspace,
            chain.run_id,
            evidence=chain.nodes,
            producer_response_id="resp_1",
        )


def test_producer_metadata_is_not_part_of_the_action_digest() -> None:
    """The digest covers the run, the Goal Lock and the proposal. Producer provenance is
    stored beside it and can never be a reason for, or against, an action."""

    parameters = list(inspect.signature(action_digest).parameters)
    assert parameters == ["run_id", "envelope", "proposal"]
    assert not any("producer" in name for name in parameters)


# ---------------------------------------------------------------------------
# Guard decisions: the review link.
# ---------------------------------------------------------------------------


def test_a_decision_for_an_action_with_a_review_must_carry_that_review(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _reviewed(connection, chain)
    for verdict, reasons in (("ALLOW", None), ("BLOCK", ["INVALID_STATE"])):
        _rejects(
            database,
            "guard_decision_review_link_required",
            lambda c, v=verdict, r=reasons: _decision(
                c, chain, ordinal=2, verdict=v, reasons=r, review_id=None
            ),
        )
    with database.begin() as connection:
        _decision(connection, chain, ordinal=2, review_id=review)


def test_a_straight_allow_or_block_needs_no_review(database: Engine) -> None:
    allowed = _committed(database, _chain)
    blocked = _committed(database, _chain)
    with database.begin() as connection:
        _decision(connection, allowed)
        _decision(connection, blocked, verdict="BLOCK", reasons=["INVALID_STATE"])


def test_a_decision_cannot_carry_the_review_of_another_action(database: Engine) -> None:
    mine = _committed(database, _chain)
    other = _committed(database, _chain)
    with database.begin() as connection:
        foreign = _reviewed(connection, other)
    _rejects(
        database,
        "guard_decision_review_link_required|guard_decisions_review_fk",
        lambda c: _decision(c, mine, review_id=foreign),
    )


# ---------------------------------------------------------------------------
# Classifier identities for the new rules.
# ---------------------------------------------------------------------------


def test_new_required_write_rules_classify_only_under_their_own_write(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _reviewed(connection, chain)
        ticket, _ = _ticket(connection, chain)
    decision_error = failure_of(database, lambda c: _decision(c, chain, ordinal=2, review_id=None))
    assert sqlstate_of(decision_error) == "P0001"
    assert classified_as(decision_error) == {"decision"}
    link_error = failure_of(
        database, lambda c: _execution(c, chain, ticket, guard_decision_id=None)
    )
    assert sqlstate_of(link_error) == "P0001"
    assert classified_as(link_error) == {"link"}
    assert not is_lineage_integrity_failure(link_error, DECISION_WRITE)
    assert not is_lineage_integrity_failure(link_error, PRODUCER_WRITE)
    producer_error = failure_of(
        database,
        lambda c: _action(
            c,
            chain.workspace,
            chain.run_id,
            evidence=chain.nodes,
            producer_provider=None,
            producer_model=None,
            producer_prompt_version=None,
        ),
    )
    assert sqlstate_of(producer_error) == "P0001"
    assert classified_as(producer_error) == {"producer"}


def test_the_policy_shape_and_review_rules_are_not_lineage_write_failures(
    database: Engine,
) -> None:
    chain = _committed(database, _chain)
    shape = failure_of(
        database,
        lambda c: execute(
            c,
            "INSERT INTO workspaces(id,name,policy_revision) VALUES(:id,'Policy',' ')",
            {"id": str(uuid4())},
        ),
    )
    assert sqlstate_of(shape) == "23514"
    assert classified_as(shape) == set()
    stamp = failure_of(database, lambda c: _review(c, chain, requested_at=None))
    assert sqlstate_of(stamp) == "P0001"
    assert classified_as(stamp) == set()
    for write in (DECISION_WRITE, EXECUTION_LINK, PRODUCER_WRITE):
        assert "workspaces_policy_revision_shape" not in write.constraints
        assert "review_requested_at_required" not in write.trigger_codes


# ---------------------------------------------------------------------------
# 0005 -> 0006 on a populated database, with every in-flight historical state.
# ---------------------------------------------------------------------------


def _snapshot(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        return {
            table: rows(connection, f"SELECT * FROM {table} ORDER BY 1, 2") for table in ALL_TABLES
        }


def _counts_of(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {t: _count(connection, f"SELECT count(*) FROM {t}") for t in ALL_TABLES}


NO_PRODUCER: dict[str, str | None] = {
    "producer_provider": None,
    "producer_model": None,
    "producer_prompt_version": None,
    "producer_response_id": None,
}


def _populate_in_flight(engine: Engine) -> dict[str, Any]:
    """Fixtures A to G, written through the 0005 schema exactly as each era left them."""

    ids: dict[str, Any] = {}
    with engine.begin() as c:
        # A historical action (no producer) and B its historical execution (no link).
        historical = _chain_without_producer(c)
        ticket, _ = _ticket(c, historical)
        ids["A"] = historical.action_id
        ids["B"] = _execution(c, historical, ticket, guard_decision_id=None)
        ids["A_chain"] = historical

        # C: a historical review with no request time and no decision.
        c_chain = _chain_without_producer(c)
        ids["C"] = _review(c, c_chain, requested_at=None)

        # D: a review approved by the old writer: reviewer set, decided_at NULL.
        d_chain = _chain_without_producer(c)
        ids["D"] = _review(c, d_chain, requested_at=None)
        execute(
            c,
            "UPDATE reviews SET decision='approve',reviewer='legacy' WHERE id=:id",
            {"id": ids["D"]},
        )

        # E: consumed by the old writer: consumed true, consumed_at NULL.
        e_chain = _chain_without_producer(c)
        ids["E"] = _review(c, e_chain, requested_at=None)
        execute(
            c,
            "UPDATE reviews SET decision='approve',reviewer='legacy' WHERE id=:id",
            {"id": ids["E"]},
        )
        execute(c, "UPDATE reviews SET consumed=true WHERE id=:id", {"id": ids["E"]})

        # F: a C1-era review: requested, REVIEW decision, approved with decided_at, unconsumed.
        f_chain = _chain(c)
        ids["F"] = _reviewed(c, f_chain)
        execute(
            c,
            """
            UPDATE reviews SET decision='approve',reviewer='user_reviewer',decided_at=now()
            WHERE id=:id
            """,
            {"id": ids["F"]},
        )
        ids["F_chain"] = f_chain

        # G: a C1-era execution with its ALLOW link.
        g_chain = _chain(c)
        allow = _decision(c, g_chain)
        g_ticket, _ = _ticket(c, g_chain)
        ids["G"] = _execution(c, g_chain, g_ticket, guard_decision_id=allow)
        ids["G_decision"] = allow
        ids["G_chain"] = g_chain
        ids["c_chain"], ids["d_chain"], ids["e_chain"] = c_chain, d_chain, e_chain
    return ids


def _chain_without_producer(connection: Connection) -> Chain:
    workspace = _workspace(connection)
    run_id = _run(connection, workspace)
    node = _node(connection, workspace, run_id)
    action_id, digest = _action(connection, workspace, run_id, evidence=[node], **NO_PRODUCER)
    return Chain(workspace, run_id, [node], action_id, digest)


@pytest.fixture
def enforcement_url() -> Iterator[str]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    url = _replace_database(DATABASE_URL, ENFORCEMENT_DATABASE)
    require_disposable_url(url, DEVELOPMENT_URLS)
    _recreate(ENFORCEMENT_DATABASE)
    try:
        yield url
    finally:
        _drop(ENFORCEMENT_DATABASE)


def test_a_populated_0005_database_upgrades_to_0006_without_changing_a_value_or_a_count(
    enforcement_url: str,
) -> None:
    url = enforcement_url
    assert _alembic(url, "upgrade", TOLERANT).returncode == 0
    engine = _engine(url)
    try:
        require_disposable_engine(engine)
        ids = _populate_in_flight(engine)
        before_counts, before_rows = _counts_of(engine), _snapshot(engine)
        assert before_counts["reviews"] == 4 and before_counts["executions"] == 2
        assert database_available(url) is False

        completed = _alembic(url, "upgrade", "head")
        assert completed.returncode == 0, completed.stderr.replace(url, "[redacted]")
        heads = _alembic(url, "heads")
        assert heads.stdout.count("(head)") == 1 and HEAD in heads.stdout
        assert database_available(url) is True
        assert _counts_of(engine) == before_counts
        assert _snapshot(engine) == before_rows

        with engine.connect() as connection:
            legacy_states = one(
                connection,
                """
                SELECT
                  (SELECT count(*) FROM actions WHERE producer_provider IS NULL) AS no_producer,
                  (SELECT count(*) FROM executions WHERE guard_decision_id IS NULL) AS no_link,
                  (SELECT count(*) FROM reviews WHERE requested_at IS NULL) AS no_request,
                  (SELECT count(*) FROM reviews
                    WHERE decision IS NOT NULL AND decided_at IS NULL) AS no_decided_at,
                  (SELECT count(*) FROM reviews
                    WHERE consumed AND consumed_at IS NULL) AS no_consumed_at
                """,
            )
        assert legacy_states == {
            "no_producer": 4,
            "no_link": 1,
            "no_request": 3,
            "no_decided_at": 2,
            "no_consumed_at": 1,
        }

        _assert_legacy_rows_still_work(engine, ids)
        _assert_new_writes_are_strict(engine, ids)
    finally:
        engine.dispose()


def _assert_legacy_rows_still_work(engine: Engine, ids: dict[str, Any]) -> None:
    # Historical rows keep working under the current writers' own statement shapes.
    with engine.begin() as connection:
        # C: a legacy review with no request time can still be decided and then consumed.
        execute(
            connection,
            """
            UPDATE reviews SET decision='approve',reviewer='user_reviewer',decided_at=now()
            WHERE id=:id
            """,
            {"id": ids["C"]},
        )
        execute(
            connection,
            "UPDATE reviews SET consumed=true,consumed_at=now() WHERE id=:id",
            {"id": ids["C"]},
        )
        # D: decided without decided_at, then consumed with its timestamp.
        execute(
            connection,
            "UPDATE reviews SET consumed=true,consumed_at=now() WHERE id=:id",
            {"id": ids["D"]},
        )
        # F: the C1-era review is consumed.
        execute(
            connection,
            "UPDATE reviews SET consumed=true,consumed_at=now() WHERE id=:id",
            {"id": ids["F"]},
        )
        # B: a legacy execution still verifies once.
        execute(
            connection, "UPDATE executions SET verified_at=now() WHERE id=:id", {"id": ids["B"]}
        )
    with engine.begin() as connection:
        # E: consumed without a timestamp stays as it was, and cannot be rewritten.
        for assignment in ("consumed=false", "consumed_at=now()"):
            with pytest.raises(DBAPIError, match=CONSUMPTION_PATTERN):
                with connection.begin_nested():
                    _update(connection, "reviews", assignment, ids["E"])
        for assignment in ("decision='reject'", "decided_at=now()"):
            with pytest.raises(DBAPIError, match=DECISION_PATTERN):
                with connection.begin_nested():
                    _update(connection, "reviews", assignment, ids["D"])
        # A: a historical action's producer columns stay immutable evidence.
        with pytest.raises(DBAPIError, match="immutable_action"):
            with connection.begin_nested():
                _update(connection, "actions", "producer_provider='late'", ids["A"])


def _assert_new_writes_are_strict(engine: Engine, ids: dict[str, Any]) -> None:
    with engine.begin() as connection:
        fresh = _chain(connection)
        ticket, _ = _ticket(connection, fresh)
        for pattern, attempt in (
            (
                "action_producer_required",
                lambda: _action(
                    connection, fresh.workspace, fresh.run_id, evidence=fresh.nodes, **NO_PRODUCER
                ),
            ),
            (
                "review_requested_at_required",
                lambda: _review(connection, fresh, requested_at=None),
            ),
            (
                "execution_guard_decision_required",
                lambda: _execution(connection, fresh, ticket, guard_decision_id=None),
            ),
        ):
            with pytest.raises(DBAPIError, match=pattern):
                with connection.begin_nested():
                    attempt()
    # The linked C1-era execution cannot lose its decision. The rule is checked at commit.
    with pytest.raises(DBAPIError, match="executions_guard_decision_fk"):
        with engine.begin() as connection:
            execute(
                connection, "DELETE FROM guard_decisions WHERE id=:id", {"id": ids["G_decision"]}
            )
    with engine.connect() as connection:
        assert _count(connection, "SELECT count(*) FROM executions WHERE id=:id", id=ids["G"]) == 1


def test_a_populated_upgrade_stops_when_a_policy_revision_is_malformed(
    enforcement_url: str,
) -> None:
    """The migration never repairs history. A malformed source value stops it, and nothing
    is half-applied because the revision runs in one transaction."""

    url = enforcement_url
    assert _alembic(url, "upgrade", TOLERANT).returncode == 0
    engine = _engine(url)
    try:
        require_disposable_engine(engine)
        with engine.begin() as connection:
            execute(
                connection,
                "INSERT INTO workspaces(id,name,policy_revision) VALUES(:id,'Bad',' padded ')",
                {"id": str(uuid4())},
            )
        before = _counts_of(engine)
        completed = _alembic(url, "upgrade", "head")
        assert completed.returncode != 0
        with engine.connect() as connection:
            version = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            strict = connection.execute(
                text("SELECT to_regproc('require_review_requested_at') IS NOT NULL")
            ).scalar_one()
        assert (version, strict) == (TOLERANT, False)
        assert _counts_of(engine) == before
    finally:
        engine.dispose()


def test_a_run_cascade_still_works_for_a_historical_chain_after_the_upgrade(
    enforcement_url: str,
) -> None:
    url = enforcement_url
    assert _alembic(url, "upgrade", TOLERANT).returncode == 0
    engine = _engine(url)
    try:
        require_disposable_engine(engine)
        with engine.begin() as connection:
            workspace = _workspace(connection)
            run_id = _run(connection, workspace, aged=True)
            node = _node(connection, workspace, run_id)
            action_id, digest = _action(
                connection, workspace, run_id, evidence=[node], **NO_PRODUCER
            )
            chain = Chain(workspace, run_id, [node], action_id, digest)
            ticket, _ = _ticket(connection, chain)
            _execution(connection, chain, ticket, guard_decision_id=None)
        assert _alembic(url, "upgrade", "head").returncode == 0
        with engine.begin() as connection:
            execute(connection, "DELETE FROM runs WHERE id=:r", {"r": run_id})
        with engine.connect() as connection:
            for table in ("actions", "tickets", "executions"):
                assert (
                    _count(connection, f"SELECT count(*) FROM {table} WHERE run_id=:r", r=run_id)
                    == 0
                )
    finally:
        engine.dispose()
