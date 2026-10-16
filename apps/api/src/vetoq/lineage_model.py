"""Typed, structural read model of one run's lineage.

Lineage describes what happened. It is output evidence and never an input to
authorization: nothing here is imported by the workflow or the Action Guard, and
nothing here grants or widens authority.

The model carries structural metadata only. It never carries a content body, ticket
text, a finding explanation, or model text. Facts the database did not record are
`not_recorded`, never invented. A recorded fact that contradicts another recorded fact is
reported as an integrity finding, so a missing historical fact and an anomaly are never
the same thing.

Stable entity identities, with the persisted id after the colon:
`goal_lock:<run_id>`, `content:<id>`, `finding:<id>`, `proposal:<action_id>`,
`guard_decision:<id>`, `review:<id>`, `execution:<id>`, `ticket:<id>`.
"""

from datetime import datetime
from typing import Final, Literal

from vetoq.contracts import Strict
from vetoq.ingestion.limits import BUDGETS

Check = Literal["consistent", "inconsistent", "unverifiable", "not_recorded"]
Basis = Literal[
    "structural_fk",
    "digest_bound_json",
    "derived_join",
    "envelope_binding",
    "not_recorded",
]
BodyState = Literal["available", "expired_body_pending_deletion"]
# `removed_by_retention` is reserved and currently unreachable: no persisted fact records that
# the `retain` command, rather than any other delete, removed content. The read model never
# emits it. An absent original is `inconsistent` or `unverifiable`, never removed by retention.
RetentionState = Literal[
    "available",
    "expired_body_pending_deletion",
    "removed_by_retention",
    "inconsistent",
    "unverifiable",
]
Stage = Literal[
    "proposed",
    "review_pending",
    "blocked",
    "authorized",
    "executed",
    "verified",
    "expired",
    "cancelled",
    "failed",
    "latest_only",
]
RelationKind = Literal[
    "goal_lock_binds_source",
    "goal_lock_binds_proposal",
    "derived_from",
    "finding_on_content",
    "proposal_cites_content",
    "finding_on_cited_evidence",
    "guard_decision_evaluates",
    "guard_decision_references_review",
    "review_for_proposal",
    "execution_of_proposal",
    "execution_authorized_by",
    "execution_produced_ticket",
]
IntegrityCode = Literal[
    "bound_exceeded",
    "scope_mismatch",
    "envelope_invalid",
    "source_missing_before_retention",
    "source_missing_retention_unverifiable",
    "source_missing_with_graph_present",
    "source_digest_mismatch",
    "source_binding_unverifiable",
    "content_digest_mismatch",
    "content_size_mismatch",
    "orphan_derived_node",
    "edge_cycle",
    "unreachable_node",
    "edge_steps_inconsistent",
    "finding_node_missing",
    "proposal_invalid",
    "proposal_digest_mismatch",
    "proposal_digest_unverifiable",
    "evidence_malformed",
    "evidence_unresolved",
    "decision_digest_mismatch",
    "decision_ordinal_gap",
    "decision_review_link_missing",
    "decision_review_link_mismatch",
    "decisions_missing",
    "verdict_cache_mismatch",
    "review_digest_mismatch",
    "review_timeline_order",
    "review_consumption_inconsistent",
    "execution_digest_mismatch",
    "execution_link_missing",
    "execution_link_invalid",
    "execution_ticket_missing",
]


class LineageBounds(Strict):
    """Fixed caps for one read. Derived from the frozen M003 budgets and M002 fan-out."""

    max_nodes: int = 300
    max_edges: int = 300
    max_steps: int = 1200
    max_findings: int = 2730
    max_actions: int = 8
    max_decisions: int = 16
    max_reviews: int = 8
    max_executions: int = 8
    max_tickets: int = 8
    max_evidence_ids: int = 16
    max_traversal_depth: int = 3


DEFAULT_BOUNDS: Final = LineageBounds()

# Heuristic families in `inspection.RULES`. A test pins the count to that table so a
# new family cannot silently exceed the findings cap.
HEURISTIC_FAMILY_COUNT: Final = 9
# `Analysis.findings` max_length. A test pins this to the live field.
MODEL_FINDING_CAP: Final = 30
# `runs.proposals` CHECK and `GoalLock.max_proposals`.
RUN_PROPOSAL_CAP: Final = 3
# `runs.attempts` CHECK. Current writers persist at most one decision per authorize call.
RUN_ATTEMPT_CAP: Final = 4


class WritePathMaxima(Strict):
    """Largest cardinality a still-supported writer can persist for one run.

    M002 legacy inspection does not enforce `derived_representations_per_run`. It fans out
    at most `base64_matches_per_representation` children per node for `derivation_depth`
    generations. That path is the node/edge/step/finding maximum. M003 enforces the 32
    derived-representation cap and is strictly smaller. M004 writers add no content nodes.
    """

    nodes: int
    edges: int
    steps: int
    findings: int
    actions: int
    decisions: int
    reviews: int
    executions: int
    tickets: int
    evidence_ids: int
    traversal_depth: int


def write_path_maxima() -> WritePathMaxima:
    """Compute the legal maxima from the frozen budgets and schema CHECKs.

    Findings may still truncate as a diagnostic set: the cap is above this number, but a
    focused node or action is never 404 because a cap hid it, because every focused
    identity belongs to a set whose cap is >= that set's legal maximum.
    """

    originals = BUDGETS.originals_per_run
    branching = BUDGETS.base64_matches_per_representation
    # Generation 1 from the original, then generation 2 from each of those (depth 2).
    m002_derived = branching * (1 + branching)
    m003_derived = BUDGETS.derived_representations_per_run
    derived = max(m002_derived, m003_derived)
    nodes = originals + derived
    return WritePathMaxima(
        nodes=nodes,
        edges=derived,
        steps=derived * BUDGETS.transform_steps_per_edge,
        findings=HEURISTIC_FAMILY_COUNT * nodes + MODEL_FINDING_CAP,
        actions=RUN_PROPOSAL_CAP,
        decisions=RUN_PROPOSAL_CAP * RUN_ATTEMPT_CAP,
        reviews=RUN_PROPOSAL_CAP,
        executions=RUN_PROPOSAL_CAP,
        tickets=1,
        evidence_ids=BUDGETS.proposal_evidence_ids,
        traversal_depth=BUDGETS.derivation_depth,
    )


LEGAL_MAXIMA: Final = write_path_maxima()


class ObservedCounts(Strict):
    nodes: int
    edges: int
    steps: int
    findings: int
    actions: int
    decisions: int
    reviews: int
    executions: int
    tickets: int
    max_depth: int


class BoundsReport(Strict):
    """What was capped, what was observed, and whether anything was left out."""

    caps: LineageBounds
    observed: ObservedCounts
    truncated: bool
    truncated_sets: tuple[str, ...]


class IntegrityFinding(Strict):
    code: IntegrityCode
    status: Literal["inconsistent", "unverifiable"]
    subject: str


class Relationship(Strict):
    kind: RelationKind
    source: str
    target: str | None
    basis: Basis


class RunSummary(Strict):
    run_id: str
    workspace_id: str
    state: str
    created_at: datetime
    expires_at: datetime
    complete: bool
    uncertain: bool
    cancelled: bool
    failure: str | None


class GoalLockEntity(Strict):
    id: str
    run_id: str
    valid: bool
    tool: str | None
    tool_version: int | None
    destination: str | None
    policy_revision: str | None
    source_id: str | None
    source_digest: str | None
    expires_at: datetime | None


class ParserIdentity(Strict):
    id: str
    version: str


class SourceBinding(Strict):
    """Envelope source id and digest against the stored original."""

    status: Literal["consistent", "inconsistent", "unverifiable"]
    source_id: str | None


class ContentEntity(Strict):
    id: str
    origin: str
    supplier: str
    digest: str
    complete: bool
    is_source: bool
    representation_kind: str | None
    declared_media_type: str | None
    charset: str | None
    byte_size: int | None
    # The parser that produced a derived representation. It is distinct from the ordered
    # transform steps recorded on the edge that links it to its parent.
    parser: ParserIdentity | None
    parser_state: Literal["recorded", "not_recorded", "not_applicable"]
    body_state: BodyState
    digest_check: Literal["consistent", "inconsistent"]
    created_at: datetime
    expires_at: datetime
    parent_ids: tuple[str, ...]
    child_ids: tuple[str, ...]


class TransformStepEntity(Strict):
    index: int
    transform: str
    version: str


class ContentEdgeEntity(Strict):
    id: str
    parent_id: str
    child_id: str
    transform: str
    version: str
    lossy: bool
    # None means the chain was not recorded. It is never reconstructed from the summary.
    steps: tuple[TransformStepEntity, ...] | None
    steps_state: Literal["recorded", "not_recorded"]


class FindingEntity(Strict):
    """Metadata only. The explanation and any quote are deliberately absent."""

    id: str
    node_id: str
    origin: str
    family: str
    start_offset: int
    end_offset: int
    version: str


class EvidenceRef(Strict):
    """One stored evidence id, in the exact stored position."""

    position: int
    node_id: str
    resolution: Literal["resolved", "unresolved", "unverifiable"]
    body_state: BodyState | None


class ProducerRecord(Strict):
    """Opaque insert-time metadata about the proposal producer. Not authority."""

    state: Literal["recorded", "not_recorded"]
    provider: str | None
    model: str | None
    prompt_version: str | None
    response_id: str | None


class ProposalEntity(Strict):
    id: str
    action_id: str
    digest: str
    digest_check: Literal["consistent", "inconsistent", "unverifiable"]
    tool: str | None
    tool_version: int | None
    evidence: tuple[EvidenceRef, ...]
    producer: ProducerRecord
    verdict_cache: str | None
    created_at: datetime
    # Structural co-location only: findings stored on a node the proposal cites. This is
    # not a record that the model relied on, or even saw, those findings.
    findings_on_cited_evidence: tuple[str, ...]


class GuardDecisionEntity(Strict):
    id: str
    action_id: str
    ordinal: int
    verdict: str
    reasons: tuple[str, ...]
    action_digest: str
    policy_revision_observed: str
    guard_version: str
    review_id: str | None
    evaluated_at: datetime
    digest_check: Literal["consistent", "inconsistent"]


class ReviewEntity(Strict):
    id: str
    action_id: str
    digest: str
    decision: str | None
    consumed: bool
    requested_at: datetime | None
    decided_at: datetime | None
    consumed_at: datetime | None
    expires_at: datetime
    not_recorded: tuple[str, ...]
    digest_check: Literal["consistent", "inconsistent"]
    timeline_check: Literal["consistent", "inconsistent"]


class ExecutionEntity(Strict):
    id: str
    action_id: str
    ticket_id: str
    digest: str
    guard_decision_id: str | None
    committed_at: datetime
    verified_at: datetime | None
    digest_check: Literal["consistent", "inconsistent"]
    authorization: Check


class TicketEntity(Strict):
    """Identity only. The ticket title and body are never part of lineage."""

    id: str
    action_id: str
    created_at: datetime


class PathStep(Strict):
    kind: Literal[
        "goal_lock",
        "source",
        "evidence",
        "proposal",
        "guard_decision",
        "review",
        "execution",
        "ticket",
    ]
    entity: str
    check: Check


class VerifiedPath(Strict):
    """The run's path to an outcome. `complete` only when it is verified end to end."""

    steps: tuple[PathStep, ...]
    complete: bool


class ActionLineage(Strict):
    action_id: str
    stage: Stage
    proposal: ProposalEntity
    decisions: tuple[GuardDecisionEntity, ...]
    review: ReviewEntity | None
    execution: ExecutionEntity | None
    ticket: TicketEntity | None
    path: VerifiedPath


class RetentionSummary(Strict):
    state: RetentionState
    source_present: bool
    nodes_present: int
    nodes_expired_pending_deletion: int


class RunLineage(Strict):
    run: RunSummary
    read_time: datetime
    goal_lock: GoalLockEntity
    source_binding: SourceBinding
    contents: tuple[ContentEntity, ...]
    edges: tuple[ContentEdgeEntity, ...]
    findings: tuple[FindingEntity, ...]
    actions: tuple[ActionLineage, ...]
    relationships: tuple[Relationship, ...]
    integrity: tuple[IntegrityFinding, ...]
    retention: RetentionSummary
    bounds: BoundsReport


class Traversal(Strict):
    """Bounded ancestry or descendant walk from one content node."""

    start: str
    direction: Literal["ancestors", "descendants"]
    nodes: tuple[tuple[str, int], ...]
    truncated: bool


class NodeLineage(Strict):
    node: ContentEntity
    ancestors: Traversal
    descendants: Traversal
    findings: tuple[str, ...]
    citing_proposals: tuple[str, ...]
