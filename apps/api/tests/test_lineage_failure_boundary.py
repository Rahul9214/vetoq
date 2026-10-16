"""M004 Slice C1B: which database failures are `lineage_write_failure`.

`lineage_write_failure` means one required structural lineage write was rejected by a
lineage integrity rule. It never means a generic database failure. These tests run real
PostgreSQL errors, with their real SQLSTATE and diagnostics, through the classifier and
through the real workflow, and prove that nothing survives a failure.
"""

import logging
import os
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import pytest
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from test_database_integration import TicketProvider
from test_lineage_schema import _action, _chain, _decision, _execution, _ticket
from test_lineage_writers import Variant, counts, fetch, injecting, run_state, start

from vetoq import workflow
from vetoq.config import Settings
from vetoq.db import engine_for, execute
from vetoq.lineage_failure import (
    DECISION_WRITE,
    EXECUTION_LINK,
    PRODUCER_WRITE,
    LineageWrite,
    is_lineage_integrity_failure,
)
from vetoq.workflow import tick

DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
pytestmark = pytest.mark.integration

ALL_WRITES = (DECISION_WRITE, EXECUTION_LINK, PRODUCER_WRITE)
# One action, no decision, review, ticket, execution, or model finding survives a rollback.
NOTHING_SURVIVES = {
    "actions": 1,
    "decisions": 0,
    "reviews": 0,
    "tickets": 0,
    "executions": 0,
    "model_findings": 0,
}


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


def failure_of(database: Engine, attempt: Callable[[Connection], object]) -> DBAPIError:
    """Run `attempt` in one transaction that must fail, and return the real error."""

    with pytest.raises(DBAPIError) as caught:
        with database.begin() as connection:
            attempt(connection)
    return caught.value


def sqlstate_of(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def classified_as(error: DBAPIError) -> set[str]:
    """The names of every required lineage write this error would be classified under."""

    names = {"decision": DECISION_WRITE, "link": EXECUTION_LINK, "producer": PRODUCER_WRITE}
    return {name for name, write in names.items() if is_lineage_integrity_failure(error, write)}


# ---------------------------------------------------------------------------
# Classifier: real lineage integrity failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "sqlstate", "options"),
    [
        ("verdict check", "23514", {"verdict": "MAYBE"}),
        ("digest check", "23514", {"digest": "A" * 64}),
        ("policy revision check", "23514", {"policy": " padded"}),
        ("guard version check", "23514", {"version": ""}),
        ("review link check", "23514", {"verdict": "REVIEW", "reasons": ["MATERIAL_UNCERTAINTY"]}),
        ("action digest foreign key", "23503", {"digest": "0" * 64}),
        ("review foreign key", "23503", {"review_id": "not-a-review"}),
        ("ordinal trigger", "P0001", {"ordinal": 7}),
    ],
)
def test_a_real_decision_integrity_failure_is_a_decision_lineage_failure(
    database: Engine, label: str, sqlstate: str, options: dict[str, Any]
) -> None:
    with database.begin() as connection:
        chain = _chain(connection)
    error = failure_of(database, lambda c: _decision(c, chain, **options))
    assert sqlstate_of(error) == sqlstate, label
    assert classified_as(error) == {"decision"}, label


def test_a_real_invalid_execution_link_is_an_execution_link_failure(database: Engine) -> None:
    with database.begin() as connection:
        chain = _chain(connection)

    def unknown_decision(c: Connection) -> object:
        ticket, _ = _ticket(c, chain)
        return _execution(c, chain, ticket, guard_decision_id=str(uuid4()))

    def blocking_decision(c: Connection) -> object:
        decision = _decision(c, chain, verdict="BLOCK", reasons=["GOAL_SCOPE_MISMATCH"])
        ticket, _ = _ticket(c, chain)
        return _execution(c, chain, ticket, guard_decision_id=decision)

    for attempt in (unknown_decision, blocking_decision):
        error = failure_of(database, attempt)
        assert sqlstate_of(error) == "P0001"
        assert classified_as(error) == {"link"}


def test_the_execution_link_foreign_key_identity_is_classified(database: Engine) -> None:
    """The foreign key only fires when the trigger is bypassed, so reach it deliberately.

    The statement disables the link trigger inside one transaction that always rolls
    back. PostgreSQL DDL is transactional, so the trigger is restored and nothing is
    committed. This reaches the real diagnostics of the foreign key, which the trigger
    otherwise makes unreachable.
    """

    with database.begin() as connection:
        chain = _chain(connection)

    def bypassed(c: Connection) -> object:
        execute(c, "ALTER TABLE executions DISABLE TRIGGER execution_authorization_link")
        ticket, _ = _ticket(c, chain)
        return _execution(c, chain, ticket, guard_decision_id=str(uuid4()))

    error = failure_of(database, bypassed)
    assert sqlstate_of(error) == "23503"
    assert classified_as(error) == {"link"}
    with database.connect() as connection:
        enabled = connection.execute(
            text("SELECT tgenabled FROM pg_trigger WHERE tgname='execution_authorization_link'")
        ).scalar_one()
    assert enabled == "O"


def test_a_real_producer_check_failure_is_a_producer_lineage_failure(database: Engine) -> None:
    with database.begin() as connection:
        chain = _chain(connection)

    def attempt(producer: dict[str, str | None]) -> Callable[[Connection], object]:
        def insert(c: Connection) -> object:
            return _action(c, chain.workspace, chain.run_id, evidence=chain.nodes[:1], **producer)

        return insert

    invalid: list[dict[str, str | None]] = [
        {"producer_provider": "", "producer_model": "m", "producer_prompt_version": "p"},
        {
            "producer_provider": "p",
            "producer_model": "m",
            "producer_prompt_version": "v",
            "producer_response_id": "r" * 201,
        },
    ]
    for producer in invalid:
        error = failure_of(database, attempt(producer))
        assert sqlstate_of(error) == "23514"
        assert classified_as(error) == {"producer"}
    # Schema 0006: a missing trio member is rejected by the insert trigger, with its own code.
    partial: dict[str, str | None] = {
        "producer_provider": "x",
        "producer_model": None,
        "producer_prompt_version": None,
    }
    error = failure_of(database, attempt(partial))
    assert sqlstate_of(error) == "P0001"
    assert classified_as(error) == {"producer"}
    orphan_id: dict[str, str | None] = {
        "producer_provider": None,
        "producer_model": None,
        "producer_prompt_version": None,
        "producer_response_id": "resp_1",
    }
    error = failure_of(database, attempt(orphan_id))
    assert sqlstate_of(error) == "P0001"
    assert classified_as(error) == {"producer"}


# ---------------------------------------------------------------------------
# Classifier: failures that are not lineage failures
# ---------------------------------------------------------------------------


def test_a_statement_timeout_is_never_a_lineage_failure(database: Engine) -> None:
    def slow(c: Connection) -> None:
        execute(c, "SET LOCAL statement_timeout = '1ms'")
        execute(c, "SELECT pg_sleep(2)")

    error = failure_of(database, slow)
    assert isinstance(error, OperationalError)
    assert sqlstate_of(error) == "57014"
    assert classified_as(error) == set()


def test_lock_not_available_is_never_a_lineage_failure(database: Engine) -> None:
    with database.begin() as connection:
        chain = _chain(connection)
    key = {"w": chain.workspace}
    with database.connect() as holder:
        holder.execute(text("SELECT 1 FROM workspaces WHERE id=:w FOR UPDATE"), key)
        error = failure_of(
            database,
            lambda c: c.execute(
                text("SELECT 1 FROM workspaces WHERE id=:w FOR UPDATE NOWAIT"), key
            ),
        )
    assert isinstance(error, OperationalError)
    assert sqlstate_of(error) == "55P03"
    assert classified_as(error) == set()


def test_an_administrator_shutdown_is_never_a_lineage_failure(database: Engine) -> None:
    error = failure_of(
        database, lambda c: execute(c, "SELECT pg_terminate_backend(pg_backend_pid())")
    )
    assert isinstance(error, OperationalError)
    assert sqlstate_of(error) in {"57P01", None}
    assert classified_as(error) == set()


def test_a_ticket_integrity_failure_is_not_a_lineage_failure(database: Engine) -> None:
    with database.begin() as connection:
        chain = _chain(connection)

    def empty_title(c: Connection) -> None:
        execute(
            c,
            """
            INSERT INTO tickets(id,workspace_id,run_id,action_id,title,body)
            VALUES(:id,:w,:r,:a,'','body')
            """,
            {"id": str(uuid4()), "w": chain.workspace, "r": chain.run_id, "a": chain.action_id},
        )

    error = failure_of(database, empty_title)
    assert sqlstate_of(error) == "23514"
    assert classified_as(error) == set()


def test_a_non_link_execution_integrity_failure_is_not_a_lineage_failure(
    database: Engine,
) -> None:
    with database.begin() as connection:
        chain = _chain(connection)

    def unknown_ticket(c: Connection) -> object:
        decision = _decision(c, chain)
        return _execution(c, chain, str(uuid4()), guard_decision_id=decision)

    error = failure_of(database, unknown_ticket)
    assert sqlstate_of(error) == "23503"
    assert classified_as(error) == set()


def test_an_unrelated_trigger_exception_is_not_a_lineage_failure(database: Engine) -> None:
    with database.begin() as connection:
        chain = _chain(connection)
    error = failure_of(
        database,
        lambda c: execute(
            c,
            "UPDATE actions SET producer_provider='changed' WHERE id=:a",
            {"a": chain.action_id},
        ),
    )
    assert sqlstate_of(error) == "P0001"
    assert classified_as(error) == set()


def test_a_lineage_error_is_classified_only_for_its_own_write(database: Engine) -> None:
    with database.begin() as connection:
        chain = _chain(connection)
    error = failure_of(database, lambda c: _decision(c, chain, verdict="MAYBE"))
    assert classified_as(error) == {"decision"}
    assert not is_lineage_integrity_failure(error, EXECUTION_LINK)
    assert not is_lineage_integrity_failure(error, PRODUCER_WRITE)


def test_message_text_alone_never_classifies_a_failure() -> None:
    """Identity is SQLSTATE plus diagnostics. Names in prose are not an identity."""

    for write in ALL_WRITES:
        for name in sorted(write.constraints | write.trigger_codes):
            assert not is_lineage_integrity_failure(
                DBAPIError("INSERT", {}, ValueError(f"error mentions {name}")), write
            )
    assert not is_lineage_integrity_failure(
        DBAPIError("INSERT", {}, ValueError("guard")), DECISION_WRITE
    )


def test_every_known_identity_exists_in_the_current_schema(database: Engine) -> None:
    """The classifier names real objects, so a rename in a migration cannot go unnoticed."""

    known: dict[str, LineageWrite] = {
        "guard_decisions": DECISION_WRITE,
        "executions": EXECUTION_LINK,
        "actions": PRODUCER_WRITE,
    }
    with database.connect() as connection:
        for table, write in known.items():
            names = {
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT c.conname FROM pg_constraint c
                        WHERE c.conrelid = CAST(:t AS regclass)
                        """
                    ),
                    {"t": table},
                )
            }
            assert write.constraints <= names, table
        source = " ".join(
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT p.prosrc FROM pg_proc p
                    WHERE p.proname IN (
                      'enforce_guard_decision_ordinal','enforce_execution_authorization',
                      'enforce_guard_decision_review_link','require_action_producer'
                    )
                    """
                )
            )
        )
    for write in (DECISION_WRITE, EXECUTION_LINK, PRODUCER_WRITE):
        for code in write.trigger_codes:
            assert f"'{code}'" in source


# ---------------------------------------------------------------------------
# The real workflow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("uncertain", [False, True])
@pytest.mark.parametrize(
    "tweak", [{"v": "MAYBE"}, {"d": "0" * 64}], ids=["verdict_check", "action_digest_fk"]
)
def test_a_real_decision_integrity_failure_rolls_back_the_whole_authorization(
    database: Engine, monkeypatch: pytest.MonkeyPatch, uncertain: bool, tweak: dict[str, str]
) -> None:
    run_id, workspace, _ = start(database, "decision-integrity-")
    provider = TicketProvider(workspace, uncertain=uncertain)
    assert tick(database, provider)

    def corrupt(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        real(c, sql, {**params, **tweak})

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting("INSERT INTO guard_decisions", corrupt))
        assert tick(database, provider)
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "lineage_write_failure")
    assert counts(database, run_id) == NOTHING_SURVIVES
    cached = fetch(database, "SELECT verdict,reasons FROM actions WHERE run_id=:r", r=run_id)
    assert cached == {"verdict": None, "reasons": []}
    assert state["writes"] == 0


def test_a_real_invalid_execution_link_rolls_back_the_ticket_and_the_decision(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, workspace, _ = start(database, "link-integrity-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)

    def wrong_link(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        real(c, sql, {**params, "decision": str(uuid4())})

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting("INSERT INTO executions", wrong_link))
        assert tick(database, provider)
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "lineage_write_failure")
    assert counts(database, run_id) == NOTHING_SURVIVES
    assert state["writes"] == 0


def test_a_database_producer_check_is_a_lineage_failure_without_an_action(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The application validates the trio first. This reaches the database backstop."""

    run_id, workspace, _ = start(database, "producer-backstop-")

    def blank_provider(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        real(c, sql, {**params, "provider": ""})

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting("INSERT INTO actions", blank_provider))
        assert tick(database, TicketProvider(workspace))
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "lineage_write_failure")
    assert counts(database, run_id) == {**NOTHING_SURVIVES, "actions": 0}


@pytest.mark.parametrize("write", ["INSERT INTO guard_decisions", "INSERT INTO executions"])
def test_a_statement_timeout_is_a_worker_failure_and_nothing_survives(
    database: Engine, monkeypatch: pytest.MonkeyPatch, write: str
) -> None:
    run_id, workspace, _ = start(database, "statement-timeout-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)

    def timeout(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        real(c, "SET LOCAL statement_timeout = '1ms'")
        real(c, "SELECT pg_sleep(2)")

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting(write, timeout))
        assert tick(database, provider)
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "worker_failure")
    assert state["failure"] != "lineage_write_failure"
    assert counts(database, run_id) == NOTHING_SURVIVES
    assert state["writes"] == 0


def test_an_ordinary_ticket_integrity_failure_is_not_a_lineage_failure(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, workspace, _ = start(database, "ticket-integrity-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)

    def empty_title(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        real(c, sql, {**params, "title": ""})

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting("INSERT INTO tickets", empty_title))
        assert tick(database, provider)
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "worker_failure")
    # The decision was inserted before the ticket and rolled back with it.
    assert counts(database, run_id) == NOTHING_SURVIVES


def test_a_non_link_execution_integrity_failure_is_a_worker_failure(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, workspace, _ = start(database, "execution-integrity-")
    provider = TicketProvider(workspace)
    assert tick(database, provider)

    def unknown_ticket(real: Callable[..., None], c: Any, sql: str, params: Any) -> None:
        real(c, sql, {**params, "t": str(uuid4())})

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "execute", injecting("INSERT INTO executions", unknown_ticket))
        assert tick(database, provider)
    state = run_state(database, run_id)
    assert (state["state"], state["failure"]) == ("FAILED", "worker_failure")
    assert counts(database, run_id) == NOTHING_SURVIVES


def test_invalid_model_evidence_and_producer_trio_keep_their_own_codes(database: Engine) -> None:
    run_id, workspace, _ = start(database, "vocabulary-boundary-")
    assert tick(database, Variant(workspace, evidence_ids=[uuid4()]))
    assert run_state(database, run_id)["failure"] == "invalid_model_evidence"
    other, workspace_other, _ = start(database, "vocabulary-trio-")
    assert tick(database, Variant(workspace_other, result={"model": " padded"}))
    assert run_state(database, other)["failure"] == "lineage_write_failure"
    assert counts(database, other)["actions"] == 0


# ---------------------------------------------------------------------------
# Response-id normalization and its warning
# ---------------------------------------------------------------------------


def discard_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if "producer_response_id_discarded" in r.getMessage()]


def test_an_oversize_response_id_is_discarded_with_one_safe_warning(
    database: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    run_id, workspace, _ = start(database, "oversize-id-")
    secret_id = "RAW-EXTERNAL-ID-" + "x" * 200
    caplog.set_level(logging.DEBUG, logger="vetoq.worker")
    assert tick(database, Variant(workspace, result={"request_id": secret_id}))
    action = fetch(
        database,
        "SELECT producer_provider,producer_response_id FROM actions WHERE run_id=:r",
        r=run_id,
    )
    assert action == {"producer_provider": "fixture", "producer_response_id": None}
    assert run_state(database, run_id)["state"] == "AUTHORIZING"
    warnings = discard_warnings(caplog)
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    message = warnings[0].getMessage()
    assert run_id in message and "fixture" in message and "response_id_too_long" in message
    assert "RAW-EXTERNAL-ID" not in caplog.text
    assert secret_id not in caplog.text


@pytest.mark.parametrize("request_id", ["resp_ok_123", "x" * 200, "", "   "])
def test_a_usable_or_absent_response_id_logs_no_discard_warning(
    database: Engine, caplog: pytest.LogCaptureFixture, request_id: str
) -> None:
    run_id, workspace, _ = start(database, "usable-id-")
    caplog.set_level(logging.DEBUG, logger="vetoq.worker")
    assert tick(database, Variant(workspace, result={"request_id": request_id}))
    stored = fetch(database, "SELECT producer_response_id FROM actions WHERE run_id=:r", r=run_id)
    assert stored["producer_response_id"] == (request_id.strip() or None)
    assert discard_warnings(caplog) == []
