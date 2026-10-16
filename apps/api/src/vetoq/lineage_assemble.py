"""Pure assembly of one run's lineage from rows read under a single snapshot.

Nothing here touches the database. A hand-built `Snapshot` therefore exercises
inconsistencies the schema prevents, so each integrity check is testable. A fact the
database never recorded is `not_recorded`. A fact that contradicts another recorded fact
is an integrity finding. The two are never conflated, and no single NULL decides which.

Lineage is evidence and never authority. The assembler is not imported by the workflow or
the Action Guard, and its output is never an input to either.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import ValidationError

from vetoq.contracts import GoalLock, Proposal, action_digest
from vetoq.lineage_graph import analyze_graph
from vetoq.lineage_model import (
    ActionLineage,
    Basis,
    BodyState,
    BoundsReport,
    Check,
    ContentEdgeEntity,
    ContentEntity,
    EvidenceRef,
    ExecutionEntity,
    FindingEntity,
    GoalLockEntity,
    GuardDecisionEntity,
    IntegrityCode,
    IntegrityFinding,
    LineageBounds,
    ObservedCounts,
    ParserIdentity,
    PathStep,
    ProducerRecord,
    ProposalEntity,
    RelationKind,
    Relationship,
    RetentionState,
    RetentionSummary,
    ReviewEntity,
    RunLineage,
    RunSummary,
    SourceBinding,
    Stage,
    TicketEntity,
    TransformStepEntity,
    VerifiedPath,
)

Row = dict[str, Any]

# Content retention window: the original expires 24 hours after it is written, alongside
# the run row. This is the only retention timing fact. It is not a grace period.
RETENTION_WINDOW = timedelta(hours=24)

SET_NAMES = (
    "content_nodes",
    "content_edges",
    "content_edge_steps",
    "findings",
    "actions",
    "guard_decisions",
    "reviews",
    "executions",
    "tickets",
)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Rows of one run read under one snapshot. `truncated` names every capped set."""

    run: Row
    read_time: datetime
    nodes: Sequence[Row]
    edges: Sequence[Row]
    steps: Sequence[Row]
    findings: Sequence[Row]
    actions: Sequence[Row]
    decisions: Sequence[Row]
    reviews: Sequence[Row]
    executions: Sequence[Row]
    tickets: Sequence[Row]
    truncated: frozenset[str] = frozenset()


class _Assembler:
    def __init__(self, snapshot: Snapshot, bounds: LineageBounds) -> None:
        self.snapshot = snapshot
        self.bounds = bounds
        self.run = snapshot.run
        self.run_id = str(snapshot.run["id"])
        self.workspace_id = str(snapshot.run["workspace_id"])
        self.read_time = snapshot.read_time
        self.truncated = snapshot.truncated
        self.issues: list[IntegrityFinding] = []
        self.relationships: list[Relationship] = []
        self.max_depth = 0

    # ---- helpers -----------------------------------------------------------------

    def flag(
        self,
        code: IntegrityCode,
        subject: str,
        status: Literal["inconsistent", "unverifiable"] = "inconsistent",
    ) -> None:
        self.issues.append(IntegrityFinding(code=code, status=status, subject=subject))

    def relate(
        self,
        kind: RelationKind,
        source: str,
        target: str | None,
        basis: Basis = "structural_fk",
    ) -> None:
        self.relationships.append(
            Relationship(kind=kind, source=source, target=target, basis=basis)
        )

    def scoped(self, rows: Sequence[Row], prefix: str) -> list[Row]:
        """Keep rows of the trusted run. A foreign row is excluded and reported."""

        kept: list[Row] = []
        for row in rows:
            if str(row["workspace_id"]) == self.workspace_id and str(row["run_id"]) == self.run_id:
                kept.append(row)
            else:
                self.flag("scope_mismatch", f"{prefix}:{row['id']}")
        return kept

    def missing(self, owner_set: str) -> Literal["inconsistent", "unverifiable"]:
        return "unverifiable" if owner_set in self.truncated else "inconsistent"

    # ---- assembly ----------------------------------------------------------------

    def assemble(self) -> RunLineage:
        for name in sorted(self.truncated):
            self.flag("bound_exceeded", name, "unverifiable")
        envelope = self._envelope()
        goal_lock = self._goal_lock_entity(envelope)
        source_id = str(envelope.source_id) if envelope else None

        nodes = self.scoped(self.snapshot.nodes, "content")
        edges = self.scoped(self.snapshot.edges, "edge")
        node_ids = {str(n["id"]) for n in nodes}
        retention = self._retention(nodes, source_id)
        binding = self._source_binding(envelope, nodes, retention.state)
        contents, edge_entities = self._content(nodes, edges, node_ids, source_id)
        findings = self._findings(node_ids)
        actions = self._actions(envelope, source_id, binding, retention.state, node_ids)
        if binding.source_id is not None:
            self.relate(
                "goal_lock_binds_source",
                goal_lock.id,
                f"content:{binding.source_id}",
                "envelope_binding",
            )

        observed = ObservedCounts(
            nodes=len(self.snapshot.nodes),
            edges=len(self.snapshot.edges),
            steps=len(self.snapshot.steps),
            findings=len(self.snapshot.findings),
            actions=len(self.snapshot.actions),
            decisions=len(self.snapshot.decisions),
            reviews=len(self.snapshot.reviews),
            executions=len(self.snapshot.executions),
            tickets=len(self.snapshot.tickets),
            max_depth=self.max_depth,
        )
        return RunLineage(
            run=RunSummary(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                state=self.run["state"],
                created_at=self.run["created_at"],
                expires_at=self.run["expires_at"],
                complete=bool(self.run["complete"]),
                uncertain=bool(self.run["uncertain"]),
                cancelled=bool(self.run["cancelled"]),
                failure=self.run["failure"],
            ),
            read_time=self.read_time,
            goal_lock=goal_lock,
            source_binding=binding,
            contents=tuple(contents),
            edges=tuple(edge_entities),
            findings=tuple(findings),
            actions=tuple(actions),
            relationships=tuple(self.relationships),
            integrity=tuple(self.issues),
            retention=retention,
            bounds=BoundsReport(
                caps=self.bounds,
                observed=observed,
                truncated=bool(self.truncated),
                truncated_sets=tuple(sorted(self.truncated)),
            ),
        )

    def _envelope(self) -> GoalLock | None:
        try:
            return GoalLock.model_validate(self.run["envelope"])
        except ValidationError:
            self.flag("envelope_invalid", f"goal_lock:{self.run_id}", "unverifiable")
            return None

    def _goal_lock_entity(self, envelope: GoalLock | None) -> GoalLockEntity:
        identity = f"goal_lock:{self.run_id}"
        if envelope is None:
            return GoalLockEntity(
                id=identity,
                run_id=self.run_id,
                valid=False,
                tool=None,
                tool_version=None,
                destination=None,
                policy_revision=None,
                source_id=None,
                source_digest=None,
                expires_at=None,
            )
        return GoalLockEntity(
            id=identity,
            run_id=self.run_id,
            valid=True,
            tool=envelope.tool,
            tool_version=envelope.tool_version,
            destination=envelope.destination,
            policy_revision=envelope.policy_revision,
            source_id=str(envelope.source_id),
            source_digest=envelope.source_digest,
            expires_at=envelope.expires_at,
        )

    # ---- retention and source binding ---------------------------------------------

    def _retention(self, nodes: Sequence[Row], source_id: str | None) -> RetentionSummary:
        """The state of the run's stored content, without claiming why content is absent.

        Eligibility and deletion cause are separate facts. The persisted facts are: the
        original expires 24 hours after it was written, derived nodes share that expiry, and
        the run row (created by the database clock, and undeletable for 24 hours) records
        when the run began. From these a read can show that content could not yet legitimately
        have been eligible for retention, or that it was eligible. Nothing persisted records
        that `retain`, rather than any other delete, removed content, so an absent original is
        never reported as removed by retention. No clock-skew allowance is applied: none is
        persisted, and inventing one would be an unapproved rule.
        """

        present = len(nodes)
        pending = sum(1 for n in nodes if n["expires_at"] <= self.read_time)
        eligible = self.read_time >= self.run["created_at"] + RETENTION_WINDOW
        source_present = source_id is not None and any(str(n["id"]) == source_id for n in nodes)
        subject = f"content:{source_id}"
        state: RetentionState
        if "content_nodes" in self.truncated:
            state = "unverifiable"
        elif source_id is None:
            state = "unverifiable"
        elif present == 0 and eligible:
            state = "unverifiable"
            self.flag("source_missing_retention_unverifiable", subject, "unverifiable")
        elif present == 0:
            state = "inconsistent"
            self.flag("source_missing_before_retention", subject)
        elif not source_present:
            # Derived nodes share the original's expiry, so one retention delete removes them
            # together. An original gone while derived content remains has another cause.
            state = "inconsistent"
            self.flag("source_missing_with_graph_present", subject)
        elif pending:
            state = "expired_body_pending_deletion"
        else:
            state = "available"
        return RetentionSummary(
            state=state,
            source_present=source_present,
            nodes_present=present,
            nodes_expired_pending_deletion=pending,
        )

    def _source_binding(
        self, envelope: GoalLock | None, nodes: Sequence[Row], retention: RetentionState
    ) -> SourceBinding:
        subject = f"goal_lock:{self.run_id}"
        if envelope is None:
            self.flag("source_binding_unverifiable", subject, "unverifiable")
            return SourceBinding(status="unverifiable", source_id=None)
        source_id = str(envelope.source_id)
        original = next((n for n in nodes if str(n["id"]) == source_id), None)
        if original is None:
            # The retention state already carries the finding that explains the absence.
            return SourceBinding(
                status="unverifiable" if retention == "unverifiable" else "inconsistent",
                source_id=source_id,
            )
        if original["digest"] != envelope.source_digest:
            self.flag("source_digest_mismatch", f"content:{source_id}")
            return SourceBinding(status="inconsistent", source_id=source_id)
        if not original["digest_ok"]:
            return SourceBinding(status="inconsistent", source_id=source_id)
        return SourceBinding(status="consistent", source_id=source_id)

    # ---- content graph -------------------------------------------------------------

    def _content(
        self,
        nodes: Sequence[Row],
        edges: Sequence[Row],
        node_ids: set[str],
        source_id: str | None,
    ) -> tuple[list[ContentEntity], list[ContentEdgeEntity]]:
        steps_by_edge: dict[str, list[Row]] = defaultdict(list)
        for step in self.snapshot.steps:
            steps_by_edge[str(step["edge_id"])].append(step)

        edge_entities: list[ContentEdgeEntity] = []
        parents: dict[str, list[str]] = defaultdict(list)
        children: dict[str, list[str]] = defaultdict(list)
        graph_edges: list[tuple[str, str]] = []
        for edge in edges:
            parent, child = str(edge["parent_id"]), str(edge["child_id"])
            if parent not in node_ids or child not in node_ids:
                self.flag("scope_mismatch", f"edge:{edge['id']}", self.missing("content_nodes"))
                continue
            parents[child].append(parent)
            children[parent].append(child)
            graph_edges.append((parent, child))
            edge_entities.append(self._edge(edge, steps_by_edge.get(str(edge["id"]), [])))
            self.relate("derived_from", f"content:{parent}", f"content:{child}")

        contents: list[ContentEntity] = []
        for node in nodes:
            identity = str(node["id"])
            subject = f"content:{identity}"
            if not node["digest_ok"]:
                self.flag("content_digest_mismatch", subject)
            if node["byte_size"] is not None and node["byte_size"] != node["body_octets"]:
                self.flag("content_size_mismatch", subject)
            derived = node["origin"] == "derived"
            parser = (
                ParserIdentity(id=node["parser_id"], version=node["parser_version"])
                if node["parser_id"] is not None and node["parser_version"] is not None
                else None
            )
            parser_state: Literal["recorded", "not_recorded", "not_applicable"] = (
                "not_applicable"
                if not derived
                else ("recorded" if parser is not None else "not_recorded")
            )
            body_state: BodyState = (
                "expired_body_pending_deletion"
                if node["expires_at"] <= self.read_time
                else "available"
            )
            contents.append(
                ContentEntity(
                    id=subject,
                    origin=node["origin"],
                    supplier=node["supplier"],
                    digest=node["digest"],
                    complete=bool(node["complete"]),
                    is_source=identity == source_id,
                    representation_kind=node["representation_kind"],
                    declared_media_type=node["declared_media_type"],
                    charset=node["charset"],
                    byte_size=node["byte_size"],
                    parser=parser,
                    parser_state=parser_state,
                    body_state=body_state,
                    digest_check="consistent" if node["digest_ok"] else "inconsistent",
                    created_at=node["created_at"],
                    expires_at=node["expires_at"],
                    parent_ids=tuple(f"content:{p}" for p in parents.get(identity, ())),
                    child_ids=tuple(f"content:{c}" for c in children.get(identity, ())),
                )
            )

        if not ({"content_nodes", "content_edges"} & self.truncated):
            analysis = analyze_graph(
                {str(n["id"]): n["origin"] == "derived" for n in nodes},
                graph_edges,
                source_id,
            )
            self.max_depth = analysis.max_depth
            for code, identity in analysis.anomalies:
                self.flag(code, f"content:{identity}")
            if analysis.max_depth > self.bounds.max_traversal_depth:
                self.flag("bound_exceeded", "traversal_depth", "unverifiable")
        return contents, edge_entities

    def _edge(self, edge: Row, steps: Sequence[Row]) -> ContentEdgeEntity:
        ordered = sorted(steps, key=lambda s: s["step_index"])
        count = edge["transform_step_count"]
        recorded: tuple[TransformStepEntity, ...] | None = None
        if count is None:
            if ordered:
                self.flag("edge_steps_inconsistent", f"edge:{edge['id']}")
        else:
            recorded = tuple(
                TransformStepEntity(
                    index=s["step_index"], transform=s["transform"], version=s["version"]
                )
                for s in ordered
            )
            expected = list(range(1, count + 1))
            if [s["step_index"] for s in ordered] != expected:
                self.flag(
                    "edge_steps_inconsistent",
                    f"edge:{edge['id']}",
                    "unverifiable" if "content_edge_steps" in self.truncated else "inconsistent",
                )
        return ContentEdgeEntity(
            id=f"edge:{edge['id']}",
            parent_id=f"content:{edge['parent_id']}",
            child_id=f"content:{edge['child_id']}",
            transform=edge["transform"],
            version=edge["version"],
            lossy=bool(edge["lossy"]),
            steps=recorded,
            steps_state="not_recorded" if count is None else "recorded",
        )

    def _findings(self, node_ids: set[str]) -> list[FindingEntity]:
        found: list[FindingEntity] = []
        for row in self.scoped(self.snapshot.findings, "finding"):
            identity = f"finding:{row['id']}"
            if str(row["node_id"]) not in node_ids:
                self.flag("finding_node_missing", identity, self.missing("content_nodes"))
                continue
            found.append(
                FindingEntity(
                    id=identity,
                    node_id=f"content:{row['node_id']}",
                    origin=row["origin"],
                    family=row["family"],
                    start_offset=row["start_offset"],
                    end_offset=row["end_offset"],
                    version=row["version"],
                )
            )
            self.relate("finding_on_content", identity, f"content:{row['node_id']}")
        return found

    # ---- actions -------------------------------------------------------------------

    def _actions(
        self,
        envelope: GoalLock | None,
        source_id: str | None,
        binding: SourceBinding,
        retention: RetentionState,
        node_ids: set[str],
    ) -> list[ActionLineage]:
        actions = self.scoped(self.snapshot.actions, "proposal")
        decisions = self.scoped(self.snapshot.decisions, "guard_decision")
        reviews = self.scoped(self.snapshot.reviews, "review")
        executions = self.scoped(self.snapshot.executions, "execution")
        tickets = self.scoped(self.snapshot.tickets, "ticket")
        by_action: dict[str, dict[str, list[Row]]] = defaultdict(lambda: defaultdict(list))
        for label, members in (
            ("decisions", decisions),
            ("reviews", reviews),
            ("executions", executions),
            ("tickets", tickets),
        ):
            for row in members:
                by_action[str(row["action_id"])][label].append(row)
        findings_by_node: dict[str, list[str]] = defaultdict(list)
        for row in self.snapshot.findings:
            findings_by_node[str(row["node_id"])].append(f"finding:{row['id']}")
        content_rows = {str(n["id"]): n for n in self.snapshot.nodes}

        built: list[ActionLineage] = []
        latest_id = str(actions[-1]["id"]) if actions else None
        for action in actions:
            action_id = str(action["id"])
            group = by_action.get(action_id, {})
            built.append(
                self._action(
                    action,
                    envelope,
                    binding,
                    retention,
                    node_ids,
                    content_rows,
                    findings_by_node,
                    group,
                    is_latest=action_id == latest_id,
                    source_id=source_id,
                )
            )
        return built

    def _action(
        self,
        action: Row,
        envelope: GoalLock | None,
        binding: SourceBinding,
        retention: RetentionState,
        node_ids: set[str],
        content_rows: Mapping[str, Row],
        findings_by_node: Mapping[str, list[str]],
        group: Mapping[str, list[Row]],
        *,
        is_latest: bool,
        source_id: str | None,
    ) -> ActionLineage:
        action_id = str(action["id"])
        identity = f"proposal:{action_id}"
        digest_check, tool, tool_version = self._proposal_digest(action, envelope, identity)
        evidence, cited = self._evidence(action, node_ids, retention, content_rows, identity)
        producer = self._producer(action)
        colocated = tuple(
            dict.fromkeys(f for node in cited for f in findings_by_node.get(node, ()))
        )
        proposal = ProposalEntity(
            id=identity,
            action_id=action_id,
            digest=action["digest"],
            digest_check=digest_check,
            tool=tool,
            tool_version=tool_version,
            evidence=evidence,
            producer=producer,
            verdict_cache=action["verdict"],
            created_at=action["created_at"],
            findings_on_cited_evidence=colocated,
        )
        self.relate(
            "goal_lock_binds_proposal", f"goal_lock:{self.run_id}", identity, "digest_bound_json"
        )
        for ref in evidence:
            if ref.resolution == "resolved":
                self.relate(
                    "proposal_cites_content",
                    identity,
                    f"content:{ref.node_id}",
                    "digest_bound_json",
                )
        for finding in colocated:
            self.relate("finding_on_cited_evidence", finding, identity, "derived_join")

        decisions = self._decisions(action, group.get("decisions", []), identity, producer)
        review = self._review(action, group.get("reviews", []), identity)
        self._decision_links(action, decisions, review)
        execution = self._execution(action, group.get("executions", []), decisions, identity)
        ticket = self._ticket(group.get("tickets", []), execution, action_id)

        stage = self._stage(action, decisions, review, execution, is_latest)
        path = self._path(
            envelope,
            binding,
            source_id,
            proposal,
            decisions,
            review,
            execution,
            ticket,
            stage,
        )
        return ActionLineage(
            action_id=action_id,
            stage=stage,
            proposal=proposal,
            decisions=tuple(decisions),
            review=review,
            execution=execution,
            ticket=ticket,
            path=path,
        )

    def _proposal_digest(
        self, action: Row, envelope: GoalLock | None, identity: str
    ) -> tuple[Literal["consistent", "inconsistent", "unverifiable"], str | None, int | None]:
        try:
            proposal = Proposal.model_validate(action["proposal"])
        except ValidationError:
            self.flag("proposal_invalid", identity, "unverifiable")
            raw = action["proposal"] if isinstance(action["proposal"], dict) else {}
            tool = raw.get("tool") if isinstance(raw.get("tool"), str) else None
            version = raw.get("tool_version") if isinstance(raw.get("tool_version"), int) else None
            return "unverifiable", tool, version
        if envelope is None:
            self.flag("proposal_digest_unverifiable", identity, "unverifiable")
            return "unverifiable", proposal.tool, proposal.tool_version
        recomputed = action_digest(self.run_id, envelope, proposal)
        if recomputed != action["digest"]:
            self.flag("proposal_digest_mismatch", identity)
            return "inconsistent", proposal.tool, proposal.tool_version
        return "consistent", proposal.tool, proposal.tool_version

    def _evidence(
        self,
        action: Row,
        node_ids: set[str],
        retention: RetentionState,
        content_rows: Mapping[str, Row],
        identity: str,
    ) -> tuple[tuple[EvidenceRef, ...], list[str]]:
        raw = (
            action["proposal"].get("evidence_ids") if isinstance(action["proposal"], dict) else None
        )
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            self.flag("evidence_malformed", identity)
            return (), []
        if len(raw) > self.bounds.max_evidence_ids:
            self.flag("bound_exceeded", identity, "unverifiable")
            raw = raw[: self.bounds.max_evidence_ids]
        refs: list[EvidenceRef] = []
        cited: list[str] = []
        for position, node in enumerate(raw):
            body_state: BodyState | None = None
            if node in node_ids:
                resolution: Literal["resolved", "unresolved", "unverifiable"] = "resolved"
                cited.append(node)
                body_state = (
                    "expired_body_pending_deletion"
                    if content_rows[node]["expires_at"] <= self.read_time
                    else "available"
                )
            elif "content_nodes" in self.truncated:
                resolution = "unverifiable"
            else:
                resolution = "unresolved"
                if retention != "unverifiable":
                    self.flag("evidence_unresolved", identity)
            refs.append(
                EvidenceRef(
                    position=position, node_id=node, resolution=resolution, body_state=body_state
                )
            )
        return tuple(refs), cited

    @staticmethod
    def _producer(action: Row) -> ProducerRecord:
        recorded = (
            action["producer_provider"] is not None
            and action["producer_model"] is not None
            and action["producer_prompt_version"] is not None
        )
        return ProducerRecord(
            state="recorded" if recorded else "not_recorded",
            provider=action["producer_provider"],
            model=action["producer_model"],
            prompt_version=action["producer_prompt_version"],
            response_id=action["producer_response_id"],
        )

    def _decisions(
        self, action: Row, rows: Sequence[Row], identity: str, producer: ProducerRecord
    ) -> list[GuardDecisionEntity]:
        ordered = sorted(rows, key=lambda d: d["ordinal"])
        decisions: list[GuardDecisionEntity] = []
        for row in ordered:
            subject = f"guard_decision:{row['id']}"
            matches = row["action_digest"] == action["digest"]
            if not matches:
                self.flag("decision_digest_mismatch", subject)
            decisions.append(
                GuardDecisionEntity(
                    id=subject,
                    action_id=str(action["id"]),
                    ordinal=row["ordinal"],
                    verdict=row["verdict"],
                    reasons=tuple(row["reasons"]),
                    action_digest=row["action_digest"],
                    policy_revision_observed=row["policy_revision_observed"],
                    guard_version=row["guard_version"],
                    review_id=row["review_id"],
                    evaluated_at=row["evaluated_at"],
                    digest_check="consistent" if matches else "inconsistent",
                )
            )
            self.relate("guard_decision_evaluates", subject, identity)
        if "guard_decisions" not in self.truncated:
            if [d.ordinal for d in decisions] != list(range(1, len(decisions) + 1)):
                self.flag("decision_ordinal_gap", identity)
            if decisions:
                if action["verdict"] != decisions[-1].verdict:
                    self.flag("verdict_cache_mismatch", identity)
            elif action["verdict"] is not None and producer.state == "recorded":
                # A recorded producer proves a writer that also records decisions.
                self.flag("decisions_missing", identity)
        return decisions

    def _review(self, action: Row, rows: Sequence[Row], identity: str) -> ReviewEntity | None:
        if not rows:
            return None
        row = rows[0]
        subject = f"review:{row['id']}"
        missing = tuple(
            name
            for name, absent in (
                ("requested_at", row["requested_at"] is None),
                ("decided_at", row["decision"] is not None and row["decided_at"] is None),
                ("consumed_at", bool(row["consumed"]) and row["consumed_at"] is None),
            )
            if absent
        )
        recorded = [
            t for t in (row["requested_at"], row["decided_at"], row["consumed_at"]) if t is not None
        ]
        ordered_time = all(a <= b for a, b in zip(recorded, recorded[1:], strict=False))
        digest_ok = row["digest"] == action["digest"]
        if not digest_ok:
            self.flag("review_digest_mismatch", subject)
        if not ordered_time:
            self.flag("review_timeline_order", subject)
        if row["consumed"] and row["decision"] != "approve":
            self.flag("review_consumption_inconsistent", subject)
        self.relate("review_for_proposal", subject, identity)
        return ReviewEntity(
            id=subject,
            action_id=str(action["id"]),
            digest=row["digest"],
            decision=row["decision"],
            consumed=bool(row["consumed"]),
            requested_at=row["requested_at"],
            decided_at=row["decided_at"],
            consumed_at=row["consumed_at"],
            expires_at=row["expires_at"],
            not_recorded=missing,
            digest_check="consistent" if digest_ok else "inconsistent",
            timeline_check="consistent" if ordered_time else "inconsistent",
        )

    def _decision_links(
        self,
        action: Row,
        decisions: Sequence[GuardDecisionEntity],
        review: ReviewEntity | None,
    ) -> None:
        for decision in decisions:
            if decision.review_id is not None:
                self.relate(
                    "guard_decision_references_review", decision.id, f"review:{decision.review_id}"
                )
            if review is None:
                continue
            if decision.review_id is None:
                self.flag("decision_review_link_missing", decision.id)
            elif f"review:{decision.review_id}" != review.id:
                self.flag("decision_review_link_mismatch", decision.id)

    def _execution(
        self,
        action: Row,
        rows: Sequence[Row],
        decisions: Sequence[GuardDecisionEntity],
        identity: str,
    ) -> ExecutionEntity | None:
        if not rows:
            return None
        row = rows[0]
        subject = f"execution:{row['id']}"
        digest_ok = row["digest"] == action["digest"]
        if not digest_ok:
            self.flag("execution_digest_mismatch", subject)
        authorization: Check
        link = row["guard_decision_id"]
        allows = [d for d in decisions if d.verdict == "ALLOW"]
        if link is None:
            if allows:
                # An ALLOW decision proves a writer that links every execution it makes.
                authorization = "inconsistent"
                self.flag("execution_link_missing", subject)
            else:
                authorization = "not_recorded"
            self.relate("execution_authorized_by", subject, None, "not_recorded")
        else:
            match = next((d for d in decisions if d.id == f"guard_decision:{link}"), None)
            if match is None:
                authorization = (
                    "unverifiable" if "guard_decisions" in self.truncated else "inconsistent"
                )
                self.flag("execution_link_invalid", subject, self.missing("guard_decisions"))
            elif match.verdict != "ALLOW" or match.action_digest != row["digest"]:
                authorization = "inconsistent"
                self.flag("execution_link_invalid", subject)
            else:
                authorization = "consistent"
                self.relate("execution_authorized_by", subject, match.id)
        self.relate("execution_of_proposal", subject, identity)
        return ExecutionEntity(
            id=subject,
            action_id=str(action["id"]),
            ticket_id=str(row["ticket_id"]),
            digest=row["digest"],
            guard_decision_id=link,
            committed_at=row["committed_at"],
            verified_at=row["verified_at"],
            digest_check="consistent" if digest_ok else "inconsistent",
            authorization=authorization,
        )

    def _ticket(
        self, rows: Sequence[Row], execution: ExecutionEntity | None, action_id: str
    ) -> TicketEntity | None:
        ticket = rows[0] if rows else None
        if execution is not None:
            if ticket is None or str(ticket["id"]) != execution.ticket_id:
                self.flag("execution_ticket_missing", execution.id, self.missing("tickets"))
            else:
                self.relate("execution_produced_ticket", execution.id, f"ticket:{ticket['id']}")
        if ticket is None:
            return None
        return TicketEntity(
            id=f"ticket:{ticket['id']}", action_id=action_id, created_at=ticket["created_at"]
        )

    # ---- derived stage and path ------------------------------------------------------

    def _stage(
        self,
        action: Row,
        decisions: Sequence[GuardDecisionEntity],
        review: ReviewEntity | None,
        execution: ExecutionEntity | None,
        is_latest: bool,
    ) -> Stage:
        if execution is not None:
            # Verified requires the recorded verification time, not merely a run state.
            return "verified" if execution.verified_at is not None else "executed"
        latest = decisions[-1] if decisions else None
        if (latest is not None and latest.verdict == "BLOCK") or (
            review is not None and review.decision == "reject"
        ):
            return "blocked"
        if is_latest:
            terminal: dict[str, Stage] = {
                "CANCELLED": "cancelled",
                "EXPIRED": "expired",
                "FAILED": "failed",
            }
            if self.run["state"] in terminal:
                return terminal[self.run["state"]]
        if review is not None and review.decision is None and review.expires_at <= self.read_time:
            return "expired"
        if latest is not None and latest.verdict == "ALLOW":
            return "authorized"
        if review is not None:
            return "review_pending"
        if latest is None and action["verdict"] is not None:
            return "latest_only"
        return "proposed"

    def _path(
        self,
        envelope: GoalLock | None,
        binding: SourceBinding,
        source_id: str | None,
        proposal: ProposalEntity,
        decisions: Sequence[GuardDecisionEntity],
        review: ReviewEntity | None,
        execution: ExecutionEntity | None,
        ticket: TicketEntity | None,
        stage: Stage,
    ) -> VerifiedPath:
        steps = [
            PathStep(
                kind="goal_lock",
                entity=f"goal_lock:{self.run_id}",
                check="consistent" if envelope is not None else "unverifiable",
            )
        ]
        if source_id is not None:
            steps.append(
                PathStep(kind="source", entity=f"content:{source_id}", check=binding.status)
            )
        digest_by_content = {c["id"]: c for c in self.snapshot.nodes}
        for ref in proposal.evidence:
            resolved = ref.resolution == "resolved"
            node = digest_by_content.get(ref.node_id)
            check: Check = (
                ("consistent" if node is not None and node["digest_ok"] else "inconsistent")
                if resolved
                else "unverifiable"
            )
            steps.append(PathStep(kind="evidence", entity=f"content:{ref.node_id}", check=check))
        steps.append(PathStep(kind="proposal", entity=proposal.id, check=proposal.digest_check))
        if decisions:
            decision = decisions[-1]
            steps.append(
                PathStep(kind="guard_decision", entity=decision.id, check=decision.digest_check)
            )
        if review is not None:
            both = review.digest_check == "consistent" and review.timeline_check == "consistent"
            steps.append(
                PathStep(
                    kind="review", entity=review.id, check="consistent" if both else "inconsistent"
                )
            )
        if execution is not None:
            check = (
                execution.authorization
                if execution.digest_check == "consistent"
                else "inconsistent"
            )
            steps.append(PathStep(kind="execution", entity=execution.id, check=check))
        if ticket is not None:
            steps.append(PathStep(kind="ticket", entity=ticket.id, check="consistent"))
        kinds = {step.kind for step in steps}
        involved = {step.entity for step in steps} | {d.id for d in decisions}
        involved.add(proposal.id)
        complete = (
            stage == "verified"
            and {"guard_decision", "execution", "ticket"} <= kinds
            and all(step.check == "consistent" for step in steps)
            and not any(issue.subject in involved for issue in self.issues)
        )
        return VerifiedPath(steps=tuple(steps), complete=complete)


def assemble(snapshot: Snapshot, bounds: LineageBounds) -> RunLineage:
    return _Assembler(snapshot, bounds).assemble()
