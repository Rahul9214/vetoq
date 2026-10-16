"""M004 Slice D: pure lineage assembly and bounded graph analysis.

No database is used. A hand-built snapshot reaches states the schema forbids (a digest
mismatch, a cycle, a foreign-scope row), so each integrity check is proven directly. The
fixtures are labeled synthetic test data and are never operational metrics.
"""

import copy
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from vetoq.contracts import GoalLock, Proposal, TicketArguments, action_digest
from vetoq.inspection import content_digest
from vetoq.lineage_assemble import RETENTION_WINDOW, Snapshot, assemble
from vetoq.lineage_graph import analyze_graph, traverse
from vetoq.lineage_model import DEFAULT_BOUNDS, LineageBounds, RunLineage

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
BODY = "Synthetic test source."

Parts = dict[str, Any]


def baseline() -> Parts:
    """A coherent, verified ALLOW run with every current-writer fact recorded."""

    run_id, workspace, source = str(uuid4()), str(uuid4()), str(uuid4())
    envelope = GoalLock(
        principal="user_synthetic",
        workspace_id=UUID(workspace),
        source_id=UUID(source),
        source_digest=content_digest(BODY),
        goal="Synthetic goal.",
        expires_at=NOW + timedelta(hours=1),
    )
    proposal = Proposal(
        tool="tickets.create",
        tool_version=1,
        arguments=TicketArguments(workspace_id=UUID(workspace), title="Title", body="Body"),
        evidence_ids=[UUID(source)],
    )
    action_id, decision_id, execution_id, ticket_id = (str(uuid4()) for _ in range(4))
    digest = action_digest(run_id, envelope, proposal)
    scope = {"workspace_id": workspace, "run_id": run_id}
    return {
        "run": {
            **{"id": run_id, "workspace_id": workspace},
            "state": "COMPLETED",
            "created_at": NOW - timedelta(hours=1),
            "expires_at": NOW + timedelta(hours=1),
            "complete": True,
            "uncertain": False,
            "cancelled": False,
            "failure": None,
            "envelope": envelope.model_dump(mode="json"),
        },
        "nodes": [
            {
                **scope,
                "id": source,
                "origin": "pasted-email",
                "supplier": "synthetic",
                "digest": content_digest(BODY),
                "complete": True,
                "created_at": NOW - timedelta(hours=1),
                "expires_at": NOW + timedelta(hours=23),
                "declared_media_type": "text/plain",
                "representation_kind": "original",
                "charset": "utf-8",
                "byte_size": len(BODY.encode()),
                "parser_id": None,
                "parser_version": None,
                "body_octets": len(BODY.encode()),
                "digest_ok": True,
            }
        ],
        "edges": [],
        "steps": [],
        "findings": [],
        "actions": [
            {
                **scope,
                "id": action_id,
                "proposal": proposal.model_dump(mode="json"),
                "digest": digest,
                "verdict": "ALLOW",
                "created_at": NOW - timedelta(minutes=50),
                "producer_provider": "fixture",
                "producer_model": "fixture/structured",
                "producer_prompt_version": "fixture/1",
                "producer_response_id": None,
            }
        ],
        "decisions": [
            {
                **scope,
                "id": decision_id,
                "action_id": action_id,
                "ordinal": 1,
                "verdict": "ALLOW",
                "reasons": ["WITHIN_CONFIRMED_AUTHORITY"],
                "action_digest": digest,
                "policy_revision_observed": "support-triage/1",
                "guard_version": "action-guard/1",
                "review_id": None,
                "evaluated_at": NOW - timedelta(minutes=49),
            }
        ],
        "reviews": [],
        "executions": [
            {
                **scope,
                "id": execution_id,
                "action_id": action_id,
                "ticket_id": ticket_id,
                "digest": digest,
                "committed_at": NOW - timedelta(minutes=48),
                "verified_at": NOW - timedelta(minutes=47),
                "guard_decision_id": decision_id,
            }
        ],
        "tickets": [
            {
                **scope,
                "id": ticket_id,
                "action_id": action_id,
                "created_at": NOW - timedelta(minutes=48),
            }
        ],
        "truncated": frozenset(),
    }


def read(parts: Parts, bounds: LineageBounds = DEFAULT_BOUNDS, at: datetime = NOW) -> RunLineage:
    snapshot = Snapshot(
        run=parts["run"],
        read_time=at,
        nodes=parts["nodes"],
        edges=parts["edges"],
        steps=parts["steps"],
        findings=parts["findings"],
        actions=parts["actions"],
        decisions=parts["decisions"],
        reviews=parts["reviews"],
        executions=parts["executions"],
        tickets=parts["tickets"],
        truncated=parts["truncated"],
    )
    return assemble(snapshot, bounds)


def codes(lineage: RunLineage) -> set[str]:
    return {finding.code for finding in lineage.integrity}


def scope_of(parts: Parts) -> dict[str, str]:
    return {"workspace_id": parts["run"]["workspace_id"], "run_id": parts["run"]["id"]}


def add_review(parts: Parts, *, decision: str | None = None) -> dict[str, Any]:
    action = parts["actions"][0]
    review = {
        **scope_of(parts),
        "id": str(uuid4()),
        "action_id": action["id"],
        "digest": action["digest"],
        "expires_at": NOW + timedelta(minutes=10),
        "decision": decision,
        "consumed": False,
        "requested_at": NOW - timedelta(minutes=30),
        "decided_at": None if decision is None else NOW - timedelta(minutes=20),
        "consumed_at": None,
    }
    parts["reviews"].append(review)
    return review


def test_coherent_run_is_verified_with_no_integrity_findings() -> None:
    lineage = read(baseline())
    assert lineage.integrity == ()
    action = lineage.actions[0]
    assert action.stage == "verified"
    assert action.path.complete is True
    assert [step.kind for step in action.path.steps] == [
        "goal_lock",
        "source",
        "evidence",
        "proposal",
        "guard_decision",
        "execution",
        "ticket",
    ]
    assert lineage.source_binding.status == "consistent"
    assert lineage.retention.state == "available"
    assert lineage.bounds.truncated is False


def test_entity_identities_are_stable_and_prefixed() -> None:
    parts = baseline()
    lineage = read(parts)
    action = parts["actions"][0]
    assert lineage.goal_lock.id == f"goal_lock:{parts['run']['id']}"
    assert lineage.contents[0].id == f"content:{parts['nodes'][0]['id']}"
    assert lineage.actions[0].proposal.id == f"proposal:{action['id']}"
    assert lineage.actions[0].decisions[0].id == f"guard_decision:{parts['decisions'][0]['id']}"
    assert lineage.actions[0].execution is not None
    assert lineage.actions[0].execution.id == f"execution:{parts['executions'][0]['id']}"
    assert lineage.actions[0].ticket is not None
    assert lineage.actions[0].ticket.id == f"ticket:{parts['tickets'][0]['id']}"


def test_model_carries_no_body_ticket_text_or_explanation() -> None:
    parts = baseline()
    parts["findings"].append(
        {
            **scope_of(parts),
            "id": str(uuid4()),
            "node_id": parts["nodes"][0]["id"],
            "origin": "model",
            "family": "Tool Abuse",
            "explanation": "SYNTHETIC-EXPLANATION-SENTINEL",
            "start_offset": 0,
            "end_offset": 3,
            "version": "synthetic/1",
        }
    )
    parts["nodes"][0]["content"] = "SYNTHETIC-BODY-SENTINEL"
    dumped = read(parts).model_dump_json()
    for sentinel in ("SYNTHETIC-EXPLANATION-SENTINEL", "SYNTHETIC-BODY-SENTINEL", "Body", "Title"):
        assert sentinel not in dumped


def test_findings_on_cited_evidence_is_structural_colocation() -> None:
    parts = baseline()
    finding_id = str(uuid4())
    parts["findings"].append(
        {
            **scope_of(parts),
            "id": finding_id,
            "node_id": parts["nodes"][0]["id"],
            "origin": "deterministic",
            "family": "Tool Abuse",
            "start_offset": 0,
            "end_offset": 3,
            "version": "rules/1",
        }
    )
    proposal = read(parts).actions[0].proposal
    assert proposal.findings_on_cited_evidence == (f"finding:{finding_id}",)
    kinds = {(r.kind, r.basis) for r in read(parts).relationships}
    assert ("finding_on_cited_evidence", "derived_join") in kinds
    assert ("proposal_cites_content", "digest_bound_json") in kinds


# ---- not recorded is never an anomaly ----------------------------------------------


def legacy_parts() -> Parts:
    """A pre-0005 run: no producer, no decisions, no execution link, bare review times."""

    parts = baseline()
    action = parts["actions"][0]
    for name in ("provider", "model", "prompt_version", "response_id"):
        action[f"producer_{name}"] = None
    parts["decisions"].clear()
    parts["executions"][0]["guard_decision_id"] = None
    review = add_review(parts, decision="approve")
    review.update(requested_at=None, decided_at=None, consumed=True, consumed_at=None)
    return parts


def test_legacy_facts_are_not_recorded_and_raise_no_integrity_finding() -> None:
    lineage = read(legacy_parts())
    action = lineage.actions[0]
    assert lineage.integrity == ()
    assert action.proposal.producer.state == "not_recorded"
    assert action.decisions == ()
    assert action.execution is not None
    assert action.execution.authorization == "not_recorded"
    assert action.review is not None
    assert action.review.not_recorded == ("requested_at", "decided_at", "consumed_at")
    assert action.stage == "verified"
    # A legacy run is verified, but it cannot claim an end-to-end verified path.
    assert action.path.complete is False


def test_one_null_does_not_decide_legacy_status() -> None:
    parts = baseline()
    parts["actions"][0]["producer_provider"] = None
    parts["actions"][0]["producer_model"] = None
    parts["actions"][0]["producer_prompt_version"] = None
    lineage = read(parts)
    assert lineage.actions[0].proposal.producer.state == "not_recorded"
    assert lineage.integrity == ()
    assert lineage.actions[0].path.complete is True


def test_latest_only_when_only_the_verdict_cache_exists() -> None:
    parts = legacy_parts()
    parts["executions"].clear()
    parts["tickets"].clear()
    parts["reviews"].clear()
    parts["run"]["state"] = "AUTHORIZING"
    action = read(parts).actions[0]
    assert action.stage == "latest_only"
    assert read(parts).integrity == ()


def test_recorded_producer_with_verdict_but_no_decision_is_an_anomaly() -> None:
    parts = baseline()
    parts["decisions"].clear()
    parts["executions"].clear()
    parts["tickets"].clear()
    assert "decisions_missing" in codes(read(parts))


def test_execution_without_link_but_with_allow_decision_is_an_anomaly() -> None:
    parts = baseline()
    parts["executions"][0]["guard_decision_id"] = None
    lineage = read(parts)
    assert "execution_link_missing" in codes(lineage)
    assert lineage.actions[0].execution is not None
    assert lineage.actions[0].execution.authorization == "inconsistent"


def test_producer_is_opaque_metadata_with_optional_response_id() -> None:
    parts = baseline()
    parts["actions"][0]["producer_response_id"] = "resp-synthetic"
    producer = read(parts).actions[0].proposal.producer
    assert (producer.state, producer.provider, producer.response_id) == (
        "recorded",
        "fixture",
        "resp-synthetic",
    )


# ---- integrity findings -------------------------------------------------------------


def mutate_digest(parts: Parts) -> None:
    parts["actions"][0]["digest"] = "0" * 64


def mutate_decision_digest(parts: Parts) -> None:
    parts["decisions"][0]["action_digest"] = "1" * 64


def mutate_ordinal(parts: Parts) -> None:
    parts["decisions"][0]["ordinal"] = 2


def mutate_cache(parts: Parts) -> None:
    parts["actions"][0]["verdict"] = "BLOCK"


def mutate_execution_digest(parts: Parts) -> None:
    parts["executions"][0]["digest"] = "2" * 64


def mutate_link_unknown(parts: Parts) -> None:
    parts["executions"][0]["guard_decision_id"] = str(uuid4())


def mutate_link_not_allow(parts: Parts) -> None:
    parts["decisions"][0]["verdict"] = "REVIEW"
    parts["actions"][0]["verdict"] = "REVIEW"


def mutate_content_digest(parts: Parts) -> None:
    parts["nodes"][0]["digest_ok"] = False


def mutate_size(parts: Parts) -> None:
    parts["nodes"][0]["byte_size"] = 9999


def mutate_source_digest(parts: Parts) -> None:
    parts["nodes"][0]["digest"] = "3" * 64


def mutate_missing_ticket(parts: Parts) -> None:
    parts["tickets"].clear()


def mutate_envelope(parts: Parts) -> None:
    parts["run"]["envelope"] = {}


def mutate_foreign_scope(parts: Parts) -> None:
    parts["decisions"][0]["workspace_id"] = str(uuid4())


def mutate_unresolved_evidence(parts: Parts) -> None:
    parts["actions"][0]["proposal"]["evidence_ids"] = [str(uuid4())]


def mutate_malformed_evidence(parts: Parts) -> None:
    parts["actions"][0]["proposal"]["evidence_ids"] = "not-a-list"


def mutate_finding_node(parts: Parts) -> None:
    parts["findings"].append(
        {
            **scope_of(parts),
            "id": str(uuid4()),
            "node_id": str(uuid4()),
            "origin": "deterministic",
            "family": "Tool Abuse",
            "start_offset": 0,
            "end_offset": 1,
            "version": "rules/1",
        }
    )


def mutate_steps(parts: Parts) -> None:
    child = str(uuid4())
    parts["nodes"].append({**copy.deepcopy(parts["nodes"][0]), "id": child, "origin": "derived"})
    parts["edges"].append(
        {
            **scope_of(parts),
            "id": str(uuid4()),
            "parent_id": parts["nodes"][0]["id"],
            "child_id": child,
            "transform": "t",
            "version": "1",
            "lossy": False,
            "transform_step_count": 2,
        }
    )
    parts["steps"].append(
        {"edge_id": parts["edges"][0]["id"], "step_index": 1, "transform": "t", "version": "1"}
    )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (mutate_digest, "proposal_digest_mismatch"),
        (mutate_decision_digest, "decision_digest_mismatch"),
        (mutate_ordinal, "decision_ordinal_gap"),
        (mutate_cache, "verdict_cache_mismatch"),
        (mutate_execution_digest, "execution_digest_mismatch"),
        (mutate_link_unknown, "execution_link_invalid"),
        (mutate_link_not_allow, "execution_link_invalid"),
        (mutate_content_digest, "content_digest_mismatch"),
        (mutate_size, "content_size_mismatch"),
        (mutate_source_digest, "source_digest_mismatch"),
        (mutate_missing_ticket, "execution_ticket_missing"),
        (mutate_envelope, "envelope_invalid"),
        (mutate_foreign_scope, "scope_mismatch"),
        (mutate_unresolved_evidence, "evidence_unresolved"),
        (mutate_malformed_evidence, "evidence_malformed"),
        (mutate_finding_node, "finding_node_missing"),
        (mutate_steps, "edge_steps_inconsistent"),
    ],
)
def test_integrity_finding_is_reported(mutate: Callable[[Parts], None], expected: str) -> None:
    parts = baseline()
    mutate(parts)
    lineage = read(parts)
    assert expected in codes(lineage)
    # An anomaly on anything the path involves means the path is not verified end to end.
    unrelated = {"finding_node_missing", "edge_steps_inconsistent"}
    assert lineage.actions[0].path.complete is (expected in unrelated)


def test_invalid_envelope_makes_the_digest_unverifiable_not_inconsistent() -> None:
    parts = baseline()
    parts["run"]["envelope"] = {}
    lineage = read(parts)
    assert lineage.actions[0].proposal.digest_check == "unverifiable"
    assert lineage.source_binding.status == "unverifiable"
    assert {f.status for f in lineage.integrity} == {"unverifiable"}


def test_action_digest_is_recomputed_with_the_production_function() -> None:
    parts = baseline()
    assert read(parts).actions[0].proposal.digest_check == "consistent"
    parts["actions"][0]["proposal"]["arguments"]["title"] = "Changed"
    assert read(parts).actions[0].proposal.digest_check == "inconsistent"


def test_evidence_sequence_is_exact_including_duplicates_and_order() -> None:
    parts = baseline()
    source = parts["nodes"][0]["id"]
    other = str(uuid4())
    parts["nodes"].append({**copy.deepcopy(parts["nodes"][0]), "id": other, "origin": "derived"})
    parts["edges"].append(
        {
            **scope_of(parts),
            "id": str(uuid4()),
            "parent_id": source,
            "child_id": other,
            "transform": "t",
            "version": "1",
            "lossy": False,
            "transform_step_count": None,
        }
    )
    parts["actions"][0]["proposal"]["evidence_ids"] = [other, source, other]
    evidence = read(parts).actions[0].proposal.evidence
    assert [(e.position, e.node_id) for e in evidence] == [(0, other), (1, source), (2, other)]
    assert {e.resolution for e in evidence} == {"resolved"}


def test_decision_review_link_checks() -> None:
    parts = baseline()
    review = add_review(parts, decision=None)
    assert "decision_review_link_missing" in codes(read(parts))
    parts["decisions"][0]["review_id"] = str(uuid4())
    assert "decision_review_link_mismatch" in codes(read(parts))
    parts["decisions"][0]["review_id"] = review["id"]
    assert "decision_review_link_mismatch" not in codes(read(parts))


def test_review_timeline_and_consumption_checks() -> None:
    parts = baseline()
    review = add_review(parts, decision="approve")
    parts["decisions"][0]["review_id"] = review["id"]
    review.update(decided_at=review["requested_at"] - timedelta(minutes=1))
    assert "review_timeline_order" in codes(read(parts))
    review.update(decided_at=review["requested_at"], consumed=True, decision="reject")
    review["consumed_at"] = review["decided_at"]
    assert "review_consumption_inconsistent" in codes(read(parts))
    review.update(digest="4" * 64)
    assert "review_digest_mismatch" in codes(read(parts))


# ---- graph anomalies ----------------------------------------------------------------


def derived(parts: Parts, parent: str | None) -> str:
    identity = str(uuid4())
    parts["nodes"].append({**copy.deepcopy(parts["nodes"][0]), "id": identity, "origin": "derived"})
    if parent is not None:
        parts["edges"].append(
            {
                **scope_of(parts),
                "id": str(uuid4()),
                "parent_id": parent,
                "child_id": identity,
                "transform": "t",
                "version": "1",
                "lossy": False,
                "transform_step_count": None,
            }
        )
    return identity


def test_derived_node_and_edge_without_recorded_provenance_are_not_recorded() -> None:
    parts = baseline()
    child = derived(parts, parts["nodes"][0]["id"])
    lineage = read(parts)
    entity = next(c for c in lineage.contents if c.id == f"content:{child}")
    assert (entity.parser_state, entity.parser) == ("not_recorded", None)
    assert [(e.steps_state, e.steps) for e in lineage.edges] == [("not_recorded", None)]
    assert lineage.integrity == ()


def test_orphan_derived_node_is_reported() -> None:
    parts = baseline()
    orphan = derived(parts, None)
    found = {(f.code, f.subject) for f in read(parts).integrity}
    assert ("orphan_derived_node", f"content:{orphan}") in found


def test_cycle_and_unreachable_nodes_are_reported() -> None:
    parts = baseline()
    first = derived(parts, None)
    second = derived(parts, first)
    parts["edges"].append(
        {**parts["edges"][0], "id": str(uuid4()), "parent_id": second, "child_id": first}
    )
    found = {(f.code, f.subject) for f in read(parts).integrity}
    assert ("edge_cycle", f"content:{first}") in found
    assert ("edge_cycle", f"content:{second}") in found


def test_unreachable_node_without_a_cycle_is_reported() -> None:
    parts = baseline()
    parent = derived(parts, parts["nodes"][0]["id"])
    detached_root = derived(parts, None)
    # Give the detached node a parent that is itself detached and not derived.
    parts["nodes"][-1]["origin"] = "pasted-email"
    child = derived(parts, detached_root)
    found = {(f.code, f.subject) for f in read(parts).integrity}
    assert ("unreachable_node", f"content:{detached_root}") in found
    assert ("unreachable_node", f"content:{child}") in found
    assert ("unreachable_node", f"content:{parent}") not in found


def test_depth_beyond_the_bound_is_reported_and_not_silently_clipped() -> None:
    parts = baseline()
    node = parts["nodes"][0]["id"]
    for _ in range(DEFAULT_BOUNDS.max_traversal_depth + 1):
        node = derived(parts, node)
    lineage = read(parts)
    assert ("bound_exceeded", "traversal_depth") in {(f.code, f.subject) for f in lineage.integrity}
    assert lineage.bounds.observed.max_depth == DEFAULT_BOUNDS.max_traversal_depth + 1


def test_analyze_graph_flags_a_self_loop() -> None:
    result = analyze_graph({"a": False, "b": True}, [("a", "b"), ("b", "b")], "a")
    assert ("edge_cycle", "b") in result.anomalies


def test_traverse_is_bounded_visited_and_reports_truncation() -> None:
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("a", "c"), ("d", "b")]
    nodes = ["a", "b", "c", "d"]
    full = traverse(edges, nodes, "a", "descendants", 9, 9)
    assert dict(full.nodes) == {"b": 1, "c": 1, "d": 2}
    assert full.truncated is False
    shallow = traverse(edges, nodes, "a", "descendants", 1, 9)
    assert dict(shallow.nodes) == {"b": 1, "c": 1}
    assert shallow.truncated is True
    capped = traverse(edges, nodes, "a", "descendants", 9, 1)
    assert len(capped.nodes) == 1 and capped.truncated is True
    up = traverse(edges, nodes, "d", "ancestors", 9, 9)
    assert set(dict(up.nodes)) == {"a", "b", "c"}


# ---- retention ----------------------------------------------------------------------


def test_expired_body_pending_deletion_keeps_every_authority_fact() -> None:
    parts = baseline()
    parts["nodes"][0]["expires_at"] = NOW - timedelta(seconds=1)
    lineage = read(parts)
    assert lineage.retention.state == "expired_body_pending_deletion"
    assert lineage.contents[0].body_state == "expired_body_pending_deletion"
    assert lineage.actions[0].proposal.evidence[0].body_state == "expired_body_pending_deletion"
    assert lineage.integrity == ()


def removed(parts: Parts, age: timedelta) -> RunLineage:
    parts["nodes"].clear()
    parts["findings"].clear()
    parts["run"]["created_at"] = NOW - age
    return read(parts)


def test_source_absent_after_eligibility_is_unverifiable_never_removed_by_retention() -> None:
    # Eligibility is a timing fact. No persisted fact records who deleted the content.
    lineage = removed(baseline(), RETENTION_WINDOW)
    assert lineage.retention.state == "unverifiable"
    found = {(f.code, f.status) for f in lineage.integrity}
    assert ("source_missing_retention_unverifiable", "unverifiable") in found
    assert {f.status for f in lineage.integrity} == {"unverifiable"}
    # Persisted facts remain and are presented as they are. No deleted graph is invented.
    action = lineage.actions[0]
    assert lineage.goal_lock.source_id is not None
    assert lineage.goal_lock.source_digest is not None
    assert [(e.node_id, e.resolution) for e in action.proposal.evidence] == [
        (action.proposal.evidence[0].node_id, "unresolved")
    ]
    assert action.stage == "verified"
    assert len(action.decisions) == 1 and action.execution is not None
    assert lineage.source_binding.status == "unverifiable"
    assert (lineage.contents, lineage.edges, lineage.findings) == ((), (), ())
    assert lineage.bounds.observed.nodes == lineage.bounds.observed.edges == 0
    assert lineage.relationships and not any(
        r.kind in {"derived_from", "finding_on_content"} for r in lineage.relationships
    )
    # An unresolved evidence id is explained by the unverifiable absence, not a second anomaly.
    assert "evidence_unresolved" not in codes(lineage)


def test_source_absent_before_it_could_be_eligible_is_inconsistent() -> None:
    lineage = removed(baseline(), RETENTION_WINDOW - timedelta(microseconds=1))
    assert lineage.retention.state == "inconsistent"
    assert {"source_missing_before_retention", "evidence_unresolved"} <= codes(lineage)
    assert "source_missing_retention_unverifiable" not in codes(lineage)
    assert lineage.source_binding.status == "inconsistent"


def test_there_is_no_grace_period_around_the_eligibility_boundary() -> None:
    assert removed(baseline(), RETENTION_WINDOW).retention.state == "unverifiable"
    assert removed(baseline(), RETENTION_WINDOW + timedelta(minutes=1)).retention.state == (
        "unverifiable"
    )
    assert removed(baseline(), RETENTION_WINDOW - timedelta(minutes=1)).retention.state == (
        "inconsistent"
    )


@pytest.mark.parametrize(
    "age", [timedelta(0), timedelta(hours=23), timedelta(hours=24), timedelta(days=400)]
)
def test_removed_by_retention_is_never_emitted(age: timedelta) -> None:
    for build in (baseline, legacy_parts):
        assert removed(build(), age).retention.state != "removed_by_retention"
    partial = baseline()
    partial["nodes"][0]["id"] = str(uuid4())
    partial["run"]["created_at"] = NOW - age
    assert read(partial).retention.state != "removed_by_retention"


def test_source_missing_while_other_nodes_remain_is_inconsistent_at_any_age() -> None:
    for age in (timedelta(hours=1), timedelta(days=30)):
        parts = baseline()
        parts["nodes"][0]["id"] = str(uuid4())
        parts["run"]["created_at"] = NOW - age
        lineage = read(parts)
        assert lineage.retention.state == "inconsistent"
        assert "source_missing_with_graph_present" in codes(lineage)


def test_absent_source_with_invalid_envelope_is_unverifiable_without_a_retention_claim() -> None:
    parts = baseline()
    parts["run"]["envelope"] = {}
    lineage = removed(parts, timedelta(days=2))
    assert lineage.retention.state == "unverifiable"
    assert "source_missing_retention_unverifiable" not in codes(lineage)


# ---- bounds -------------------------------------------------------------------------


def test_truncated_sets_are_reported_and_cross_set_checks_become_unverifiable() -> None:
    parts = baseline()
    parts["truncated"] = frozenset({"content_nodes"})
    parts["nodes"].clear()
    lineage = read(parts)
    assert lineage.bounds.truncated is True
    assert lineage.bounds.truncated_sets == ("content_nodes",)
    assert lineage.retention.state == "unverifiable"
    assert lineage.actions[0].proposal.evidence[0].resolution == "unverifiable"
    assert {f.status for f in lineage.integrity} == {"unverifiable"}
    assert "bound_exceeded" in codes(lineage)
    assert "evidence_unresolved" not in codes(lineage)


def test_bounds_report_the_caps_and_observed_counts() -> None:
    lineage = read(baseline())
    assert lineage.bounds.caps == DEFAULT_BOUNDS
    observed = lineage.bounds.observed
    assert (observed.nodes, observed.edges, observed.actions, observed.decisions) == (1, 0, 1, 1)


# ---- stages -------------------------------------------------------------------------


def stage_of(parts: Parts, **run: Any) -> str:
    parts["run"].update(run)
    return read(parts).actions[0].stage


def test_stage_derivation() -> None:
    proposed = baseline()
    proposed["decisions"].clear()
    proposed["executions"].clear()
    proposed["tickets"].clear()
    proposed["actions"][0]["verdict"] = None
    assert stage_of(proposed, state="AUTHORIZING") == "proposed"

    blocked = baseline()
    blocked["decisions"][0]["verdict"] = "BLOCK"
    blocked["actions"][0]["verdict"] = "BLOCK"
    blocked["executions"].clear()
    blocked["tickets"].clear()
    assert stage_of(blocked, state="BLOCKED") == "blocked"

    authorized = baseline()
    authorized["executions"].clear()
    authorized["tickets"].clear()
    assert stage_of(authorized, state="AUTHORIZING") == "authorized"
    assert stage_of(authorized, state="CANCELLED") == "cancelled"
    assert stage_of(authorized, state="EXPIRED") == "expired"
    assert stage_of(authorized, state="FAILED") == "failed"

    pending = baseline()
    review = add_review(pending)
    pending["decisions"][0].update(verdict="REVIEW", review_id=review["id"])
    pending["actions"][0]["verdict"] = "REVIEW"
    pending["executions"].clear()
    pending["tickets"].clear()
    assert stage_of(pending, state="AWAITING_REVIEW") == "review_pending"
    review["expires_at"] = NOW - timedelta(seconds=1)
    assert stage_of(pending, state="AWAITING_REVIEW") == "expired"
    review.update(decision="reject", decided_at=NOW - timedelta(minutes=5))
    assert stage_of(pending, state="BLOCKED") == "blocked"


def test_verified_requires_a_recorded_verification_time_not_a_run_state() -> None:
    parts = baseline()
    parts["executions"][0]["verified_at"] = None
    assert stage_of(parts, state="COMPLETED") == "executed"
    assert read(parts).actions[0].path.complete is False


def test_terminal_run_state_applies_only_to_the_latest_action() -> None:
    parts = baseline()
    first = parts["actions"][0]
    parts["decisions"][0]["verdict"] = "BLOCK"
    first["verdict"] = "BLOCK"
    parts["executions"].clear()
    parts["tickets"].clear()
    second = copy.deepcopy(first)
    second.update(id=str(uuid4()), verdict=None, created_at=first["created_at"] + timedelta(1))
    parts["actions"].append(second)
    parts["run"]["state"] = "CANCELLED"
    stages = [a.stage for a in read(parts).actions]
    assert stages == ["blocked", "cancelled"]
