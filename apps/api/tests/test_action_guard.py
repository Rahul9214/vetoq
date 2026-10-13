from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from vetoq.action_guard import GuardInput, guard
from vetoq.contracts import GoalLock, Proposal, TicketArguments, action_digest

WORKSPACE_A = UUID("00000000-0000-4000-8000-00000000000a")
WORKSPACE_B = UUID("00000000-0000-4000-8000-00000000000b")
SOURCE = UUID("00000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 10, 9, tzinfo=UTC)


def values() -> tuple[GoalLock, Proposal, GuardInput]:
    envelope = GoalLock(
        principal="user_operator",
        workspace_id=WORKSPACE_A,
        source_id=SOURCE,
        source_digest="a" * 64,
        goal="Create one support ticket in workspace A.",
        expires_at=NOW + timedelta(minutes=30),
    )
    proposal = Proposal(
        tool="tickets.create",
        tool_version=1,
        arguments=TicketArguments(
            workspace_id=WORKSPACE_A,
            title="Unable to sign in",
            body="Synthetic customer cannot sign in after a password reset.",
        ),
        evidence_ids=[SOURCE],
    )
    inputs = GuardInput(
        run_id="run-1",
        principal="user_operator",
        envelope=envelope,
        proposal=proposal,
        persisted_digest=action_digest("run-1", envelope, proposal),
        now=NOW,
        membership_active=True,
        workspace_active=True,
        policy_revision="support-triage/1",
        state="AUTHORIZING",
        writes=0,
        proposals=1,
        complete=True,
        source_ids=frozenset({str(SOURCE)}),
        uncertain=False,
    )
    return envelope, proposal, inputs


def test_exact_authorized_action_is_allowed() -> None:
    assert guard(values()[2]).verdict == "ALLOW"


def test_same_tool_wrong_workspace_is_blocked_even_with_membership() -> None:
    envelope, proposal, inputs = values()
    wrong = proposal.model_copy(
        update={"arguments": proposal.arguments.model_copy(update={"workspace_id": WORKSPACE_B})}
    )
    changed = replace(
        inputs,
        proposal=wrong,
        persisted_digest=action_digest("run-1", envelope, wrong),
        membership_active=True,
    )
    decision = guard(changed)
    assert decision.verdict == "BLOCK"
    assert "GOAL_SCOPE_MISMATCH" in decision.reasons


def test_unknown_tool_and_incomplete_analysis_fail_closed() -> None:
    envelope, proposal, inputs = values()
    unknown = proposal.model_copy(update={"tool": "secrets.read"})
    decision = guard(
        replace(
            inputs,
            proposal=unknown,
            persisted_digest=action_digest("run-1", envelope, unknown),
            complete=False,
        )
    )
    assert decision.verdict == "BLOCK"
    assert {"TOOL_NOT_GRANTED", "INCOMPLETE_OR_INVALID_EVIDENCE"}.issubset(decision.reasons)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"cancelled": True}, "REVOKED_OR_CANCELLED"),
        ({"membership_active": False}, "IDENTITY_OR_MEMBERSHIP_INVALID"),
        ({"policy_revision": "missing"}, "POLICY_UNAVAILABLE_OR_STALE"),
        ({"writes": 1}, "LIMIT_EXHAUSTED"),
        ({"execution_exists": True}, "ALREADY_EXECUTED"),
        ({"now": NOW + timedelta(hours=1)}, "GOAL_EXPIRED"),
    ],
)
def test_hard_failures_never_allow(change: dict[str, Any], reason: str) -> None:
    decision = guard(replace(values()[2], **change))
    assert decision.verdict == "BLOCK"
    assert reason in decision.reasons


def test_argument_mutation_invalidates_digest() -> None:
    _, proposal, inputs = values()
    changed = proposal.model_copy(
        update={"arguments": proposal.arguments.model_copy(update={"title": "Changed"})}
    )
    decision = guard(replace(inputs, proposal=changed))
    assert decision.verdict == "BLOCK"
    assert "ARGUMENT_OR_ENVELOPE_MUTATION" in decision.reasons


def test_originator_approval_is_never_allow() -> None:
    _, _, inputs = values()
    decision = guard(
        replace(
            inputs,
            uncertain=True,
            approval_digest=inputs.persisted_digest,
            approval_expires=NOW + timedelta(minutes=5),
            reviewer_active=True,
            reviewer_is_originator=True,
        )
    )
    assert decision.verdict == "BLOCK"
    assert decision.reasons == ["SELF_REVIEW_PROHIBITED"]


def test_scope_mismatch_cannot_be_approved_into_allow() -> None:
    envelope, proposal, inputs = values()
    wrong = proposal.model_copy(
        update={"arguments": proposal.arguments.model_copy(update={"workspace_id": WORKSPACE_B})}
    )
    decision = guard(
        replace(
            inputs,
            proposal=wrong,
            persisted_digest=action_digest("run-1", envelope, wrong),
            uncertain=True,
            approval_digest=action_digest("run-1", envelope, wrong),
            approval_expires=NOW + timedelta(minutes=5),
            reviewer_active=True,
        )
    )
    assert decision.verdict == "BLOCK"
    assert "GOAL_SCOPE_MISMATCH" in decision.reasons


def test_mutated_arguments_do_not_inherit_approval() -> None:
    envelope, proposal, inputs = values()
    changed = proposal.model_copy(
        update={
            "arguments": proposal.arguments.model_copy(update={"title": "Changed after approval"})
        }
    )
    stale = guard(
        replace(
            inputs,
            proposal=changed,
            uncertain=True,
            approval_digest=inputs.persisted_digest,
            approval_expires=NOW + timedelta(minutes=5),
            reviewer_active=True,
        )
    )
    assert stale.verdict == "BLOCK"
    assert "ARGUMENT_OR_ENVELOPE_MUTATION" in stale.reasons
    fresh_digest = action_digest(inputs.run_id, envelope, changed)
    inherited = guard(
        replace(
            inputs,
            proposal=changed,
            persisted_digest=fresh_digest,
            uncertain=True,
            approval_digest=inputs.persisted_digest,
            approval_expires=NOW + timedelta(minutes=5),
            reviewer_active=True,
        )
    )
    assert inherited.verdict == "BLOCK"
    assert "APPROVAL_INVALID_OR_STALE" in inherited.reasons


def test_uncertainty_requires_exact_fresh_single_use_review() -> None:
    inputs = replace(values()[2], uncertain=True)
    assert guard(inputs).verdict == "REVIEW"
    allowed = replace(
        inputs,
        approval_digest=inputs.persisted_digest,
        approval_expires=NOW + timedelta(minutes=5),
        reviewer_active=True,
    )
    assert guard(allowed).verdict == "ALLOW"
    assert guard(replace(allowed, approval_consumed=True)).verdict == "BLOCK"
    assert guard(replace(allowed, approval_expires=NOW)).verdict == "BLOCK"
    assert guard(replace(allowed, approval_digest="f" * 64)).verdict == "BLOCK"
