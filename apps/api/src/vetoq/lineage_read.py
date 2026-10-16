"""Internal, run-scoped, read-only lineage service.

The typed lineage routes expose it read-only. It resolves the run through the one canonical
visibility rule and then reads everything from one `REPEATABLE READ, READ ONLY` snapshot with
a fixed number of indexed, run-scoped queries and Python assembly. There is no N+1 and no
recursive SQL.

The trusted run row supplies the workspace and run id for every query. A client id selects
the run and nothing else. Audit events are never an input, content bodies are never
returned, and a failed read changes no run, authority, execution, audit, or lineage state.

Lineage is evidence and never authority. The workflow and the Action Guard do not import
this module, and nothing here feeds an authorization decision.
"""

from typing import Any

from sqlalchemy import Connection, Engine, text

from vetoq.db import one, rows
from vetoq.lineage_assemble import Snapshot, assemble
from vetoq.lineage_graph import traverse
from vetoq.lineage_model import (
    DEFAULT_BOUNDS,
    ActionLineage,
    LineageBounds,
    NodeLineage,
    RunLineage,
)
from vetoq.visibility import visible_run
from vetoq.workflow import DomainError

# Every query binds the trusted workspace and run, and asks for one row beyond its cap so
# truncation is detected rather than silently clipped. Bodies are compared inside the
# database and never returned.
_NODES = """
    SELECT id,workspace_id,run_id,origin,supplier,digest,complete,created_at,expires_at,
           declared_media_type,representation_kind,charset,byte_size,parser_id,parser_version,
           octet_length(convert_to(content,'UTF8')) AS body_octets,
           encode(sha256(convert_to(content,'UTF8')),'hex') = digest AS digest_ok
    FROM content_nodes WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY created_at,id LIMIT :limit
"""
_EDGES = """
    SELECT id,workspace_id,run_id,parent_id,child_id,transform,version,lossy,
           transform_step_count
    FROM content_edges WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY parent_id,child_id LIMIT :limit
"""
_STEPS = """
    SELECT s.edge_id,s.step_index,s.transform,s.version
    FROM content_edge_steps s JOIN content_edges e ON e.id=s.edge_id
    WHERE e.workspace_id=:workspace AND e.run_id=:run
    ORDER BY s.edge_id,s.step_index LIMIT :limit
"""
_FINDINGS = """
    SELECT id,workspace_id,run_id,node_id,origin,family,start_offset,end_offset,version
    FROM findings WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY node_id,start_offset,end_offset,id LIMIT :limit
"""
_ACTIONS = """
    SELECT id,workspace_id,run_id,proposal,digest,verdict,created_at,
           producer_provider,producer_model,producer_prompt_version,producer_response_id
    FROM actions WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY created_at,id LIMIT :limit
"""
_DECISIONS = """
    SELECT id,workspace_id,run_id,action_id,ordinal,verdict,reasons,action_digest,
           policy_revision_observed,guard_version,review_id,evaluated_at
    FROM guard_decisions WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY action_id,ordinal LIMIT :limit
"""
_REVIEWS = """
    SELECT id,workspace_id,run_id,action_id,digest,expires_at,decision,consumed,
           requested_at,decided_at,consumed_at
    FROM reviews WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY action_id,id LIMIT :limit
"""
_EXECUTIONS = """
    SELECT id,workspace_id,run_id,action_id,ticket_id,digest,committed_at,verified_at,
           guard_decision_id
    FROM executions WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY committed_at,id LIMIT :limit
"""
_TICKETS = """
    SELECT id,workspace_id,run_id,action_id,created_at
    FROM tickets WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY created_at,id LIMIT :limit
"""


def read_snapshot(connection: Connection, run: dict[str, Any], bounds: LineageBounds) -> Snapshot:
    """Read every run-scoped set under the caller's snapshot. Uses the trusted run only."""

    clock = one(connection, "SELECT now() AS read_time")
    read_time = clock["read_time"] if clock else None
    if read_time is None:
        raise DomainError("not_found", 404)
    scope = {"workspace": run["workspace_id"], "run": run["id"]}
    truncated: set[str] = set()

    def capped(name: str, sql: str, cap: int) -> list[dict[str, Any]]:
        found = rows(connection, sql, {**scope, "limit": cap + 1})
        if len(found) > cap:
            truncated.add(name)
            return found[:cap]
        return found

    nodes = capped("content_nodes", _NODES, bounds.max_nodes)
    edges = capped("content_edges", _EDGES, bounds.max_edges)
    steps = capped("content_edge_steps", _STEPS, bounds.max_steps)
    findings = capped("findings", _FINDINGS, bounds.max_findings)
    actions = capped("actions", _ACTIONS, bounds.max_actions)
    decisions = capped("guard_decisions", _DECISIONS, bounds.max_decisions)
    reviews = capped("reviews", _REVIEWS, bounds.max_reviews)
    executions = capped("executions", _EXECUTIONS, bounds.max_executions)
    tickets = capped("tickets", _TICKETS, bounds.max_tickets)
    return Snapshot(
        run=run,
        read_time=read_time,
        nodes=nodes,
        edges=edges,
        steps=steps,
        findings=findings,
        actions=actions,
        decisions=decisions,
        reviews=reviews,
        executions=executions,
        tickets=tickets,
        truncated=frozenset(truncated),
    )


def build_run_lineage(
    engine: Engine,
    principal: str,
    run_id: str,
    bounds: LineageBounds = DEFAULT_BOUNDS,
) -> RunLineage:
    """Assemble one run's lineage for a principal who may see the run.

    Raises the non-enumerating `not_found` for a missing run, a foreign workspace, an
    inactive membership, or an inactive workspace. The read never writes.
    """

    with engine.connect() as connection:
        # Must be the first statement of the transaction.
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        run = visible_run(connection, run_id, principal)
        snapshot = read_snapshot(connection, run, bounds)
    return assemble(snapshot, bounds)


def focus_action(lineage: RunLineage, action_id: str) -> ActionLineage:
    """Select one action from an already assembled, already authorized run lineage."""

    for action in lineage.actions:
        if action.action_id == action_id:
            return action
    raise DomainError("not_found", 404)


def focus_node(lineage: RunLineage, node_id: str, bounds: LineageBounds) -> NodeLineage:
    """One content node with bounded ancestry and descendants, from an assembled lineage.

    The node is looked up only among the contents of the trusted run. Traversal depth and node
    cap come from the server's bounds, never from a caller.
    """

    identity = f"content:{node_id}"
    node = next((c for c in lineage.contents if c.id == identity), None)
    if node is None:
        raise DomainError("not_found", 404)
    edges = [(e.parent_id, e.child_id) for e in lineage.edges]
    ids = [c.id for c in lineage.contents]
    cap = (bounds.max_traversal_depth, bounds.max_nodes)
    ancestors = traverse(edges, ids, identity, "ancestors", *cap)
    descendants = traverse(edges, ids, identity, "descendants", *cap)
    return NodeLineage(
        node=node,
        ancestors=ancestors,
        descendants=descendants,
        findings=tuple(f.id for f in lineage.findings if f.node_id == identity),
        citing_proposals=tuple(
            a.proposal.id
            for a in lineage.actions
            if any(r.node_id == node_id and r.resolution == "resolved" for r in a.proposal.evidence)
        ),
    )


def build_action_lineage(
    engine: Engine, principal: str, run_id: str, action_id: str
) -> ActionLineage:
    """One action's lineage, resolved only within the trusted run."""

    return focus_action(build_run_lineage(engine, principal, run_id), action_id)


def build_node_lineage(
    engine: Engine,
    principal: str,
    run_id: str,
    node_id: str,
    bounds: LineageBounds = DEFAULT_BOUNDS,
) -> NodeLineage:
    """One content node with bounded ancestry and descendants, within the trusted run."""

    return focus_node(build_run_lineage(engine, principal, run_id, bounds), node_id, bounds)
