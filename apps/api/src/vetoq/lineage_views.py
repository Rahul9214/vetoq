"""Public, focused views over one already assembled and already authorized run lineage.

These are projections. They add no lineage meaning: retention, legacy state, integrity, the
verified path, relationships and action stage are all decided once, by the Slice D assembler,
and are only selected and ordered here. Nothing in this module reads the database or the audit
log, and nothing here is an input to authorization.

A node view or an action view carries the run, source, retention and bounds context needed to
interpret it, so a truncated or inconsistent run is never presented as a complete one. Free
text (content bodies, ticket text, finding explanations, model text) is not part of the model
these views are built from, so it cannot appear in them.
"""

from datetime import datetime
from typing import Literal

from vetoq.contracts import Strict
from vetoq.lineage_model import (
    ActionLineage,
    BoundsReport,
    ContentEdgeEntity,
    ContentEntity,
    FindingEntity,
    GoalLockEntity,
    IntegrityFinding,
    LineageBounds,
    Relationship,
    RetentionSummary,
    RunLineage,
    RunSummary,
    SourceBinding,
    Traversal,
)
from vetoq.lineage_read import focus_action, focus_node

Direction = Literal["ancestors", "descendants", "both"]


class NodeLineageView(Strict):
    """One content node, its bounded ancestry and descendants, and the context to read them.

    `ancestors` is null when the caller asked only for descendants, and `descendants` is null
    when the caller asked only for ancestors. A walk that was clipped by the server's depth or
    node bound carries `truncated: true`. `related` holds the content entities the requested
    walks reached, `edges` the recorded derivations among the node and those entities, and
    `integrity` the findings that name an entity in this view plus every run-level finding.
    """

    run: RunSummary
    read_time: datetime
    direction: Direction
    node: ContentEntity
    ancestors: Traversal | None
    descendants: Traversal | None
    related: tuple[ContentEntity, ...]
    edges: tuple[ContentEdgeEntity, ...]
    findings: tuple[FindingEntity, ...]
    citing_proposals: tuple[str, ...]
    relationships: tuple[Relationship, ...]
    source_binding: SourceBinding
    retention: RetentionSummary
    integrity: tuple[IntegrityFinding, ...]
    bounds: BoundsReport


class ActionLineageView(Strict):
    """One action's causal path with the context needed to interpret it.

    `action` carries the proposal and its cited evidence references and recorded producer
    metadata, the ordered guard decisions, the review, the execution, the ticket reference, the
    stage and the verified path. `evidence` and `findings` are the structural metadata of the
    cited content and of the findings stored on it. Other actions of the run are not included.
    """

    run: RunSummary
    read_time: datetime
    goal_lock: GoalLockEntity
    source_binding: SourceBinding
    action: ActionLineage
    evidence: tuple[ContentEntity, ...]
    findings: tuple[FindingEntity, ...]
    relationships: tuple[Relationship, ...]
    retention: RetentionSummary
    integrity: tuple[IntegrityFinding, ...]
    bounds: BoundsReport


def _relationship_key(item: Relationship) -> tuple[str, str, str, str]:
    return (item.kind, item.source, item.target or "", item.basis)


def canonical(lineage: RunLineage) -> RunLineage:
    """Give the one collection that follows emission order a stable, explicit order.

    Every other collection is already ordered by an explicit key (content by creation time and
    id, edges by parent and child, steps by index, decisions by ordinal, and so on).
    """

    return lineage.model_copy(
        update={
            "relationships": tuple(sorted(lineage.relationships, key=_relationship_key)),
            "integrity": tuple(
                sorted(lineage.integrity, key=lambda i: (i.code, i.subject, i.status))
            ),
        }
    )


def _known_entities(lineage: RunLineage) -> set[str]:
    known = {c.id for c in lineage.contents}
    known |= {e.id for e in lineage.edges}
    known |= {f.id for f in lineage.findings}
    for action in lineage.actions:
        known.add(action.proposal.id)
        known |= {d.id for d in action.decisions}
        known |= {e.id for e in (action.review, action.execution, action.ticket) if e is not None}
    return known


def _integrity_in_scope(lineage: RunLineage, scope: set[str]) -> tuple[IntegrityFinding, ...]:
    """Findings that name an entity in the view, plus every run-level finding.

    A subject that is not a present entity (the Goal Lock, a capped set, an absent source)
    describes the run and is always kept, so a focused view never hides a run-level anomaly.
    """

    known = _known_entities(lineage)
    return tuple(i for i in lineage.integrity if i.subject in scope or i.subject not in known)


def _relationships_in_scope(
    lineage: RunLineage, scope: set[str], excluded: frozenset[str] = frozenset()
) -> tuple[Relationship, ...]:
    return tuple(
        r
        for r in lineage.relationships
        if (r.source in scope or r.target in scope)
        and r.source not in excluded
        and r.target not in excluded
    )


def _action_entities(action: ActionLineage) -> set[str]:
    entities = {action.proposal.id} | {d.id for d in action.decisions}
    entities |= {e.id for e in (action.review, action.execution, action.ticket) if e is not None}
    return entities


def _ordered_walk(walk: Traversal) -> Traversal:
    return walk.model_copy(update={"nodes": tuple(sorted(walk.nodes, key=lambda n: (n[1], n[0])))})


def node_view(
    lineage: RunLineage, node_id: str, direction: Direction, bounds: LineageBounds
) -> NodeLineageView:
    """Focus an authorized run lineage on one node. Raises `not_found` if it is not in the run."""

    whole = canonical(lineage)
    focus = focus_node(whole, node_id, bounds)
    ancestors = _ordered_walk(focus.ancestors) if direction in ("ancestors", "both") else None
    descendants = _ordered_walk(focus.descendants) if direction in ("descendants", "both") else None
    members = {focus.node.id}
    for walk in (ancestors, descendants):
        if walk is not None:
            members |= {name for name, _ in walk.nodes}
    edges = tuple(e for e in whole.edges if e.parent_id in members and e.child_id in members)
    findings = tuple(f for f in whole.findings if f.node_id == focus.node.id)
    scope = members | {e.id for e in edges} | {f.id for f in findings} | set(focus.citing_proposals)
    return NodeLineageView(
        run=whole.run,
        read_time=whole.read_time,
        direction=direction,
        node=focus.node,
        ancestors=ancestors,
        descendants=descendants,
        related=tuple(c for c in whole.contents if c.id in members and c.id != focus.node.id),
        edges=edges,
        findings=findings,
        citing_proposals=focus.citing_proposals,
        relationships=_relationships_in_scope(whole, scope),
        source_binding=whole.source_binding,
        retention=whole.retention,
        integrity=_integrity_in_scope(whole, scope),
        bounds=whole.bounds,
    )


def action_view(lineage: RunLineage, action_id: str) -> ActionLineageView:
    """Focus an authorized run lineage on one action. Raises `not_found` if it is not in the run."""

    whole = canonical(lineage)
    action = focus_action(whole, action_id)
    by_id = {c.id: c for c in whole.contents}
    cited: list[ContentEntity] = []
    for reference in action.proposal.evidence:
        content = by_id.get(f"content:{reference.node_id}")
        if reference.resolution == "resolved" and content is not None and content not in cited:
            cited.append(content)
    colocated = set(action.proposal.findings_on_cited_evidence)
    findings = tuple(f for f in whole.findings if f.id in colocated)
    scope = _action_entities(action) | {c.id for c in cited} | {f.id for f in findings}
    # Another action may cite the same evidence. Its own entities are not part of this view.
    others = frozenset().union(*(_action_entities(a) for a in whole.actions if a is not action))
    return ActionLineageView(
        run=whole.run,
        read_time=whole.read_time,
        goal_lock=whole.goal_lock,
        source_binding=whole.source_binding,
        action=action,
        evidence=tuple(cited),
        findings=findings,
        relationships=_relationships_in_scope(whole, scope, others),
        retention=whole.retention,
        integrity=_integrity_in_scope(whole, scope),
        bounds=whole.bounds,
    )
