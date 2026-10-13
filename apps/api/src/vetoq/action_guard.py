"""Pure authorization. No provider, transport, database, or execution imports."""

from dataclasses import dataclass
from datetime import datetime

from vetoq.contracts import POLICY, Decision, GoalLock, Proposal, action_digest


@dataclass(frozen=True)
class GuardInput:
    run_id: str
    principal: str
    envelope: GoalLock
    proposal: Proposal
    persisted_digest: str
    now: datetime
    membership_active: bool
    workspace_active: bool
    policy_revision: str
    state: str
    writes: int
    proposals: int
    complete: bool
    source_ids: frozenset[str]
    uncertain: bool
    cancelled: bool = False
    execution_exists: bool = False
    approval_digest: str | None = None
    approval_expires: datetime | None = None
    approval_consumed: bool = False
    reviewer_active: bool = False
    reviewer_is_originator: bool = False


def guard(i: GuardInput) -> Decision:
    reasons: list[str] = []
    g, p = i.envelope, i.proposal
    if not i.membership_active or i.principal != g.principal:
        reasons.append("IDENTITY_OR_MEMBERSHIP_INVALID")
    if not i.workspace_active or i.cancelled:
        reasons.append("REVOKED_OR_CANCELLED")
    if i.state not in {"AUTHORIZING", "AWAITING_REVIEW"}:
        reasons.append("INVALID_STATE")
    if p.tool != g.tool or p.tool_version != g.tool_version:
        reasons.append("TOOL_NOT_GRANTED")
    if p.arguments.workspace_id != g.workspace_id:
        reasons.append("GOAL_SCOPE_MISMATCH")
    if i.policy_revision != POLICY or g.policy_revision != i.policy_revision:
        reasons.append("POLICY_UNAVAILABLE_OR_STALE")
    if i.now >= g.expires_at:
        reasons.append("GOAL_EXPIRED")
    if i.writes >= g.max_writes or not 1 <= i.proposals <= g.max_proposals:
        reasons.append("LIMIT_EXHAUSTED")
    if not i.complete or not {str(x) for x in p.evidence_ids}.issubset(i.source_ids):
        reasons.append("INCOMPLETE_OR_INVALID_EVIDENCE")
    if action_digest(i.run_id, g, p) != i.persisted_digest:
        reasons.append("ARGUMENT_OR_ENVELOPE_MUTATION")
    if i.execution_exists:
        reasons.append("ALREADY_EXECUTED")
    if reasons:
        return Decision(verdict="BLOCK", reasons=reasons)
    if i.uncertain:
        if i.approval_digest is None:
            return Decision(verdict="REVIEW", reasons=["MATERIAL_UNCERTAINTY"])
        if i.reviewer_is_originator:
            return Decision(verdict="BLOCK", reasons=["SELF_REVIEW_PROHIBITED"])
        if (
            i.approval_digest != i.persisted_digest
            or i.approval_consumed
            or not i.reviewer_active
            or i.approval_expires is None
            or i.now >= i.approval_expires
        ):
            return Decision(verdict="BLOCK", reasons=["APPROVAL_INVALID_OR_STALE"])
    return Decision(verdict="ALLOW", reasons=["WITHIN_CONFIRMED_AUTHORITY"])
