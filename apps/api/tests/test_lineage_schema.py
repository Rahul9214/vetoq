"""M004 Slice B: schema 0005 provenance and lineage structure.

Database behavior is tested directly. These tests insert lineage rows with plain
SQL against a disposable database so they exercise the database rules on their
own. The runtime writers that populate those rows are covered separately in
`test_lineage_writers.py`.
"""

import ast
import inspect
import itertools
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from disposable_database import (
    UnsafeTestDatabase,
    development_urls,
    require_disposable_engine,
    require_disposable_url,
)
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError
from test_action_guard import NOW, WORKSPACE_B, values

from vetoq import action_guard
from vetoq.action_guard import GuardInput, guard
from vetoq.config import Settings
from vetoq.contracts import action_digest
from vetoq.db import engine_for, execute, one, rows
from vetoq.ingestion.limits import BUDGETS
from vetoq.main import SCHEMA_REVISION, database_available

API_ROOT = Path(__file__).resolve().parents[1]
UPGRADE_DATABASE = "vetoq_m004_upgrade_test"
FRESH_DATABASE = "vetoq_m004_fresh_test"
DATABASE_URL = os.environ.get("VETOQ_TEST_DATABASE_URL")
DEVELOPMENT_URLS = development_urls()
REASON_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")
HEAD = "0007_lineage_execution_lookup"
ENFORCEMENT = "0006_lineage_enforcement"
TOLERANT = "0005_provenance_lineage"
EXECUTIONS_RUN_INDEX = "executions_workspace_run_idx"

# ---------------------------------------------------------------------------
# Guard reason cardinality proof. No database is needed.
# ---------------------------------------------------------------------------


def test_every_return_path_of_guard_carries_at_least_one_reason() -> None:
    """Structural proof. A Decision either has a non-empty literal or is the
    BLOCK that is only returned under `if reasons:`."""

    function = ast.parse(inspect.getsource(action_guard.guard)).body[0]
    assert isinstance(function, ast.FunctionDef)
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Decision"
    ]
    assert len(calls) == 5
    guarded_returns: list[ast.Return] = []
    for statement in ast.walk(function):
        if isinstance(statement, ast.If) and (
            isinstance(statement.test, ast.Name) and statement.test.id == "reasons"
        ):
            guarded_returns.extend(n for n in statement.body if isinstance(n, ast.Return))
    guarded_calls = [r.value for r in guarded_returns if isinstance(r.value, ast.Call)]
    assert len(guarded_calls) == 1
    for call in calls:
        reasons = next(k.value for k in call.keywords if k.arg == "reasons")
        if isinstance(reasons, ast.List):
            assert len(reasons.elts) >= 1
            assert all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in reasons.elts
            )
        else:
            assert isinstance(reasons, ast.Name) and reasons.id == "reasons"
            assert call is guarded_calls[0]


def _enumerated_decisions() -> Iterator[tuple[str, list[str]]]:
    envelope, proposal, base = values()
    wrong_scope = proposal.model_copy(
        update={"arguments": proposal.arguments.model_copy(update={"workspace_id": WORKSPACE_B})}
    )
    wrong_tool = proposal.model_copy(update={"tool": "secrets.read"})
    for bits in itertools.product((False, True), repeat=11):
        (
            no_member,
            no_workspace,
            cancelled,
            bad_state,
            bad_tool,
            bad_scope,
            bad_policy,
            expired,
            exhausted,
            incomplete,
            executed,
        ) = bits
        chosen = proposal
        if bad_tool:
            chosen = chosen.model_copy(update={"tool": wrong_tool.tool})
        if bad_scope:
            chosen = chosen.model_copy(update={"arguments": wrong_scope.arguments})
        base_inputs = replace(
            base,
            proposal=chosen,
            persisted_digest=action_digest(base.run_id, envelope, chosen),
            membership_active=not no_member,
            workspace_active=not no_workspace,
            cancelled=cancelled,
            state="COMPLETED" if bad_state else "AUTHORIZING",
            policy_revision="other" if bad_policy else base.policy_revision,
            now=NOW + timedelta(hours=1) if expired else NOW,
            writes=1 if exhausted else 0,
            complete=not incomplete,
            execution_exists=executed,
        )
        for digest_wrong in (False, True):
            digest_inputs = (
                replace(base_inputs, persisted_digest="f" * 64) if digest_wrong else base_inputs
            )
            variants: list[GuardInput] = [replace(digest_inputs, uncertain=False)]
            uncertain = replace(digest_inputs, uncertain=True)
            for approval in ("none", "valid", "originator", "stale", "consumed"):
                candidate = uncertain
                if approval != "none":
                    candidate = replace(
                        uncertain,
                        approval_digest=uncertain.persisted_digest,
                        approval_expires=NOW + timedelta(minutes=5),
                        reviewer_active=True,
                        reviewer_is_originator=approval == "originator",
                        approval_consumed=approval == "consumed",
                    )
                    if approval == "stale":
                        candidate = replace(candidate, approval_digest="e" * 64)
                variants.append(candidate)
            for inputs in variants:
                decision = guard(inputs)
                yield decision.verdict, decision.reasons


def test_no_valid_guard_decision_has_zero_reasons_and_none_exceeds_the_database_bound() -> None:
    """Behavioral proof over every combination of the guard's own conditions.

    The database bound is 1..16. If the guard ever gains a path that can return
    no reasons, or more than sixteen, this test fails and the schema bound must
    be reviewed. The guard is never changed to fit storage."""

    sizes: set[int] = set()
    verdicts: set[str] = set()
    codes: set[str] = set()
    for verdict, reasons in _enumerated_decisions():
        sizes.add(len(reasons))
        verdicts.add(verdict)
        codes.update(reasons)
    assert verdicts == {"ALLOW", "REVIEW", "BLOCK"}
    assert min(sizes) == 1
    assert max(sizes) == 11
    assert max(sizes) <= 16
    assert all(REASON_PATTERN.fullmatch(code) for code in codes)
    assert len(codes) == 15


# ---------------------------------------------------------------------------
# Migration structure that needs no database.
# ---------------------------------------------------------------------------


def test_revision_0007_is_the_single_head_after_0006() -> None:
    script = ScriptDirectory(str(API_ROOT / "migrations"))
    assert script.get_heads() == [HEAD]
    revision = script.get_revision(HEAD)
    enforcement = script.get_revision(ENFORCEMENT)
    structure = script.get_revision("0005_provenance_lineage")
    assert revision is not None and enforcement is not None and structure is not None
    assert revision.down_revision == ENFORCEMENT
    assert enforcement.down_revision == "0005_provenance_lineage"
    assert structure.down_revision == "0004_edge_steps"
    assert SCHEMA_REVISION == HEAD


def test_lineage_migrations_refuse_downgrade_and_earlier_revisions_were_not_rewritten() -> None:
    versions = API_ROOT / "migrations" / "versions"
    for lineage in (
        "0005_provenance_lineage.py",
        "0006_lineage_enforcement.py",
        "0007_lineage_execution_lookup.py",
    ):
        source = (versions / lineage).read_text(encoding="utf-8")
        assert "Destructive rollback requires an explicit operator recovery plan" in source
        assert "raise RuntimeError" in source
    for name in (
        "0001_security_slice.py",
        "0002_worker_claim.py",
        "0003_secure_ingestion.py",
        "0004_edge_steps.py",
    ):
        earlier = (versions / name).read_text(encoding="utf-8")
        assert "guard_decisions" not in earlier
        assert "producer_provider" not in earlier
        assert "requested_at" not in earlier
        assert EXECUTIONS_RUN_INDEX not in earlier
    # 0005 stays the tolerant revision. Strictness lives only in 0006.
    tolerant = (versions / "0005_provenance_lineage.py").read_text(encoding="utf-8")
    assert "review_requested_at_required" not in tolerant
    assert "action_producer_required" not in tolerant
    assert EXECUTIONS_RUN_INDEX not in tolerant
    enforcement = (versions / "0006_lineage_enforcement.py").read_text(encoding="utf-8")
    assert EXECUTIONS_RUN_INDEX not in enforcement
    lookup = (versions / "0007_lineage_execution_lookup.py").read_text(encoding="utf-8")
    assert "CREATE INDEX executions_workspace_run_idx" in lookup
    assert "committed_at" not in lookup.split("CREATE INDEX", 1)[1].split("downgrade", 1)[0]
    assert "INCLUDE" not in lookup
    assert "action_id" not in lookup.split("CREATE INDEX", 1)[1]
    assert "ticket_id" not in lookup.split("CREATE INDEX", 1)[1]


# ---------------------------------------------------------------------------
# Database fixtures.
# ---------------------------------------------------------------------------


def _engine(url: str) -> Engine:
    return engine_for(Settings(_env_file=None, environment="test", database_url=SecretStr(url)))


def _replace_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, ""))


@pytest.fixture
def database() -> Iterator[Engine]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    try:
        require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    except UnsafeTestDatabase as error:
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    database = _engine(DATABASE_URL)
    try:
        require_disposable_engine(database)
    except UnsafeTestDatabase as error:
        database.dispose()
        pytest.fail(f"refusing destructive integration setup: {error}", pytrace=False)
    yield database
    database.dispose()


def _workspace(connection: Connection) -> str:
    workspace, principal = str(uuid4()), "user_" + uuid4().hex
    execute(
        connection,
        "INSERT INTO workspaces(id,name) VALUES(:id,'Lineage schema')",
        {"id": workspace},
    )
    execute(
        connection,
        """
        INSERT INTO memberships(workspace_id,principal,role)
        VALUES(:workspace,:principal,'operator')
        """,
        {"workspace": workspace, "principal": principal},
    )
    return workspace


def _run(connection: Connection, workspace: str, *, aged: bool = False) -> str:
    """A terminal run, so no worker claims it. `aged` lets the retention guard delete it."""

    principal = one(
        connection,
        "SELECT principal FROM memberships WHERE workspace_id=:workspace",
        {"workspace": workspace},
    )
    assert principal is not None
    run_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO runs(
          id,workspace_id,principal,submission_key,submission_digest,
          envelope,state,expires_at,cancelled,created_at
        ) VALUES(
          :run,:workspace,:principal,:key,'digest',CAST('{}' AS jsonb),'CANCELLED',
          now()+interval '30 minutes',true,
          CASE WHEN CAST(:aged AS boolean) THEN now()-interval '2 days' ELSE now() END
        )
        """,
        {
            "run": run_id,
            "workspace": workspace,
            "principal": principal["principal"],
            "key": uuid4().hex,
            "aged": aged,
        },
    )
    return run_id


def _node(
    connection: Connection, workspace: str, run_id: str, *, origin: str = "pasted-email"
) -> str:
    node_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO content_nodes(
          id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
        ) VALUES(
          :id,:workspace,:run,:origin,'user_schema',:digest,'synthetic','untrusted',true,
          now()+interval '24 hours'
        )
        """,
        {
            "id": node_id,
            "workspace": workspace,
            "run": run_id,
            "origin": origin,
            "digest": "a" * 64,
        },
    )
    return node_id


def _proposal(evidence: object) -> str:
    return json.dumps({"tool": "tickets.create", "evidence_ids": evidence})


def _action(
    connection: Connection,
    workspace: str,
    run_id: str,
    *,
    evidence: object,
    digest: str | None = None,
    **producer: str | None,
) -> tuple[str, str]:
    action_id, value = str(uuid4()), digest or uuid4().hex * 2
    # Schema 0006 requires the producer trio on every new action, as the runtime writer
    # supplies it. A test that needs a different shape passes it explicitly.
    columns = {
        "producer_provider": "fixture",
        "producer_model": "fixture/structured",
        "producer_prompt_version": "fixture/1",
        "producer_response_id": None,
        **producer,
    }
    execute(
        connection,
        """
        INSERT INTO actions(
          id,workspace_id,run_id,proposal,digest,
          producer_provider,producer_model,producer_prompt_version,producer_response_id
        ) VALUES(
          :id,:workspace,:run,CAST(:proposal AS jsonb),:digest,
          :producer_provider,:producer_model,:producer_prompt_version,:producer_response_id
        )
        """,
        {
            "id": action_id,
            "workspace": workspace,
            "run": run_id,
            "proposal": _proposal(evidence),
            "digest": value,
            **columns,
        },
    )
    return action_id, value


@dataclass(frozen=True)
class Chain:
    workspace: str
    run_id: str
    nodes: list[str]
    action_id: str
    digest: str


def _chain(connection: Connection, *, nodes: int = 1, aged: bool = False) -> Chain:
    workspace = _workspace(connection)
    run_id = _run(connection, workspace, aged=aged)
    node_ids = [_node(connection, workspace, run_id) for _ in range(nodes)]
    action_id, digest = _action(connection, workspace, run_id, evidence=node_ids[:1])
    return Chain(workspace, run_id, node_ids, action_id, digest)


def _review(
    connection: Connection, chain: Chain, *, action_id: str | None = None, **columns: Any
) -> str:
    """Insert one review row only. Schema 0006 requires `requested_at`, and a REVIEW decision
    that references the review by commit. Use `_reviewed` for a review that commits."""

    review_id = str(uuid4())
    payload: dict[str, Any] = {
        "id": review_id,
        "workspace": chain.workspace,
        "run": chain.run_id,
        "action": action_id or chain.action_id,
        "digest": chain.digest,
        "requested_at": connection.execute(text("SELECT now()")).scalar_one(),
        **columns,
    }
    execute(
        connection,
        """
        INSERT INTO reviews(id,workspace_id,run_id,action_id,digest,expires_at,requested_at)
        VALUES(:id,:workspace,:run,:action,:digest,now()+interval '10 minutes',:requested_at)
        """,
        payload,
    )
    return review_id


def _next_ordinal(connection: Connection, chain: Chain) -> int:
    return _count(
        connection,
        "SELECT COALESCE(max(ordinal),0)+1 FROM guard_decisions WHERE action_id=:a",
        a=chain.action_id,
    )


def _reviewed(connection: Connection, chain: Chain, **columns: Any) -> str:
    """A review as the runtime writes it: the review, then the REVIEW decision referencing it."""

    review_id = _review(connection, chain, **columns)
    _decision(
        connection,
        chain,
        ordinal=_next_ordinal(connection, chain),
        verdict="REVIEW",
        reasons=["MATERIAL_UNCERTAINTY"],
        review_id=review_id,
    )
    return review_id


def _decision(
    connection: Connection,
    chain: Chain,
    *,
    ordinal: int = 1,
    verdict: str = "ALLOW",
    reasons: object = None,
    digest: str | None = None,
    review_id: str | None = None,
    policy: str = "support-triage/1",
    version: str = "action-guard/1",
    action_id: str | None = None,
    workspace: str | None = None,
    run_id: str | None = None,
) -> str:
    decision_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO guard_decisions(
          id,workspace_id,run_id,action_id,ordinal,verdict,reasons,action_digest,
          policy_revision_observed,guard_version,review_id
        ) VALUES(
          :id,:workspace,:run,:action,:ordinal,:verdict,CAST(:reasons AS text[]),:digest,
          :policy,:version,:review
        )
        """,
        {
            "id": decision_id,
            "workspace": workspace or chain.workspace,
            "run": run_id or chain.run_id,
            "action": action_id or chain.action_id,
            "ordinal": ordinal,
            "verdict": verdict,
            "reasons": ["WITHIN_CONFIRMED_AUTHORITY"] if reasons is None else reasons,
            "digest": chain.digest if digest is None else digest,
            "policy": policy,
            "version": version,
            "review": review_id,
        },
    )
    return decision_id


def _committed(database: Engine, build: Callable[[Connection], Chain]) -> Chain:
    with database.begin() as connection:
        return build(connection)


def _rejects(
    database: Engine, pattern: str, attempt: Callable[..., object], *args: Any, **kwargs: Any
) -> None:
    """Run `attempt(connection, *args, **kwargs)` in one transaction that must fail."""

    with pytest.raises(DBAPIError, match=pattern):
        with database.begin() as connection:
            attempt(connection, *args, **kwargs)


def _update(connection: Connection, table: str, assignment: str, key: str) -> None:
    execute(connection, f"UPDATE {table} SET {assignment} WHERE id=:id", {"id": key})


def _count(connection: Connection, sql: str, **params: object) -> int:
    value = connection.execute(text(sql), params).scalar_one()
    assert isinstance(value, int)
    return value


# ---------------------------------------------------------------------------
# guard_decisions.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ordinals_are_contiguous_per_action(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _decision(connection, chain, ordinal=1, verdict="BLOCK", reasons=["INVALID_STATE"])
        _decision(connection, chain, ordinal=2)
        other_action, other_digest = _action(
            connection, chain.workspace, chain.run_id, evidence=chain.nodes
        )
        other = replace(chain, action_id=other_action, digest=other_digest)
        _decision(connection, other, ordinal=1)
        stored = rows(
            connection,
            """
            SELECT ordinal FROM guard_decisions WHERE action_id=:action ORDER BY ordinal
            """,
            {"action": chain.action_id},
        )
    assert stored == [{"ordinal": 1}, {"ordinal": 2}]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("existing", "ordinal"),
    [(0, 2), (0, 0), (0, -1), (1, 3), (1, 1), (2, 2), (2, 4)],
)
def test_gap_duplicate_and_stale_ordinals_fail(
    database: Engine, existing: int, ordinal: int
) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        for position in range(1, existing + 1):
            _decision(connection, chain, ordinal=position)
    _rejects(
        database,
        "guard_decision_ordinal_invalid",
        lambda connection: _decision(connection, chain, ordinal=ordinal),
    )
    with database.connect() as connection:
        assert (
            _count(
                connection,
                "SELECT count(*) FROM guard_decisions WHERE action_id=:a",
                a=chain.action_id,
            )
            == existing
        )


@pytest.mark.integration
def test_repeated_verdicts_and_more_than_two_decisions_are_not_forbidden(database: Engine) -> None:
    """The schema freezes no verdict-specific uniqueness and no maximum of two."""

    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _review(connection, chain)
        _decision(
            connection,
            chain,
            ordinal=1,
            verdict="REVIEW",
            reasons=["MATERIAL_UNCERTAINTY"],
            review_id=review,
        )
        _decision(
            connection,
            chain,
            ordinal=2,
            verdict="REVIEW",
            reasons=["MATERIAL_UNCERTAINTY"],
            review_id=review,
        )
        # An action that has a review: every later decision carries that review (0006).
        _decision(connection, chain, ordinal=3, review_id=review)
        _decision(connection, chain, ordinal=4, review_id=review)
        _decision(
            connection,
            chain,
            ordinal=5,
            verdict="BLOCK",
            reasons=["INVALID_STATE"],
            review_id=review,
        )
        total = _count(
            connection, "SELECT count(*) FROM guard_decisions WHERE action_id=:a", a=chain.action_id
        )
    assert total == 5


@pytest.mark.integration
@pytest.mark.parametrize("verdict", ["allow", "DENY", "", "ALLOW "])
def test_invalid_verdict_is_rejected(database: Engine, verdict: str) -> None:
    chain = _committed(database, _chain)
    _rejects(database, "guard_decision_verdict", lambda c: _decision(c, chain, verdict=verdict))


@pytest.mark.integration
@pytest.mark.parametrize("digest", ["", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "z" + "a" * 63])
def test_malformed_action_digest_is_rejected(database: Engine, digest: str) -> None:
    chain = _committed(database, _chain)
    _rejects(database, "guard_decision_digest", lambda c: _decision(c, chain, digest=digest))


@pytest.mark.integration
def test_decision_digest_must_equal_the_actions_immutable_digest(database: Engine) -> None:
    chain = _committed(database, _chain)
    wrong = "b" * 64 if chain.digest != "b" * 64 else "c" * 64
    _rejects(
        database,
        "guard_decisions_action_digest_fk",
        lambda c: _decision(c, chain, digest=wrong),
    )


@pytest.mark.integration
def test_decision_cannot_reference_an_action_of_another_run_or_workspace(database: Engine) -> None:
    mine = _committed(database, _chain)
    other = _committed(database, _chain)
    # Another run in the same workspace, and another workspace entirely.
    with database.begin() as connection:
        sibling_run = _run(connection, mine.workspace)
    for run_id, workspace in (
        (other.run_id, other.workspace),
        (sibling_run, mine.workspace),
        (other.run_id, mine.workspace),
        (mine.run_id, other.workspace),
    ):
        _rejects(
            database,
            "guard_decisions_action_digest_fk",
            _decision,
            mine,
            run_id=run_id,
            workspace=workspace,
        )
    with pytest.raises(DBAPIError, match="guard_decisions_action_digest_fk"):
        with database.begin() as connection:
            _decision(connection, mine, action_id=other.action_id, digest=other.digest)


@pytest.mark.integration
def test_review_verdict_requires_a_review(database: Engine) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "guard_decision_review_link",
        lambda c: _decision(c, chain, verdict="REVIEW", reasons=["MATERIAL_UNCERTAINTY"]),
    )
    with database.begin() as connection:
        review = _review(connection, chain)
        _decision(
            connection,
            chain,
            verdict="REVIEW",
            reasons=["MATERIAL_UNCERTAINTY"],
            review_id=review,
        )
        stored = one(
            connection,
            "SELECT review_id FROM guard_decisions WHERE action_id=:a",
            {"a": chain.action_id},
        )
    assert stored == {"review_id": review}


@pytest.mark.integration
def test_straight_allow_and_block_need_no_review(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _decision(connection, chain, ordinal=1, verdict="BLOCK", reasons=["GOAL_EXPIRED"])
        _decision(connection, chain, ordinal=2, verdict="ALLOW")
        nulls = _count(
            connection,
            "SELECT count(*) FROM guard_decisions WHERE action_id=:a AND review_id IS NULL",
            a=chain.action_id,
        )
    assert nulls == 2


@pytest.mark.integration
def test_review_must_belong_to_the_same_action_run_and_workspace(database: Engine) -> None:
    chain = _committed(database, _chain)
    other = _committed(database, _chain)
    with database.begin() as connection:
        other_action, other_digest = _action(
            connection, chain.workspace, chain.run_id, evidence=chain.nodes
        )
        sibling_run = _run(connection, chain.workspace)
        sibling_node = _node(connection, chain.workspace, sibling_run)
        sibling_action, sibling_digest = _action(
            connection, chain.workspace, sibling_run, evidence=[sibling_node]
        )
        same_workspace_other_run = Chain(
            chain.workspace, sibling_run, [sibling_node], sibling_action, sibling_digest
        )
        same_run_other_action = Chain(
            chain.workspace, chain.run_id, chain.nodes, other_action, other_digest
        )
        wrong_action_review = _reviewed(connection, same_run_other_action)
        sibling_review = _reviewed(connection, same_workspace_other_run)
        foreign_review = _reviewed(connection, other)
    for review in (wrong_action_review, sibling_review, foreign_review):
        _rejects(
            database,
            "guard_decisions_review_fk",
            _decision,
            chain,
            verdict="REVIEW",
            reasons=["MATERIAL_UNCERTAINTY"],
            review_id=review,
        )
        _rejects(
            database,
            "guard_decisions_review_fk",
            _decision,
            chain,
            review_id=review,
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "reasons",
    [
        ["WITHIN_CONFIRMED_AUTHORITY"],
        ["A"],
        ["_"],
        ["9"],
        ["A" * 64],
        ["TOOL_NOT_GRANTED", "GOAL_EXPIRED"],
        [f"R{index}" for index in range(16)],
        ["DUPLICATE", "DUPLICATE"],
    ],
)
def test_valid_reason_arrays_are_accepted(database: Engine, reasons: list[str]) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _decision(connection, chain, reasons=reasons)
        stored = one(
            connection,
            "SELECT reasons FROM guard_decisions WHERE action_id=:a",
            {"a": chain.action_id},
        )
    assert stored == {"reasons": reasons}


@pytest.mark.integration
@pytest.mark.parametrize(
    "reasons",
    [
        [],
        [f"R{index}" for index in range(17)],
        ["lowercase"],
        ["Mixed_Case"],
        ["HAS SPACE"],
        ["HAS-DASH"],
        ["A" * 65],
        [""],
        [" "],
        ["TRAILING_NEWLINE\n"],
        ["BAD", ""],
        ["GOOD", None],
        [None],
        [["A"], ["B"]],
        ["ÄÖ"],
    ],
)
def test_malformed_reason_arrays_are_rejected(database: Engine, reasons: object) -> None:
    chain = _committed(database, _chain)
    _rejects(database, "guard_decision_reasons", lambda c: _decision(c, chain, reasons=reasons))


@pytest.mark.integration
def test_reason_arrays_are_bounded_one_to_sixteen_and_match_the_guard(database: Engine) -> None:
    with database.connect() as connection:
        definition = connection.exec_driver_sql(
            "SELECT pg_get_functiondef('guard_reasons_valid(text[])'::regprocedure)"
        ).scalar_one()
    bounds = re.search(r"BETWEEN (\d+) AND (\d+)", definition)
    assert bounds is not None
    assert (int(bounds.group(1)), int(bounds.group(2))) == (1, 16)


@pytest.mark.integration
@pytest.mark.parametrize("value", ["", " ", " support-triage/1", "support-triage/1 ", "p" * 81])
def test_policy_revision_observed_is_trimmed_and_bounded(database: Engine, value: str) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "guard_decision_policy_revision",
        lambda c: _decision(c, chain, policy=value),
    )


@pytest.mark.integration
@pytest.mark.parametrize("value", ["", " ", " action-guard/1", "action-guard/1 ", "v" * 81])
def test_guard_version_is_trimmed_and_bounded(database: Engine, value: str) -> None:
    chain = _committed(database, _chain)
    _rejects(database, "guard_decision_version", lambda c: _decision(c, chain, version=value))


@pytest.mark.integration
def test_eighty_character_labels_are_accepted(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _decision(connection, chain, policy="p" * 80, version="v" * 80)


@pytest.mark.integration
@pytest.mark.parametrize(
    "assignment",
    [
        "verdict='BLOCK'",
        "reasons=ARRAY['CHANGED']",
        "ordinal=9",
        "guard_version='changed'",
        "policy_revision_observed='changed'",
        "evaluated_at=now()",
        "review_id=NULL",
    ],
)
def test_guard_decisions_are_append_only(database: Engine, assignment: str) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain)
    _rejects(
        database,
        "immutable_guard_decision",
        lambda c: execute(
            c, f"UPDATE guard_decisions SET {assignment} WHERE id=:id", {"id": decision}
        ),
    )


@pytest.mark.integration
def test_guard_decisions_table_exists(database: Engine) -> None:
    with database.connect() as connection:
        exists = connection.exec_driver_sql(
            "SELECT to_regclass('public.guard_decisions') IS NOT NULL"
        ).scalar_one()
    assert exists is True


@pytest.mark.integration
def test_deleting_an_action_removes_its_decisions_and_linked_execution(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain)
        ticket, _ = _ticket(connection, chain)
        _execution(connection, chain, ticket, guard_decision_id=decision)
    with database.begin() as connection:
        execute(connection, "DELETE FROM actions WHERE id=:a", {"a": chain.action_id})
    with database.connect() as connection:
        assert (
            _count(
                connection,
                "SELECT count(*) FROM guard_decisions WHERE action_id=:a",
                a=chain.action_id,
            )
            == 0
        )
        assert (
            _count(
                connection, "SELECT count(*) FROM executions WHERE action_id=:a", a=chain.action_id
            )
            == 0
        )
        assert (
            _count(connection, "SELECT count(*) FROM tickets WHERE action_id=:a", a=chain.action_id)
            == 0
        )


@pytest.mark.integration
def test_deleting_an_aged_run_cascades_through_the_whole_lineage(database: Engine) -> None:
    chain = _committed(database, lambda c: _chain(c, aged=True))
    with database.begin() as connection:
        review = _review(connection, chain)
        _decision(
            connection,
            chain,
            ordinal=1,
            verdict="REVIEW",
            reasons=["MATERIAL_UNCERTAINTY"],
            review_id=review,
        )
        allowed = _decision(connection, chain, ordinal=2, review_id=review)
        ticket, _ = _ticket(connection, chain)
        _execution(connection, chain, ticket, guard_decision_id=allowed)
    with database.begin() as connection:
        execute(connection, "DELETE FROM runs WHERE id=:r", {"r": chain.run_id})
    with database.connect() as connection:
        for table in ("guard_decisions", "reviews", "executions", "tickets", "actions"):
            assert (
                _count(connection, f"SELECT count(*) FROM {table} WHERE run_id=:r", r=chain.run_id)
                == 0
            )


# ---------------------------------------------------------------------------
# Reviews.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_new_review_without_requested_at_is_rejected(database: Engine) -> None:
    """Schema 0006: a new review always carries its request time. A historical review with
    no request time is covered by the populated 0005 upgrade tests, never by a fresh insert."""

    chain = _committed(database, _chain)
    _rejects(
        database,
        "review_requested_at_required",
        lambda c: _review(c, chain, requested_at=None),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "column", ["id", "workspace_id", "run_id", "action_id", "digest", "expires_at", "requested_at"]
)
def test_review_identity_digest_expiry_and_creation_are_frozen(
    database: Engine, column: str
) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        other_action, _ = _action(connection, chain.workspace, chain.run_id, evidence=chain.nodes)
        review = _reviewed(connection, chain)
    expressions = {
        "id": (":value", str(uuid4())),
        "workspace_id": (":value", str(uuid4())),
        "run_id": (":value", str(uuid4())),
        "action_id": (":value", other_action),
        "digest": (":value", "f" * 64),
        "expires_at": ("now()+interval '1 day'", None),
        "requested_at": ("now()", None),
    }
    expression, value = expressions[column]
    params: dict[str, object] = {"id": review}
    if value is not None:
        params["value"] = value
    _rejects(
        database,
        "immutable_review",
        lambda c: execute(c, f"UPDATE reviews SET {column}={expression} WHERE id=:id", params),
    )


@pytest.mark.integration
@pytest.mark.parametrize("expression", ["now()-interval '1 minute'", "now()+interval '1 day'"])
def test_review_expires_at_cannot_be_updated_through_the_production_trigger(
    database: Engine, expression: str
) -> None:
    """No trigger is disabled: the production `immutable_review` rejects the UPDATE."""

    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _reviewed(connection, chain)
        enabled = one(
            connection,
            "SELECT tgenabled FROM pg_trigger WHERE tgname='immutable_review' "
            "AND tgrelid='reviews'::regclass",
        )
        before = one(connection, "SELECT expires_at FROM reviews WHERE id=:id", {"id": review})
    assert enabled == {"tgenabled": "O"}
    assert before is not None
    _rejects(database, "immutable_review", _update, "reviews", f"expires_at={expression}", review)
    with database.connect() as connection:
        after = one(connection, "SELECT expires_at FROM reviews WHERE id=:id", {"id": review})
    assert after == before


@pytest.mark.integration
def test_requested_at_cannot_be_rewritten_or_removed(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        stamped = _reviewed(
            connection,
            chain,
            requested_at=connection.execute(text("SELECT now()-interval '1 minute'")).scalar_one(),
        )
        before = one(connection, "SELECT requested_at FROM reviews WHERE id=:id", {"id": stamped})
    for expression in ("now()", "NULL"):
        _rejects(
            database,
            "immutable_review",
            _update,
            "reviews",
            f"requested_at={expression}",
            stamped,
        )
    with database.connect() as connection:
        after = one(connection, "SELECT requested_at FROM reviews WHERE id=:id", {"id": stamped})
    assert after == before


@pytest.mark.integration
def test_the_current_writers_decision_and_consumption_shapes_are_accepted(
    database: Engine,
) -> None:
    """The shape of routes.decide_review and workflow.authorize, each with its timestamp."""

    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _reviewed(connection, chain)
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE reviews SET decision='approve',reviewer='user_reviewer',decided_at=now()
            WHERE id=:id
            """,
            {"id": review},
        )
    with database.begin() as connection:
        execute(
            connection,
            "UPDATE reviews SET consumed=true,consumed_at=now() WHERE id=:id",
            {"id": review},
        )
    with database.connect() as connection:
        stored = one(
            connection,
            """
            SELECT decision,reviewer,consumed,
                   decided_at IS NOT NULL AS decided,consumed_at IS NOT NULL AS stamped
            FROM reviews WHERE id=:id
            """,
            {"id": review},
        )
    assert stored == {
        "decision": "approve",
        "reviewer": "user_reviewer",
        "consumed": True,
        "decided": True,
        "stamped": True,
    }


@pytest.mark.integration
def test_decided_at_without_decision_or_reviewer_is_rejected(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _reviewed(connection, chain)
        other_action, other_digest = _action(
            connection, chain.workspace, chain.run_id, evidence=chain.nodes
        )
        decided = _reviewed(connection, replace(chain, action_id=other_action, digest=other_digest))
    for assignment, key in (
        ("decided_at=now()", review),
        ("decision='approve',decided_at=now()", decided),
        ("reviewer='user_reviewer',decided_at=now()", decided),
    ):
        _rejects(
            database,
            "invalid_review_decision_transition",
            lambda c, a=assignment, k=key: execute(
                c, f"UPDATE reviews SET {a} WHERE id=:id", {"id": k}
            ),
        )


@pytest.mark.integration
def test_consumed_at_without_consumed_is_rejected(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _reviewed(connection, chain)
    _rejects(
        database,
        "invalid_review_consumption_transition",
        lambda c: execute(c, "UPDATE reviews SET consumed_at=now() WHERE id=:id", {"id": review}),
    )


@pytest.mark.integration
def test_the_review_checks_from_0005_remain_as_a_backstop(database: Engine) -> None:
    with database.connect() as connection:
        names = set(
            connection.exec_driver_sql(
                "SELECT conname FROM pg_constraint WHERE conrelid='reviews'::regclass"
            ).scalars()
        )
        triggers = set(
            connection.exec_driver_sql(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid='reviews'::regclass AND NOT tgisinternal
                """
            ).scalars()
        )
    assert {"review_decided_at_requires_decision", "review_consumed_at_requires_consumed"} <= names
    assert triggers == {
        "immutable_review",
        "review_requested_at_required",
        "review_has_review_decision",
    }


# ---------------------------------------------------------------------------
# Action producer columns and protect_action.
# ---------------------------------------------------------------------------

TRIPLE = {
    "producer_provider": "groq",
    "producer_model": "requested-model",
    "producer_prompt_version": "support-analysis/1",
}


@pytest.mark.integration
def test_new_actions_require_the_producer_triplet_and_keep_the_response_id_optional(
    database: Engine,
) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _action(
            connection,
            chain.workspace,
            chain.run_id,
            evidence=chain.nodes,
            producer_response_id="resp_1",
        )
        _action(connection, chain.workspace, chain.run_id, evidence=chain.nodes, **TRIPLE)
        _action(
            connection,
            chain.workspace,
            chain.run_id,
            evidence=chain.nodes,
            producer_response_id="r" * 200,
            producer_provider="p" * 120,
            producer_model="m" * 120,
            producer_prompt_version="v" * 120,
        )


@pytest.mark.integration
@pytest.mark.parametrize("missing", list(TRIPLE))
def test_partial_producer_triplet_is_rejected(database: Engine, missing: str) -> None:
    chain = _committed(database, _chain)
    partial: dict[str, str | None] = {k: (None if k == missing else v) for k, v in TRIPLE.items()}
    _rejects(
        database,
        "action_producer_required|action_producer_triplet",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=chain.nodes, **partial),
    )
    only: dict[str, str | None] = {k: (v if k == missing else None) for k, v in TRIPLE.items()}
    _rejects(
        database,
        "action_producer_required|action_producer_triplet",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=chain.nodes, **only),
    )
    none: dict[str, str | None] = {k: None for k in TRIPLE}
    _rejects(
        database,
        "action_producer_required",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=chain.nodes, **none),
    )


@pytest.mark.integration
@pytest.mark.parametrize("column", list(TRIPLE))
@pytest.mark.parametrize("value", ["", " ", " x", "x ", "x" * 121])
def test_producer_triplet_values_are_trimmed_and_bounded(
    database: Engine, column: str, value: str
) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "action_producer_.*_length",
        lambda c: _action(
            c, chain.workspace, chain.run_id, evidence=chain.nodes, **{**TRIPLE, column: value}
        ),
    )


@pytest.mark.integration
@pytest.mark.parametrize("value", ["", " ", " x", "x ", "x" * 201])
def test_producer_response_id_is_null_or_trimmed_and_bounded(database: Engine, value: str) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "action_producer_response_id_length",
        lambda c: _action(
            c, chain.workspace, chain.run_id, evidence=chain.nodes, producer_response_id=value
        ),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "assignment",
    [
        "producer_provider='changed'",
        "producer_model='changed'",
        "producer_prompt_version='changed'",
        "producer_response_id='late'",
        "producer_response_id=NULL",
        "producer_provider=NULL",
    ],
)
def test_producer_fields_are_insert_time_evidence(database: Engine, assignment: str) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        stamped, _ = _action(
            connection,
            chain.workspace,
            chain.run_id,
            evidence=chain.nodes,
            producer_response_id="resp_1",
            **TRIPLE,
        )
    # A historical action with NULL producer columns cannot be inserted any more. Its
    # immutability is proven by the populated 0005 -> 0006 upgrade test.
    _rejects(database, "immutable_action", _update, "actions", assignment, stamped)


@pytest.mark.integration
def test_existing_frozen_action_fields_and_mutable_cache_are_unchanged(database: Engine) -> None:
    chain = _committed(database, _chain)
    for assignment in (
        "proposal=CAST('{}' AS jsonb)",
        "digest='" + "d" * 64 + "'",
        "run_id='" + str(uuid4()) + "'",
        "workspace_id='" + str(uuid4()) + "'",
    ):
        _rejects(
            database,
            "immutable_action",
            _update,
            "actions",
            assignment,
            chain.action_id,
        )
    with database.begin() as connection:
        execute(
            connection,
            """
            UPDATE actions SET verdict='REVIEW',reasons=CAST('["MATERIAL_UNCERTAINTY"]' AS jsonb)
            WHERE id=:id
            """,
            {"id": chain.action_id},
        )
        execute(
            connection,
            """
            UPDATE actions
            SET verdict='ALLOW',reasons=CAST('["WITHIN_CONFIRMED_AUTHORITY"]' AS jsonb)
            WHERE id=:id
            """,
            {"id": chain.action_id},
        )


# ---------------------------------------------------------------------------
# Action evidence database validation.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_one_evidence_id_is_accepted(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _action(connection, chain.workspace, chain.run_id, evidence=chain.nodes[:1])


@pytest.mark.integration
def test_sixteen_evidence_ids_are_accepted_and_seventeen_are_not(database: Engine) -> None:
    chain = _committed(database, lambda c: _chain(c, nodes=17))
    with database.begin() as connection:
        _action(connection, chain.workspace, chain.run_id, evidence=chain.nodes[:16])
    _rejects(
        database,
        "invalid_action_evidence",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=chain.nodes[:17]),
    )
    _rejects(
        database,
        "invalid_action_evidence",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=[chain.nodes[0]] * 17),
    )


@pytest.mark.integration
def test_duplicate_evidence_ids_are_accepted_and_the_proposal_is_not_rewritten(
    database: Engine,
) -> None:
    chain = _committed(database, _chain)
    duplicated = [chain.nodes[0]] * 3
    with database.begin() as connection:
        action_id, _ = _action(connection, chain.workspace, chain.run_id, evidence=duplicated)
        stored = one(connection, "SELECT proposal FROM actions WHERE id=:id", {"id": action_id})
    assert stored is not None
    assert stored["proposal"]["evidence_ids"] == duplicated


@pytest.mark.integration
@pytest.mark.parametrize(
    "evidence",
    [[], "text", {"a": 1}, 7, None, True],
)
def test_missing_empty_or_non_array_evidence_is_rejected(
    database: Engine, evidence: object
) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "invalid_action_evidence",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=evidence),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "proposal", ["{}", '{"tool":"tickets.create"}', "[]", "7", '"text"', "null"]
)
def test_proposal_without_an_evidence_array_is_rejected(database: Engine, proposal: str) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "invalid_action_evidence",
        lambda c: execute(
            c,
            """
            INSERT INTO actions(id,workspace_id,run_id,proposal,digest)
            VALUES(:id,:w,:r,CAST(:p AS jsonb),:d)
            """,
            {
                "id": str(uuid4()),
                "w": chain.workspace,
                "r": chain.run_id,
                "p": proposal,
                "d": "a" * 64,
            },
        ),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "form",
    ["upper", "no_hyphens", "braces", "short", "empty_string", "number", "nested", "null_item"],
)
def test_invalid_uuid_representation_is_rejected(database: Engine, form: str) -> None:
    chain = _committed(database, _chain)
    node = chain.nodes[0]
    bad: dict[str, object] = {
        "upper": node.upper(),
        "no_hyphens": node.replace("-", ""),
        "braces": "{" + node + "}",
        "short": node[:-1],
        "empty_string": "",
        "number": 1,
        "nested": [node],
        "null_item": None,
    }
    _rejects(
        database,
        "invalid_action_evidence",
        lambda c: _action(c, chain.workspace, chain.run_id, evidence=[node, bad[form]]),
    )


@pytest.mark.integration
def test_dangling_evidence_id_is_rejected(database: Engine) -> None:
    chain = _committed(database, _chain)
    _rejects(
        database,
        "invalid_action_evidence_reference",
        lambda c: _action(
            c, chain.workspace, chain.run_id, evidence=[chain.nodes[0], str(uuid4())]
        ),
    )


@pytest.mark.integration
def test_cross_run_and_cross_workspace_evidence_is_rejected(database: Engine) -> None:
    mine = _committed(database, _chain)
    foreign = _committed(database, _chain)
    with database.begin() as connection:
        sibling_run = _run(connection, mine.workspace)
        sibling_node = _node(connection, mine.workspace, sibling_run)
    for node in (sibling_node, foreign.nodes[0]):
        _rejects(
            database,
            "invalid_action_evidence_reference",
            _action,
            mine.workspace,
            mine.run_id,
            evidence=[node],
        )
        _rejects(
            database,
            "invalid_action_evidence_reference",
            _action,
            mine.workspace,
            mine.run_id,
            evidence=[mine.nodes[0], node],
        )


@pytest.mark.integration
def test_database_evidence_bound_equals_the_runtime_budget(database: Engine) -> None:
    with database.connect() as connection:
        definition = connection.exec_driver_sql(
            "SELECT pg_get_functiondef('enforce_action_evidence()'::regprocedure)"
        ).scalar_one()
    declared = re.findall(r"max_evidence_ids\s+CONSTANT\s+integer\s*:=\s*(\d+)", definition)
    assert declared == [str(BUDGETS.proposal_evidence_ids)]
    assert "NOT BETWEEN 1 AND max_evidence_ids" in definition


@pytest.mark.integration
def test_evidence_validation_does_not_replace_the_guards_completeness_checks(
    database: Engine,
) -> None:
    """An incomplete or expired but same-run node is still a valid reference."""

    chain = _committed(database, _chain)
    with database.begin() as connection:
        execute(
            connection,
            """
            INSERT INTO content_nodes(
              id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
            ) VALUES(
              :id,:w,:r,'pasted-email','user_schema',:d,'x','untrusted',false,
              now()-interval '1 hour'
            )
            """,
            {"id": (late := str(uuid4())), "w": chain.workspace, "r": chain.run_id, "d": "a" * 64},
        )
        _action(connection, chain.workspace, chain.run_id, evidence=[late])


# ---------------------------------------------------------------------------
# Tickets, executions, findings.
# ---------------------------------------------------------------------------


def _ticket(connection: Connection, chain: Chain) -> tuple[str, str]:
    ticket_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO tickets(id,workspace_id,run_id,action_id,title,body)
        VALUES(:id,:w,:r,:a,'Synthetic title','Synthetic body')
        """,
        {"id": ticket_id, "w": chain.workspace, "r": chain.run_id, "a": chain.action_id},
    )
    return ticket_id, chain.action_id


def _execution(
    connection: Connection,
    chain: Chain,
    ticket_id: str,
    *,
    guard_decision_id: str | None = None,
    digest: str | None = None,
) -> str:
    execution_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO executions(id,workspace_id,run_id,action_id,ticket_id,digest,guard_decision_id)
        VALUES(:id,:w,:r,:a,:t,:d,:g)
        """,
        {
            "id": execution_id,
            "w": chain.workspace,
            "r": chain.run_id,
            "a": chain.action_id,
            "t": ticket_id,
            "d": digest or chain.digest,
            "g": guard_decision_id,
        },
    )
    return execution_id


def _executed(database: Engine, *, decide: bool = True) -> tuple[Chain, str, str | None]:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain) if decide else None
        ticket, _ = _ticket(connection, chain)
        execution = _execution(connection, chain, ticket, guard_decision_id=decision)
    return chain, execution, decision


@pytest.mark.integration
def test_ticket_updates_are_rejected(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        ticket, _ = _ticket(connection, chain)
    for assignment in ("title='changed'", "body='changed'", "created_at=now()"):
        _rejects(
            database,
            "immutable_ticket",
            _update,
            "tickets",
            assignment,
            ticket,
        )


@pytest.mark.integration
def test_ticket_insert_and_cascade_delete_are_unchanged(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _ticket(connection, chain)
    with database.begin() as connection:
        execute(connection, "DELETE FROM actions WHERE id=:id", {"id": chain.action_id})
        assert (
            _count(connection, "SELECT count(*) FROM tickets WHERE run_id=:r", r=chain.run_id) == 0
        )


@pytest.mark.integration
def test_a_new_execution_without_a_guard_link_is_rejected(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        ticket, _ = _ticket(connection, chain)
    _rejects(
        database,
        "execution_guard_decision_required",
        lambda c: _execution(c, chain, ticket, guard_decision_id=None),
    )


@pytest.mark.integration
def test_execution_may_link_an_allow_decision_with_the_same_digest(database: Engine) -> None:
    chain, execution, decision = _executed(database)
    with database.connect() as connection:
        stored = one(
            connection, "SELECT guard_decision_id FROM executions WHERE id=:id", {"id": execution}
        )
    assert stored == {"guard_decision_id": decision}
    assert chain.digest


@pytest.mark.integration
@pytest.mark.parametrize("verdict", ["REVIEW", "BLOCK"])
def test_execution_cannot_link_a_non_allow_decision(database: Engine, verdict: str) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        review = _review(connection, chain) if verdict == "REVIEW" else None
        decision = _decision(
            connection,
            chain,
            verdict=verdict,
            reasons=["MATERIAL_UNCERTAINTY" if verdict == "REVIEW" else "INVALID_STATE"],
            review_id=review,
        )
        ticket, _ = _ticket(connection, chain)
    _rejects(
        database,
        "invalid_execution_guard_decision",
        lambda c: _execution(c, chain, ticket, guard_decision_id=decision),
    )


@pytest.mark.integration
def test_execution_digest_must_match_the_linked_decision_digest(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        decision = _decision(connection, chain)
        ticket, _ = _ticket(connection, chain)
    _rejects(
        database,
        "invalid_execution_guard_decision",
        lambda c: _execution(c, chain, ticket, guard_decision_id=decision, digest="9" * 64),
    )


@pytest.mark.integration
def test_execution_cannot_link_a_decision_of_another_action_run_or_workspace(
    database: Engine,
) -> None:
    mine = _committed(database, _chain)
    foreign = _committed(database, _chain)
    with database.begin() as connection:
        sibling_run = _run(connection, mine.workspace)
        sibling_node = _node(connection, mine.workspace, sibling_run)
        sibling_action, sibling_digest = _action(
            connection, mine.workspace, sibling_run, evidence=[sibling_node]
        )
        sibling = Chain(mine.workspace, sibling_run, [sibling_node], sibling_action, sibling_digest)
        other_action, other_digest = _action(
            connection, mine.workspace, mine.run_id, evidence=mine.nodes
        )
        same_run = replace(mine, action_id=other_action, digest=other_digest)
        decisions = [
            _decision(connection, foreign),
            _decision(connection, sibling),
            _decision(connection, same_run),
        ]
        ticket, _ = _ticket(connection, mine)
    for decision in decisions:
        _rejects(
            database,
            "invalid_execution_guard_decision|executions_guard_decision_fk",
            _execution,
            mine,
            ticket,
            guard_decision_id=decision,
        )
    _rejects(
        database,
        "invalid_execution_guard_decision|executions_guard_decision_fk",
        lambda c: _execution(c, mine, ticket, guard_decision_id=str(uuid4())),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "assignment",
    [
        "digest='" + "8" * 64 + "'",
        "committed_at=now()-interval '1 day'",
        "guard_decision_id=NULL",
        "workspace_id='{other}'",
        "run_id='{other}'",
        "action_id='{other}'",
        "ticket_id='{other}'",
        "id='{other}'",
    ],
)
def test_execution_structure_is_immutable(database: Engine, assignment: str) -> None:
    _, execution, _ = _executed(database)
    statement = assignment.replace("{other}", str(uuid4()))
    _rejects(
        database,
        "immutable_execution",
        lambda c: execute(c, f"UPDATE executions SET {statement} WHERE id=:id", {"id": execution}),
    )


@pytest.mark.integration
def test_linked_decision_cannot_be_attached_after_insert(database: Engine) -> None:
    chain, execution, _ = _executed(database)
    with database.begin() as connection:
        decision = _decision(connection, chain, ordinal=_next_ordinal(connection, chain))
    _rejects(
        database,
        "immutable_execution",
        lambda c: execute(
            c,
            "UPDATE executions SET guard_decision_id=:g WHERE id=:id",
            {"g": decision, "id": execution},
        ),
    )


@pytest.mark.integration
def test_verified_at_moves_from_null_to_a_timestamp_exactly_once(database: Engine) -> None:
    _, execution, _ = _executed(database)
    with database.begin() as connection:
        execute(
            connection, "UPDATE executions SET verified_at=NULL WHERE id=:id", {"id": execution}
        )
        execute(
            connection, "UPDATE executions SET verified_at=now() WHERE id=:id", {"id": execution}
        )
    for expression in ("now()+interval '1 minute'", "NULL"):
        _rejects(
            database,
            "immutable_execution",
            _update,
            "executions",
            f"verified_at={expression}",
            execution,
        )
    with database.connect() as connection:
        stored = one(
            connection, "SELECT verified_at FROM executions WHERE id=:id", {"id": execution}
        )
    assert stored is not None and stored["verified_at"] is not None


@pytest.mark.integration
def test_finding_insert_works_update_is_rejected_and_node_delete_cascades(database: Engine) -> None:
    chain = _committed(database, _chain)
    finding = str(uuid4())
    with database.begin() as connection:
        execute(
            connection,
            """
            INSERT INTO findings(
              id,workspace_id,run_id,node_id,origin,family,explanation,
              start_offset,end_offset,version
            ) VALUES(:id,:w,:r,:n,'deterministic','Instruction Override','Synthetic',0,4,'rules/1')
            """,
            {"id": finding, "w": chain.workspace, "r": chain.run_id, "n": chain.nodes[0]},
        )
    for assignment in (
        "explanation='changed'",
        "family='Role Change'",
        "end_offset=9",
        "node_id=node_id",
    ):
        _rejects(
            database,
            "immutable_finding",
            _update,
            "findings",
            assignment,
            finding,
        )
    with database.begin() as connection:
        execute(connection, "DELETE FROM content_nodes WHERE id=:n", {"n": chain.nodes[0]})
        assert _count(connection, "SELECT count(*) FROM findings WHERE id=:f", f=finding) == 0


# ---------------------------------------------------------------------------
# Derived node parent integrity.
# ---------------------------------------------------------------------------


def _edge(connection: Connection, workspace: str, run_id: str, parent: str, child: str) -> str:
    edge_id = str(uuid4())
    execute(
        connection,
        """
        INSERT INTO content_edges(
          id,workspace_id,run_id,parent_id,child_id,transform,version,lossy,transform_step_count
        ) VALUES(:id,:w,:r,:p,:c,'json-canonical','1',true,1)
        """,
        {"id": edge_id, "w": workspace, "r": run_id, "p": parent, "c": child},
    )
    execute(
        connection,
        """
        INSERT INTO content_edge_steps(edge_id,step_index,transform,version)
        VALUES(:edge,1,'json-canonical','1')
        """,
        {"edge": edge_id},
    )
    return edge_id


@pytest.mark.integration
def test_derived_node_with_its_edge_commits(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        child = _node(connection, chain.workspace, chain.run_id, origin="derived")
        _edge(connection, chain.workspace, chain.run_id, chain.nodes[0], child)
    with database.connect() as connection:
        stored = _count(
            connection,
            "SELECT count(*) FROM content_edges WHERE run_id=:r AND child_id=:c",
            r=chain.run_id,
            c=child,
        )
    assert stored == 1


@pytest.mark.integration
def test_derived_node_without_an_edge_fails_at_commit(database: Engine) -> None:
    chain = _committed(database, _chain)
    with pytest.raises(DBAPIError, match="derived_node_without_parent"):
        with database.begin() as connection:
            _node(connection, chain.workspace, chain.run_id, origin="derived")
    with database.connect() as connection:
        assert (
            _count(
                connection,
                "SELECT count(*) FROM content_nodes WHERE run_id=:r AND origin='derived'",
                r=chain.run_id,
            )
            == 0
        )


@pytest.mark.integration
def test_edge_of_a_different_child_does_not_satisfy_a_derived_node(database: Engine) -> None:
    chain = _committed(database, _chain)
    with pytest.raises(DBAPIError, match="derived_node_without_parent"):
        with database.begin() as connection:
            attached = _node(connection, chain.workspace, chain.run_id, origin="derived")
            _node(connection, chain.workspace, chain.run_id, origin="derived")
            _edge(connection, chain.workspace, chain.run_id, chain.nodes[0], attached)


@pytest.mark.integration
def test_derived_node_deleted_in_the_same_transaction_is_permitted(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        child = _node(connection, chain.workspace, chain.run_id, origin="derived")
        execute(connection, "DELETE FROM content_nodes WHERE id=:id", {"id": child})
    with database.connect() as connection:
        assert _count(connection, "SELECT count(*) FROM content_nodes WHERE id=:id", id=child) == 0


@pytest.mark.integration
def test_original_node_needs_no_parent(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        _node(connection, chain.workspace, chain.run_id, origin="pasted-email")


@pytest.mark.integration
def test_retention_cascade_still_removes_a_derived_node_edge_and_steps(database: Engine) -> None:
    chain = _committed(database, _chain)
    with database.begin() as connection:
        child = _node(connection, chain.workspace, chain.run_id, origin="derived")
        edge = _edge(connection, chain.workspace, chain.run_id, chain.nodes[0], child)
    with database.begin() as connection:
        execute(connection, "DELETE FROM content_nodes WHERE id=:id", {"id": child})
        assert _count(connection, "SELECT count(*) FROM content_edges WHERE id=:id", id=edge) == 0
        assert (
            _count(connection, "SELECT count(*) FROM content_edge_steps WHERE edge_id=:id", id=edge)
            == 0
        )


# ---------------------------------------------------------------------------
# Fresh migration, populated upgrade, downgrade refusal, readiness, parity.
# ---------------------------------------------------------------------------

COUNTED = [
    "workspaces",
    "memberships",
    "runs",
    "content_nodes",
    "content_edges",
    "content_edge_steps",
    "findings",
    "actions",
    "reviews",
    "tickets",
    "executions",
    "audit_events",
]
PARITY_TABLES = (
    "workspaces",
    "guard_decisions",
    "actions",
    "reviews",
    "executions",
    "tickets",
    "findings",
    "content_nodes",
    "content_edges",
)
PARITY_FUNCTIONS = (
    "protect_action",
    "protect_review",
    "protect_execution",
    "protect_ticket",
    "protect_finding",
    "protect_guard_decision",
    "enforce_guard_decision_ordinal",
    "enforce_execution_authorization",
    "enforce_action_evidence",
    "enforce_derived_node_parent",
    "guard_reasons_valid",
    "require_review_requested_at",
    "enforce_review_has_review_decision",
    "require_action_producer",
    "enforce_guard_decision_review_link",
)


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env={**os.environ, "VETOQ_DATABASE_URL": url, "PYTHONPATH": str(API_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )


def _recreate(name: str) -> None:
    assert DATABASE_URL is not None
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (name,)
        )
        connection.execute(f"DROP DATABASE IF EXISTS {name}")
        connection.execute(f"CREATE DATABASE {name}")


def _drop(name: str) -> None:
    assert DATABASE_URL is not None
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (name,)
        )
        connection.execute(f"DROP DATABASE IF EXISTS {name}")


def _counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {table: _count(connection, f"SELECT count(*) FROM {table}") for table in COUNTED}


def _execution_indexes(connection: Connection) -> dict[str, list[str]]:
    found = connection.execute(
        text(
            """
            SELECT i.relname, array_agg(a.attname ORDER BY x.ordinality) AS columns
            FROM pg_index ix
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN unnest(ix.indkey) WITH ORDINALITY AS x(attnum, ordinality) ON true
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.attnum
            WHERE t.relname = 'executions' AND t.relkind = 'r'
            GROUP BY i.relname
            """
        )
    ).all()
    return {str(name): list(columns) for name, columns in found}


def _populate_legacy(engine: Engine) -> dict[str, str]:
    """Rows exactly as schema 0004 and the M003 writers leave them."""

    ids = {name: str(uuid4()) for name in ("w", "run", "orig", "child", "edge", "finding")}
    ids.update({name: str(uuid4()) for name in ("action", "review", "ticket", "execution")})
    ids["orphan"] = str(uuid4())
    principal = "user_" + uuid4().hex
    with engine.begin() as c:
        execute(c, "INSERT INTO workspaces(id,name) VALUES(:w,'Legacy')", ids)
        execute(
            c,
            "INSERT INTO memberships(workspace_id,principal,role) VALUES(:w,:p,'reviewer')",
            {**ids, "p": principal},
        )
        execute(
            c,
            """
            INSERT INTO runs(
              id,workspace_id,principal,submission_key,submission_digest,
              envelope,state,expires_at,cancelled
            ) VALUES(:r,:w,:p,:k,'d',CAST('{}' AS jsonb),'CANCELLED',
              now()+interval '30 minutes',true)
            """,
            {"r": ids["run"], "w": ids["w"], "p": principal, "k": uuid4().hex},
        )
        for node, origin in (("orig", "pasted-email"), ("child", "derived"), ("orphan", "derived")):
            execute(
                c,
                """
                INSERT INTO content_nodes(
                  id,workspace_id,run_id,origin,supplier,digest,content,trust,complete,expires_at
                ) VALUES(:n,:w,:r,:o,'user_legacy',:d,'legacy','untrusted',true,
                  now()+interval '24 hours')
                """,
                {"n": ids[node], "w": ids["w"], "r": ids["run"], "o": origin, "d": "a" * 64},
            )
        execute(
            c,
            """
            INSERT INTO content_edges(
              id,workspace_id,run_id,parent_id,child_id,transform,version,lossy,
              transform_step_count
            ) VALUES(:edge,:w,:run,:orig,:child,'base64','1',false,1)
            """,
            ids,
        )
        execute(
            c,
            "INSERT INTO content_edge_steps(edge_id,step_index,transform,version) "
            "VALUES(:edge,1,'base64','1')",
            ids,
        )
        execute(
            c,
            """
            INSERT INTO findings(
              id,workspace_id,run_id,node_id,origin,family,explanation,
              start_offset,end_offset,version
            ) VALUES(:finding,:w,:run,:orig,'deterministic','Role Change','legacy',0,1,'rules/1')
            """,
            ids,
        )
        # A legacy proposal: no evidence validation existed at 0004.
        execute(
            c,
            """
            INSERT INTO actions(id,workspace_id,run_id,proposal,digest,verdict,reasons)
            VALUES(:action,:w,:run,CAST('{"legacy": true}' AS jsonb),:d,'ALLOW',
              CAST('["WITHIN_CONFIRMED_AUTHORITY"]' AS jsonb))
            """,
            {**ids, "d": "c" * 64},
        )
        execute(
            c,
            """
            INSERT INTO reviews(id,workspace_id,run_id,action_id,digest,expires_at)
            VALUES(:review,:w,:run,:action,:d,now()+interval '10 minutes')
            """,
            {**ids, "d": "c" * 64},
        )
        execute(
            c,
            """
            INSERT INTO tickets(id,workspace_id,run_id,action_id,title,body)
            VALUES(:ticket,:w,:run,:action,'Legacy','Legacy body')
            """,
            ids,
        )
        execute(
            c,
            """
            INSERT INTO executions(id,workspace_id,run_id,action_id,ticket_id,digest)
            VALUES(:execution,:w,:run,:action,:ticket,:d)
            """,
            {**ids, "d": "c" * 64},
        )
        execute(
            c,
            """
            INSERT INTO audit_events(workspace_id,run_id,sequence,actor,type,detail)
            VALUES(:w,:run,1,'runner','LEGACY',CAST('{}' AS jsonb))
            """,
            ids,
        )
    return ids


def _signature(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        tables = ", ".join(f"'{t}'::regclass" for t in PARITY_TABLES)
        names = ", ".join(f"'{t}'" for t in PARITY_TABLES)
        functions = ", ".join(f"'{f}'" for f in PARITY_FUNCTIONS)
        return {
            "columns": connection.exec_driver_sql(
                f"""
                SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name IN ({names})
                ORDER BY table_name, column_name
                """
            ).all(),
            "constraints": connection.exec_driver_sql(
                f"""
                SELECT conrelid::regclass::text, conname, contype, pg_get_constraintdef(oid)
                FROM pg_constraint WHERE conrelid IN ({tables}) ORDER BY 1, 2
                """
            ).all(),
            "indexes": connection.exec_driver_sql(
                f"""
                SELECT tablename, indexname, indexdef FROM pg_indexes
                WHERE schemaname='public' AND tablename IN ({names}) ORDER BY 1, 2
                """
            ).all(),
            "triggers": connection.exec_driver_sql(
                f"""
                SELECT tgrelid::regclass::text, tgname, tgenabled, pg_get_triggerdef(oid)
                FROM pg_trigger WHERE tgrelid IN ({tables}) AND NOT tgisinternal ORDER BY 1, 2
                """
            ).all(),
            "functions": connection.exec_driver_sql(
                f"""
                SELECT proname, pg_get_functiondef(oid) FROM pg_proc
                WHERE pronamespace='public'::regnamespace AND proname IN ({functions})
                ORDER BY 1
                """
            ).all(),
            "revision": connection.exec_driver_sql("SELECT version_num FROM alembic_version").all(),
        }


class ScratchUrls(dict[str, str]):
    """Connection strings carry credentials, so a failure report must not print them."""

    def __repr__(self) -> str:
        return "<scratch database urls redacted>"


@pytest.fixture(scope="module")
def scratch() -> Iterator[dict[str, str]]:
    if not DATABASE_URL:
        pytest.skip("VETOQ_TEST_DATABASE_URL is not configured")
    require_disposable_url(DATABASE_URL, DEVELOPMENT_URLS)
    fresh_url = _replace_database(DATABASE_URL, FRESH_DATABASE)
    upgrade_url = _replace_database(DATABASE_URL, UPGRADE_DATABASE)
    require_disposable_url(fresh_url, DEVELOPMENT_URLS)
    require_disposable_url(upgrade_url, DEVELOPMENT_URLS)
    _recreate(FRESH_DATABASE)
    _recreate(UPGRADE_DATABASE)
    try:
        yield ScratchUrls(fresh=fresh_url, upgrade=upgrade_url)
    finally:
        _drop(FRESH_DATABASE)
        _drop(UPGRADE_DATABASE)


@pytest.mark.integration
def test_fresh_database_migrates_from_base_to_0007(scratch: dict[str, str]) -> None:
    completed = _alembic(scratch["fresh"], "upgrade", "head")
    assert completed.returncode == 0, completed.stderr.replace(scratch["fresh"], "[redacted]")
    heads = _alembic(scratch["fresh"], "heads")
    assert heads.stdout.count("(head)") == 1 and HEAD in heads.stdout
    engine = _engine(scratch["fresh"])
    try:
        require_disposable_engine(engine)
        with engine.connect() as connection:
            version = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            tables = set(
                connection.exec_driver_sql(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                ).scalars()
            )
            decisions = _count(connection, "SELECT count(*) FROM guard_decisions")
            definition = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname=:name"
                ),
                {"name": EXECUTIONS_RUN_INDEX},
            ).scalar_one()
        assert version == HEAD
        assert "guard_decisions" in tables
        assert decisions == 0
        assert definition == (
            "CREATE INDEX executions_workspace_run_idx ON public.executions "
            "USING btree (workspace_id, run_id)"
        )
        assert database_available(scratch["fresh"]) is True
    finally:
        engine.dispose()


@pytest.mark.integration
def test_populated_0004_database_upgrades_through_0007_without_changing_legacy_rows(
    scratch: dict[str, str],
) -> None:
    url = scratch["upgrade"]
    assert _alembic(url, "upgrade", "0004_edge_steps").returncode == 0
    assert database_available(url) is False, "readiness must require the current revision"
    engine = _engine(url)
    try:
        require_disposable_engine(engine)
        ids = _populate_legacy(engine)
        before = _counts(engine)
        with engine.connect() as connection:
            snapshot = {
                table: rows(connection, f"SELECT * FROM {table} ORDER BY 1")
                for table in ("actions", "reviews", "tickets", "executions", "findings")
            }
        assert min(before[t] for t in ("actions", "reviews", "tickets", "executions")) == 1
        completed = _alembic(url, "upgrade", TOLERANT)
        assert completed.returncode == 0, completed.stderr.replace(url, "[redacted]")
        assert _counts(engine) == before
        with engine.connect() as connection:
            for table, original in snapshot.items():
                current = rows(connection, f"SELECT * FROM {table} ORDER BY 1")
                for old, new in zip(original, current, strict=True):
                    assert {k: new[k] for k in old} == old
            assert _count(connection, "SELECT count(*) FROM guard_decisions") == 0
            assert (
                _count(
                    connection,
                    """
                    SELECT count(*) FROM actions WHERE producer_provider IS NOT NULL
                      OR producer_model IS NOT NULL OR producer_prompt_version IS NOT NULL
                      OR producer_response_id IS NOT NULL
                    """,
                )
                == 0
            )
            assert (
                _count(
                    connection,
                    """
                    SELECT count(*) FROM reviews WHERE requested_at IS NOT NULL
                      OR decided_at IS NOT NULL OR consumed_at IS NOT NULL
                    """,
                )
                == 0
            )
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM executions WHERE guard_decision_id IS NOT NULL",
                )
                == 0
            )
            # A legacy derived node with no edge is reported, never rewritten or removed.
            assert (
                _count(
                    connection,
                    "SELECT count(*) FROM content_nodes WHERE id=:id",
                    id=ids["orphan"],
                )
                == 1
            )
        assert database_available(url) is False, "0005 is no longer the readiness revision"
        # Legacy rows keep working under the tolerant guards.
        with engine.begin() as connection:
            execute(
                connection,
                "UPDATE reviews SET decision='approve',reviewer='legacy' WHERE id=:review",
                ids,
            )
            execute(connection, "UPDATE reviews SET consumed=true WHERE id=:review", ids)
            execute(connection, "UPDATE executions SET verified_at=now() WHERE id=:execution", ids)
            execute(
                connection,
                "UPDATE actions SET verdict='BLOCK',reasons=CAST('[\"INVALID_STATE\"]' AS jsonb) "
                "WHERE id=:action",
                ids,
            )
        assert _counts(engine) == before
        with engine.connect() as connection:
            mutated = {
                table: rows(connection, f"SELECT * FROM {table} ORDER BY 1")
                for table in ("actions", "reviews", "executions")
            }
        # Rows in the legacy states (decided without decided_at, consumed without consumed_at,
        # NULL producer trio, NULL decision link) survive the strict revision unchanged.
        completed = _alembic(url, "upgrade", ENFORCEMENT)
        assert completed.returncode == 0, completed.stderr.replace(url, "[redacted]")
        assert _counts(engine) == before
        with engine.connect() as connection:
            for table, original in mutated.items():
                assert rows(connection, f"SELECT * FROM {table} ORDER BY 1") == original
            at_enforcement = rows(connection, "SELECT * FROM executions ORDER BY 1")
            before_index = _execution_indexes(connection)
        assert EXECUTIONS_RUN_INDEX not in before_index
        completed = _alembic(url, "upgrade", "head")
        assert completed.returncode == 0, completed.stderr.replace(url, "[redacted]")
        assert _counts(engine) == before
        with engine.connect() as connection:
            for table, original in mutated.items():
                assert rows(connection, f"SELECT * FROM {table} ORDER BY 1") == original
            assert rows(connection, "SELECT * FROM executions ORDER BY 1") == at_enforcement
            after_index = _execution_indexes(connection)
        assert EXECUTIONS_RUN_INDEX in after_index
        assert after_index[EXECUTIONS_RUN_INDEX] == ["workspace_id", "run_id"]
        equivalents = [
            name
            for name, columns in after_index.items()
            if columns[:2] == ["workspace_id", "run_id"]
        ]
        assert equivalents == [EXECUTIONS_RUN_INDEX]
        assert database_available(url) is True
    finally:
        engine.dispose()


@pytest.mark.integration
def test_0007_downgrade_is_refused(scratch: dict[str, str]) -> None:
    url = scratch["upgrade"]
    assert _alembic(url, "upgrade", "head").returncode == 0
    result = _alembic(url, "downgrade", "0004_edge_steps")
    assert result.returncode != 0
    assert "Destructive rollback requires an explicit operator recovery plan" in result.stderr
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            version = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            present = connection.exec_driver_sql(
                "SELECT to_regclass('public.guard_decisions') IS NOT NULL"
            ).scalar_one()
        assert (version, present) == (HEAD, True)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_fresh_upgraded_test_and_development_schemas_are_equivalent(
    scratch: dict[str, str],
) -> None:
    assert DATABASE_URL is not None
    development = next(
        (url for url in DEVELOPMENT_URLS if urlsplit(url).path.strip("/") == "vetoq"), None
    )
    if development is None:
        pytest.fail("development database name is not the expected local name")
    fresh, upgraded = _engine(scratch["fresh"]), _engine(scratch["upgrade"])
    test, live = _engine(DATABASE_URL), _engine(development)
    try:
        require_disposable_engine(fresh)
        require_disposable_engine(upgraded)
        require_disposable_engine(test)
        reference = _signature(fresh)
        assert reference["revision"] == [(HEAD,)]
        assert len(reference["columns"]) > 0  # type: ignore[arg-type]
        for name, engine in (("upgraded", upgraded), ("test", test), ("development", live)):
            candidate = _signature(engine)
            for key, value in reference.items():
                assert candidate[key] == value, f"{name} differs from a fresh database in {key}"
    finally:
        for engine in (fresh, upgraded, test, live):
            engine.dispose()


@pytest.mark.integration
def test_executions_workspace_run_idx_exists_with_exact_filter_columns(
    database: Engine,
) -> None:
    with database.connect() as connection:
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        indexes = _execution_indexes(connection)
        definition = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname=:name"),
            {"name": EXECUTIONS_RUN_INDEX},
        ).scalar_one()
    assert version == HEAD
    assert indexes[EXECUTIONS_RUN_INDEX] == ["workspace_id", "run_id"]
    assert definition == (
        "CREATE INDEX executions_workspace_run_idx ON public.executions "
        "USING btree (workspace_id, run_id)"
    )
    equivalents = [
        name for name, columns in indexes.items() if columns[:2] == ["workspace_id", "run_id"]
    ]
    assert equivalents == [EXECUTIONS_RUN_INDEX]


@pytest.mark.integration
def test_the_lineage_functions_use_the_expected_error_names(database: Engine) -> None:
    with database.connect() as connection:
        raised = {
            name: connection.exec_driver_sql(
                "SELECT pg_get_functiondef(%s::regproc)", (name,)
            ).scalar_one()
            for name in PARITY_FUNCTIONS
            if name != "guard_reasons_valid"
        }
    expected = {
        "protect_review": "immutable_review",
        "protect_execution": "immutable_execution",
        "protect_ticket": "immutable_ticket",
        "protect_finding": "immutable_finding",
        "protect_guard_decision": "immutable_guard_decision",
        "protect_action": "immutable_action",
        "enforce_guard_decision_ordinal": "guard_decision_ordinal_invalid",
        "enforce_execution_authorization": "execution_guard_decision_required",
        "require_review_requested_at": "review_requested_at_required",
        "enforce_review_has_review_decision": "review_without_review_decision",
        "require_action_producer": "action_producer_required",
        "enforce_guard_decision_review_link": "guard_decision_review_link_required",
        "enforce_derived_node_parent": "derived_node_without_parent",
    }
    for name, message in expected.items():
        assert message in raised[name]
