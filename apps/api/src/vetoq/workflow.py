"""Durable workflow and the only business write dispatcher."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import DBAPIError

from vetoq.action_guard import GuardInput, guard
from vetoq.contracts import (
    GUARD_VERSION,
    POLICY,
    TERMINAL,
    Analysis,
    DeclaredSubmission,
    GoalLock,
    LegacySubmission,
    Proposal,
    action_digest,
    digest,
)
from vetoq.db import execute, one, rows
from vetoq.ingestion.errors import IngestionError, ProcessingFailure, RegistryError
from vetoq.ingestion.identity import SubmissionIdentity, source_digest, submission_digest
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import normalize_media_type, stored_media_type
from vetoq.ingestion.pipeline import (
    ingest_staged,
    is_staged_original,
    legacy_metadata_absent,
    persist_recorded_base64,
)
from vetoq.ingestion.registry import AdapterRegistry, production_registry
from vetoq.inspection import content_digest, inspect
from vetoq.lineage_failure import (
    DECISION_WRITE,
    EXECUTION_LINK,
    PRODUCER_WRITE,
    is_lineage_integrity_failure,
)
from vetoq.providers.base import InferenceRequest, InferenceResult, Provider, ProviderError

logger = logging.getLogger("vetoq.worker")

PRODUCER_FIELD_LIMIT = 120
PRODUCER_RESPONSE_ID_LIMIT = 200


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class DomainError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


def event(
    c: Connection, run: dict[str, Any], kind: str, detail: object, actor: str = "runner"
) -> None:
    execute(
        c,
        """
        INSERT INTO audit_events(workspace_id,run_id,sequence,actor,type,detail)
        SELECT :w,:r,COALESCE(MAX(sequence),0)+1,:a,:t,CAST(:d AS jsonb)
        FROM audit_events WHERE run_id=:r
        """,
        {"w": run["workspace_id"], "r": run["id"], "a": actor, "t": kind, "d": json.dumps(detail)},
    )


def member(c: Connection, workspace: str, principal: str, lock: bool = False) -> dict[str, Any]:
    workspace_row = one(
        c,
        "SELECT * FROM workspaces WHERE id=:w" + (" FOR UPDATE" if lock else ""),
        {"w": workspace},
    )
    row = one(
        c,
        "SELECT * FROM memberships WHERE workspace_id=:w AND principal=:p"
        + (" FOR UPDATE" if lock else ""),
        {"w": workspace, "p": principal},
    )
    if not workspace_row or not workspace_row["active"] or not row or not row["active"]:
        raise DomainError("not_found", 404)
    return row


def submit(engine: Engine, principal: str, request: LegacySubmission, key: str) -> str:
    """Persist one historical Module 002 row. The live route does not call this."""
    if (
        not 1 <= len(key) <= 128
        or len(request.goal.encode()) > BUDGETS.goal_bytes
        or len(request.source.encode()) > BUDGETS.source_bytes
    ):
        raise DomainError("input_limit", 413)
    if not request.goal.strip() or not request.source.strip():
        raise DomainError("empty_input", 422)
    workspace = str(request.workspace_id)
    fingerprint = digest(request.model_dump(mode="json"))
    with engine.begin() as c:
        member(c, workspace, principal, True)
        existing = one(
            c,
            "SELECT * FROM runs WHERE workspace_id=:w AND principal=:p AND submission_key=:k",
            {"w": workspace, "p": principal, "k": key},
        )
        if existing:
            if existing["submission_digest"] != fingerprint:
                raise DomainError("idempotency_conflict")
            return str(existing["id"])
        count = one(
            c,
            """
            SELECT count(*) AS n FROM runs
            WHERE workspace_id=:w AND created_at>now()-interval '1 hour'
            """,
            {"w": workspace},
        )
        if count and count["n"] >= BUDGETS.accepted_runs_per_workspace_per_hour:
            raise DomainError("workspace_rate_limit", 429)
        run_id, source_id = uid(), uid()
        expiry = now() + timedelta(minutes=30)
        envelope = GoalLock(
            principal=principal,
            workspace_id=request.workspace_id,
            source_id=source_id,
            source_digest=content_digest(request.source),
            goal=request.goal,
            expires_at=expiry,
        )
        execute(
            c,
            """
            INSERT INTO runs(
                id,workspace_id,principal,submission_key,submission_digest,
                envelope,state,expires_at
            ) VALUES(:r,:w,:p,:k,:d,CAST(:g AS jsonb),'QUEUED',:e)
            """,
            {
                "r": run_id,
                "w": workspace,
                "p": principal,
                "k": key,
                "d": fingerprint,
                "g": envelope.model_dump_json(),
                "e": expiry,
            },
        )
        execute(
            c,
            """
            INSERT INTO content_nodes(
                id,workspace_id,run_id,origin,supplier,digest,content,
                trust,complete,expires_at
            ) VALUES(:id,:w,:r,'pasted-email',:p,:d,:s,'untrusted',true,:e)
            """,
            {
                "id": source_id,
                "w": workspace,
                "r": run_id,
                "p": principal,
                "d": envelope.source_digest,
                "s": request.source,
                "e": now() + timedelta(hours=24),
            },
        )
        event(
            c,
            {"id": run_id, "workspace_id": workspace},
            "RUN_ACCEPTED",
            {"goal_digest": digest(envelope.model_dump(mode="json")), "policy": POLICY},
            principal,
        )
        return run_id


def load_declared_submission(payload: object) -> DeclaredSubmission:
    """Parse the staged M003 body. The error carries the code and not the source."""

    try:
        return DeclaredSubmission.model_validate(payload)
    except ValidationError:
        raise DomainError("invalid_input", 422) from None


def accept_declared_submission(
    engine: Engine,
    principal: str,
    request: DeclaredSubmission,
    key: str,
    *,
    registry: AdapterRegistry | None = None,
) -> str:
    """Persist one original after pre-accept validation.

    `POST /runs` builds a `DeclaredSubmission` with the server-owned template
    and calls this function. The worker canonicalizes a queued original when
    that stored row is staged M003 metadata. A validation failure rolls the
    transaction back and writes no run, node, Goal Lock, or audit event.
    """

    selected = production_registry() if registry is None else registry
    workspace = str(request.workspace_id)
    with engine.begin() as c:
        member(c, workspace, principal, True)
        if (
            not 1 <= len(key) <= 128
            or len(request.goal.encode()) > BUDGETS.goal_bytes
            or len(request.source.encode()) > BUDGETS.source_bytes
        ):
            raise DomainError("input_limit", 413)
        if not request.goal.strip() or not request.source.strip():
            raise DomainError("empty_input", 422)
        try:
            declaration = normalize_media_type(request.media_type)
            adapter = selected.resolve(declaration.media_type)
            exact = adapter.validate(request.source, declaration)
        except RegistryError:
            raise DomainError("internal_error", 500) from None
        except IngestionError as error:
            raise DomainError(error.code, error.status) from None
        identity = SubmissionIdentity(
            workspace_id=request.workspace_id,
            template=request.template,
            goal=request.goal,
            source=exact,
            confirmed=request.confirmed,
            declared_media_type=declaration.media_type,
        )
        fingerprint = submission_digest(identity)
        existing = one(
            c,
            "SELECT * FROM runs WHERE workspace_id=:w AND principal=:p AND submission_key=:k",
            {"w": workspace, "p": principal, "k": key},
        )
        if existing:
            if existing["submission_digest"] != fingerprint:
                raise DomainError("idempotency_conflict")
            return str(existing["id"])
        count = one(
            c,
            """
            SELECT count(*) AS n FROM runs
            WHERE workspace_id=:w AND created_at>now()-interval '1 hour'
            """,
            {"w": workspace},
        )
        if count and count["n"] >= BUDGETS.accepted_runs_per_workspace_per_hour:
            raise DomainError("workspace_rate_limit", 429)
        run_id, source_id = uid(), uid()
        expiry = now() + timedelta(minutes=30)
        digest_value = source_digest(exact)
        envelope = GoalLock(
            principal=principal,
            workspace_id=request.workspace_id,
            source_id=source_id,
            source_digest=digest_value,
            goal=request.goal,
            expires_at=expiry,
        )
        execute(
            c,
            """
            INSERT INTO runs(
                id,workspace_id,principal,submission_key,submission_digest,
                envelope,state,expires_at
            ) VALUES(:r,:w,:p,:k,:d,CAST(:g AS jsonb),'QUEUED',:e)
            """,
            {
                "r": run_id,
                "w": workspace,
                "p": principal,
                "k": key,
                "d": fingerprint,
                "g": envelope.model_dump_json(),
                "e": expiry,
            },
        )
        execute(
            c,
            """
            INSERT INTO content_nodes(
                id,workspace_id,run_id,origin,supplier,digest,content,
                trust,complete,expires_at,
                declared_media_type,representation_kind,parser_id,parser_version,
                charset,byte_size
            ) VALUES(
                :id,:w,:r,'pasted-email',:p,:d,:s,'untrusted',true,:e,
                :media,'original',NULL,NULL,:charset,:bytes
            )
            """,
            {
                "id": source_id,
                "w": workspace,
                "r": run_id,
                "p": principal,
                "d": digest_value,
                "s": exact,
                "e": now() + timedelta(hours=24),
                "media": stored_media_type(declaration),
                "charset": None if declaration.charset is None else declaration.charset.value,
                "bytes": len(exact.encode("utf-8")),
            },
        )
        event(
            c,
            {"id": run_id, "workspace_id": workspace},
            "RUN_ACCEPTED",
            {
                "goal_digest": digest(envelope.model_dump(mode="json")),
                "policy": POLICY,
                "declared_media_type": stored_media_type(declaration),
                "byte_size": len(exact.encode("utf-8")),
                "channel": "user_paste",
                "parser_id": None,
            },
            principal,
        )
        return run_id


def locked_run(c: Connection, run_id: str, fence: int | None = None) -> dict[str, Any]:
    """Lock one run row. Callers lock workspace and membership only around a write."""
    run = one(c, "SELECT * FROM runs WHERE id=:id FOR UPDATE", {"id": run_id})
    if run is None:
        raise DomainError("not_found", 404)
    if fence is not None and (
        run["fence"] != fence or run["lease_until"] is None or run["lease_until"] <= now()
    ):
        raise DomainError("stale_worker")
    return run


def result_run(c: Connection, run_id: str, fence: int) -> dict[str, Any] | None:
    """Lock a run and reject a result whose lease was cancelled or superseded."""
    run = locked_run(c, run_id)
    if run["fence"] != fence or run["lease_until"] is None or run["lease_until"] <= now():
        return None
    return run


@dataclass
class Claim:
    run_id: str | None = None
    previous_fence: int | None = None
    fence: int | None = None
    committed: bool = False
    failure_detail: dict[str, Any] | None = None


def fail_closed(c: Connection, run: dict[str, Any], code: str) -> None:
    if run["state"] in TERMINAL:
        return
    execute(
        c,
        "UPDATE runs SET state='FAILED',failure=:code,lease_until=NULL WHERE id=:r",
        {"code": code, "r": run["id"]},
    )
    event(c, run, "FAILED", {"reason": code})
    logger.warning("run_failed run_id=%s reason=%s", run["id"], code)


def quarantine(engine: Engine, claim: Claim, code: str) -> bool:
    """Persist a terminal failure for the claimed run unless a newer fence owns it."""
    if claim.run_id is None:
        return False
    with engine.begin() as c:
        run = one(c, "SELECT * FROM runs WHERE id=:id FOR UPDATE", {"id": claim.run_id})
        if run is None or run["state"] in TERMINAL:
            return False
        if claim.committed:
            if run["fence"] != claim.fence:
                return False
        elif run["fence"] != claim.previous_fence or (
            run["lease_until"] is not None and run["lease_until"] > now()
        ):
            return False
        if code in {"parser_limit_exceeded", "ingestion_incomplete", "canonicalization_failure"}:
            detail = dict(claim.failure_detail or {})
            detail["reason"] = code
            event(c, run, "INGESTION_INCOMPLETE", detail)
        fail_closed(c, run, code)
    return True


def record_guard_decision(
    c: Connection,
    run: dict[str, Any],
    action: dict[str, Any],
    verdict: str,
    reasons: list[str],
    policy_revision: str,
    review_id: str | None,
) -> str:
    """Append one structural record of a guard evaluation, in the caller's transaction.

    The record describes what the deterministic guard returned. Nothing reads it back to
    decide anything. The ordinal continues the action's own history under the action row
    lock that `authorize` already holds. Any failure rolls the whole supporting transaction
    back. A rejected lineage integrity rule is `lineage_write_failure`; any other database
    failure propagates unchanged.
    """

    decision_id = uid()
    try:
        execute(
            c,
            """
            INSERT INTO guard_decisions(
                id,workspace_id,run_id,action_id,ordinal,verdict,reasons,action_digest,
                policy_revision_observed,guard_version,review_id
            )
            SELECT :id,:w,:r,:a,COALESCE(MAX(ordinal),0)+1,:v,CAST(:reasons AS text[]),:d,
                :p,:g,:review
            FROM guard_decisions WHERE workspace_id=:w AND run_id=:r AND action_id=:a
            """,
            {
                "id": decision_id,
                "w": run["workspace_id"],
                "r": run["id"],
                "a": action["id"],
                "v": verdict,
                "reasons": reasons,
                "d": action["digest"],
                "p": policy_revision,
                "g": GUARD_VERSION,
                "review": review_id,
            },
        )
    except DBAPIError as error:
        # Only a lineage integrity rule rejecting this write is a lineage failure. A timeout,
        # cancellation, lock failure, or lost connection keeps its general classification.
        if is_lineage_integrity_failure(error, DECISION_WRITE):
            raise DomainError("lineage_write_failure") from None
        raise
    return decision_id


def authorize(c: Connection, run: dict[str, Any]) -> None:
    action = one(
        c,
        "SELECT * FROM actions WHERE run_id=:r ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE",
        {"r": run["id"]},
    )
    if action is None:
        raise DomainError("proposal_missing")
    prior = one(c, "SELECT * FROM executions WHERE action_id=:a", {"a": action["id"]})
    if prior:
        execute(c, "UPDATE runs SET state='VERIFYING' WHERE id=:r", {"r": run["id"]})
        return
    workspace = one(
        c, "SELECT * FROM workspaces WHERE id=:w FOR UPDATE", {"w": run["workspace_id"]}
    )
    membership = one(
        c,
        "SELECT * FROM memberships WHERE workspace_id=:w AND principal=:p FOR UPDATE",
        {"w": run["workspace_id"], "p": run["principal"]},
    )
    review = one(c, "SELECT * FROM reviews WHERE action_id=:a FOR UPDATE", {"a": action["id"]})
    reviewer = (
        one(
            c,
            "SELECT * FROM memberships WHERE workspace_id=:w AND principal=:p FOR UPDATE",
            {"w": run["workspace_id"], "p": review["reviewer"]},
        )
        if review and review["reviewer"]
        else None
    )
    proposal = Proposal.model_validate(action["proposal"])
    envelope = GoalLock.model_validate(run["envelope"])
    nodes = rows(
        c,
        "SELECT id FROM content_nodes WHERE run_id=:r AND complete AND expires_at>now()",
        {"r": run["id"]},
    )
    decision = guard(
        GuardInput(
            run_id=run["id"],
            principal=run["principal"],
            envelope=envelope,
            proposal=proposal,
            persisted_digest=action["digest"],
            now=now(),
            membership_active=bool(membership and membership["active"]),
            workspace_active=bool(workspace and workspace["active"]),
            policy_revision=workspace["policy_revision"] if workspace else "",
            state=run["state"],
            writes=run["writes"],
            proposals=run["proposals"],
            complete=run["complete"] and str(envelope.source_id) in {n["id"] for n in nodes},
            source_ids=frozenset(n["id"] for n in nodes),
            uncertain=run["uncertain"],
            cancelled=run["cancelled"],
            approval_digest=review["digest"]
            if review and review["decision"] == "approve"
            else None,
            approval_expires=review["expires_at"] if review else None,
            approval_consumed=bool(review and review["consumed"]),
            reviewer_active=bool(
                reviewer and reviewer["active"] and reviewer["role"] == "reviewer"
            ),
            reviewer_is_originator=bool(
                review and review["reviewer"] and review["reviewer"] == run["principal"]
            ),
        )
    )
    # Structural lineage shares this transaction with the state transition it supports.
    # A new review is created first so the REVIEW decision can reference it. A decision
    # after an approval references that same review.
    review_id = None if review is None else str(review["id"])
    if decision.verdict == "REVIEW" and review is None:
        review_id = uid()
        execute(
            c,
            """
            INSERT INTO reviews(id,workspace_id,run_id,action_id,digest,expires_at,requested_at)
            VALUES(:id,:w,:r,:a,:d,:e,now())
            """,
            {
                "id": review_id,
                "w": run["workspace_id"],
                "r": run["id"],
                "a": action["id"],
                "d": action["digest"],
                "e": min(envelope.expires_at, now() + timedelta(minutes=10)),
            },
        )
    decision_id = record_guard_decision(
        c,
        run,
        action,
        decision.verdict,
        decision.reasons,
        workspace["policy_revision"] if workspace else "",
        review_id,
    )
    execute(
        c,
        "UPDATE actions SET verdict=:v,reasons=CAST(:reasons AS jsonb) WHERE id=:a",
        {"v": decision.verdict, "reasons": json.dumps(decision.reasons), "a": action["id"]},
    )
    event(
        c,
        run,
        "ACTION_" + decision.verdict,
        {"action_id": action["id"], "digest": action["digest"], "reasons": decision.reasons},
    )
    if decision.verdict == "REVIEW":
        execute(
            c,
            "UPDATE runs SET state='AWAITING_REVIEW',lease_until=NULL WHERE id=:r",
            {"r": run["id"]},
        )
        return
    if decision.verdict == "BLOCK":
        retry = run["continuations"] == 0 and set(decision.reasons).issubset(
            {"GOAL_SCOPE_MISMATCH", "TOOL_NOT_GRANTED"}
        )
        execute(
            c,
            "UPDATE runs SET state=:s,continuations=continuations+:n,lease_until=NULL WHERE id=:r",
            {"r": run["id"], "s": "PROPOSING" if retry else "BLOCKED", "n": int(retry)},
        )
        return
    # The final guard and all business effects share this exact transaction.
    ticket_id = uid()
    execute(
        c,
        """
        INSERT INTO tickets(id,workspace_id,run_id,action_id,title,body)
        VALUES(:id,:w,:r,:a,:title,:body)
        """,
        {
            "id": ticket_id,
            "w": str(proposal.arguments.workspace_id),
            "r": run["id"],
            "a": action["id"],
            "title": proposal.arguments.title,
            "body": proposal.arguments.body,
        },
    )
    try:
        execute(
            c,
            """
            INSERT INTO executions(id,workspace_id,run_id,action_id,ticket_id,digest,
                guard_decision_id)
            VALUES(:id,:w,:r,:a,:t,:d,:decision)
            """,
            {
                "id": uid(),
                "w": run["workspace_id"],
                "r": run["id"],
                "a": action["id"],
                "t": ticket_id,
                "d": action["digest"],
                "decision": decision_id,
            },
        )
    except DBAPIError as error:
        # Only a rejected authorization link is a lineage failure. Any other execution
        # insert failure keeps its existing, general classification.
        if is_lineage_integrity_failure(error, EXECUTION_LINK):
            raise DomainError("lineage_write_failure") from None
        raise
    if review:
        execute(
            c,
            "UPDATE reviews SET consumed=true,consumed_at=now() WHERE id=:id",
            {"id": review["id"]},
        )
    execute(
        c,
        "UPDATE runs SET writes=writes+1,state='VERIFYING',lease_until=NULL WHERE id=:r",
        {"r": run["id"]},
    )
    event(c, run, "TICKET_COMMITTED", {"ticket_id": ticket_id, "action_id": action["id"]})


def verify(c: Connection, run: dict[str, Any]) -> None:
    receipt = one(
        c,
        """
        SELECT e.*,t.title,t.body,a.proposal,a.digest AS action_digest
        FROM executions e JOIN tickets t ON t.id=e.ticket_id
        JOIN actions a ON a.id=e.action_id WHERE e.run_id=:r
        """,
        {"r": run["id"]},
    )
    if receipt is None:
        raise DomainError("receipt_missing")
    proposal = Proposal.model_validate(receipt["proposal"])
    if (
        receipt["digest"] != receipt["action_digest"]
        or receipt["title"] != proposal.arguments.title
        or receipt["body"] != proposal.arguments.body
        or receipt["workspace_id"] != str(proposal.arguments.workspace_id)
    ):
        raise DomainError("outcome_mismatch")
    execute(c, "UPDATE executions SET verified_at=now() WHERE id=:id", {"id": receipt["id"]})
    execute(c, "UPDATE runs SET state='COMPLETED',lease_until=NULL WHERE id=:r", {"r": run["id"]})
    event(c, run, "OUTCOME_VERIFIED", {"ticket_id": receipt["ticket_id"]})


def canonical_evidence_ids(values: object) -> list[str] | None:
    """Return the ids as canonical lowercase UUID strings, or None if they are malformed.

    The list is checked, never rewritten: duplicates are tolerated and order is kept.
    """

    if not isinstance(values, list) or not 1 <= len(values) <= BUDGETS.proposal_evidence_ids:
        return None
    ids: list[str] = []
    for value in values:
        candidate = str(value)
        try:
            if str(UUID(candidate)) != candidate:
                return None
        except ValueError:
            return None
        ids.append(candidate)
    return ids


def resolvable_nodes(c: Connection, run: dict[str, Any], ids: list[str]) -> set[str]:
    found = rows(
        c,
        """
        SELECT id FROM content_nodes
        WHERE workspace_id=:w AND run_id=:r AND id = ANY(CAST(:ids AS text[]))
        """,
        {"w": run["workspace_id"], "r": run["id"], "ids": sorted(set(ids))},
    )
    return {str(row["id"]) for row in found}


def validate_proposal_evidence(c: Connection, run: dict[str, Any], proposal: Proposal) -> None:
    """Proposal evidence must name one to sixteen nodes of this workspace and run."""

    ids = canonical_evidence_ids(proposal.evidence_ids)
    if ids is None or not set(ids).issubset(resolvable_nodes(c, run, ids)):
        raise DomainError("invalid_model_evidence")


def validated_finding_offsets(
    c: Connection, run: dict[str, Any], analysis: Analysis, supplied: dict[str, str]
) -> list[int]:
    """Resolve every model finding to a supplied node of this run and locate its quote.

    A malformed finding is malformed model evidence. It is neither persisted nor turned
    into a policy BLOCK.
    """

    ids = [str(finding.evidence_id) for finding in analysis.findings]
    if ids:
        known = resolvable_nodes(c, run, ids)
        if not set(ids).issubset(known) or not set(ids).issubset(supplied):
            raise DomainError("invalid_model_evidence")
    offsets: list[int] = []
    for finding in analysis.findings:
        start = supplied[str(finding.evidence_id)].find(finding.quote)
        if start < 0:
            raise DomainError("invalid_model_evidence")
        offsets.append(start)
    return offsets


def producer_provenance(run_id: str, result: InferenceResult) -> dict[str, str | None]:
    """Producer facts for one new action, taken from the exact result that produced it.

    The provider, requested model, and prompt version are required. A missing or
    malformed one fails closed. The response id is optional: an empty or oversize id is
    stored as NULL, never as a meaningless identifier, and never truncated. Discarding a
    non-empty oversize id does not fail the run. It logs one warning that carries only the
    run id, provider, and a stable reason, never the discarded value.
    """

    required = (result.provider, result.model, result.prompt_version)
    for value in required:
        if (
            not isinstance(value, str)
            or value != value.strip()
            or not 1 <= len(value) <= PRODUCER_FIELD_LIMIT
        ):
            raise DomainError("lineage_write_failure")
    response_id = result.request_id.strip() if isinstance(result.request_id, str) else ""
    if len(response_id) > PRODUCER_RESPONSE_ID_LIMIT:
        logger.warning(
            "producer_response_id_discarded run_id=%s provider=%s reason=%s",
            run_id,
            result.provider,
            "response_id_too_long",
        )
    return {
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "response_id": response_id if 1 <= len(response_id) <= PRODUCER_RESPONSE_ID_LIMIT else None,
    }


def advance(engine: Engine, provider: Provider, claim: Claim) -> bool:
    with engine.begin() as c:
        candidate = one(
            c,
            """
            SELECT id FROM runs
            WHERE (lease_until IS NULL OR lease_until<now())
              AND (
                state IN ('QUEUED','PROPOSING','AUTHORIZING','VERIFYING')
                OR (
                  state='AWAITING_REVIEW'
                  AND (
                    expires_at<=now()
                    OR EXISTS (
                      SELECT 1 FROM reviews
                      WHERE run_id=runs.id AND decision IS NULL AND expires_at<=now()
                    )
                  )
                )
              )
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """,
        )
        if candidate is None:
            return False
        run = locked_run(c, candidate["id"])
        if run["lease_until"] and run["lease_until"] > now():
            return False
        if run["state"] not in {
            "QUEUED",
            "PROPOSING",
            "AUTHORIZING",
            "VERIFYING",
            "AWAITING_REVIEW",
        }:
            return False
        fence = int(run["fence"]) + 1
        claim.run_id = run["id"]
        claim.previous_fence = int(run["fence"])
        claim.fence = fence
        execute(
            c,
            "UPDATE runs SET fence=:f,lease_until=now()+interval '90 seconds' WHERE id=:r",
            {"f": fence, "r": run["id"]},
        )
        logger.info("worker_claimed run_id=%s fence=%s state=%s", run["id"], fence, run["state"])
        if run["state"] == "VERIFYING":
            verify(c, run)
            return True
        if run["state"] == "AWAITING_REVIEW":
            # An exact-action review that expires is not left waiting forever.
            # It closes as EXPIRED and cannot be executed later.
            if run["cancelled"]:
                execute(
                    c,
                    "UPDATE runs SET state='CANCELLED',lease_until=NULL WHERE id=:r",
                    {"r": run["id"]},
                )
                event(c, run, "CANCELLED", {})
                return True
            review = one(
                c,
                """
                SELECT expires_at FROM reviews
                WHERE run_id=:r AND decision IS NULL
                ORDER BY expires_at LIMIT 1
                """,
                {"r": run["id"]},
            )
            reason = (
                "review_expired"
                if review and review["expires_at"] <= now() and run["expires_at"] > now()
                else "goal_expired"
            )
            execute(
                c,
                "UPDATE runs SET state='EXPIRED',lease_until=NULL WHERE id=:r",
                {"r": run["id"]},
            )
            event(c, run, "EXPIRED", {"reason": reason})
            return True
        if run["cancelled"] or run["expires_at"] <= now():
            state = "CANCELLED" if run["cancelled"] else "EXPIRED"
            execute(
                c,
                "UPDATE runs SET state=:s,lease_until=NULL WHERE id=:r",
                {"s": state, "r": run["id"]},
            )
            event(c, run, state, {})
            return True
        if run["state"] == "AUTHORIZING":
            authorize(c, run)
            return True
        envelope = GoalLock.model_validate(run["envelope"])
        if run["state"] == "QUEUED":
            original = one(
                c, "SELECT * FROM content_nodes WHERE id=:id", {"id": str(envelope.source_id)}
            )
            if original is None or original["digest"] != envelope.source_digest:
                raise DomainError("source_integrity_failure")
            inspection_detail: dict[str, object] = {}
            if is_staged_original(original):
                audit: dict[str, object] = {}

                def record(kind: str, detail: dict[str, object]) -> None:
                    event(c, run, kind, detail)

                try:
                    representations, findings, complete = ingest_staged(
                        c,
                        run,
                        envelope,
                        original,
                        audit,
                        record,
                    )
                except ProcessingFailure as error:
                    audit["reason"] = error.code
                    claim.failure_detail = audit
                    raise DomainError(error.code) from None
                inspection_detail = {
                    "source_id": original["id"],
                    "declared_media_type": audit.get("declared_media_type"),
                    "parser_id": audit.get("parser_id"),
                    "parser_version": audit.get("parser_version"),
                    "derived_count": audit.get("derived_count"),
                }
            elif not legacy_metadata_absent(original):
                raise DomainError("source_integrity_failure")
            else:
                representations, findings, complete = inspect(original["id"], original["content"])
                for node in representations[1:]:
                    parent_id = node.parent
                    if parent_id is None:
                        raise DomainError("ingestion_incomplete")
                    persist_recorded_base64(
                        c,
                        workspace_id=run["workspace_id"],
                        run_id=run["id"],
                        node_id=node.id,
                        edge_id=uid(),
                        parent_id=parent_id,
                        content=node.content,
                        complete=complete,
                        expires_at=original["expires_at"],
                    )
                for found in findings:
                    execute(
                        c,
                        """
                        INSERT INTO findings(
                            id,workspace_id,run_id,node_id,origin,family,explanation,
                            start_offset,end_offset,version
                        ) VALUES(
                            :id,:w,:r,:node_id,'deterministic',:family,
                            :explanation,:start,:end,'rules/1'
                        )
                        """,
                        {"id": uid(), "w": run["workspace_id"], "r": run["id"], **found},
                    )
            event(
                c,
                run,
                "INSPECTION_COMPLETED" if complete else "INSPECTION_INCOMPLETE",
                {
                    "representations": len(representations),
                    "findings": len(findings),
                    **inspection_detail,
                },
            )
            execute(
                c,
                """
                UPDATE runs SET complete=:complete,state=:s,
                    uncertain=uncertain OR :uncertain WHERE id=:r
                """,
                {
                    "r": run["id"],
                    "complete": complete,
                    "uncertain": bool(findings),
                    "s": "PROPOSING" if complete else "FAILED",
                },
            )
            if not complete:
                return True
        if run["attempts"] >= min(4, 2 * (run["continuations"] + 1)):
            execute(
                c,
                """
                UPDATE runs SET state='FAILED',failure='model_attempt_limit',
                    lease_until=NULL WHERE id=:r
                """,
                {"r": run["id"]},
            )
            event(c, run, "FAILED", {"reason": "model_attempt_limit"})
            return True
        sources = rows(
            c,
            "SELECT id,content FROM content_nodes WHERE run_id=:r AND expires_at>now()",
            {"r": run["id"]},
        )
        execute(
            c, "UPDATE runs SET state='PROPOSING',attempts=attempts+1 WHERE id=:r", {"r": run["id"]}
        )
        event(
            c,
            run,
            "MODEL_REQUESTED",
            {"attempt": run["attempts"] + 1, "source_ids": [s["id"] for s in sources]},
        )
    claim.committed = True
    # No open transaction or database connection while waiting on inference.
    try:
        result = provider.analyze(
            InferenceRequest(
                envelope, {s["id"]: s["content"] for s in sources}, bool(run["continuations"])
            )
        )
    except ProviderError as error:
        with engine.begin() as c:
            current = result_run(c, run["id"], fence)
            if current is None or current["cancelled"] or current["state"] != "PROPOSING":
                return True
            retry = error.retryable and current["attempts"] < min(
                4, 2 * (current["continuations"] + 1)
            )
            delay = min(8, 2 ** int(current["attempts"]))
            execute(
                c,
                """
                UPDATE runs SET state=:s,failure=:error,
                    lease_until=CASE
                        WHEN CAST(:retry AS boolean)
                        THEN now() + make_interval(secs => :delay)
                        ELSE NULL
                    END
                WHERE id=:r
                """,
                {
                    "s": "PROPOSING" if retry else "FAILED",
                    "error": error.code,
                    "retry": retry,
                    "delay": delay,
                    "r": run["id"],
                },
            )
            event(
                c,
                current,
                "MODEL_FAILED" if retry else "FAILED",
                {
                    "reason": error.code,
                    "retry_scheduled": retry,
                    "retry_after_seconds": delay if retry else 0,
                },
            )
            logger.warning(
                "provider_failed run_id=%s reason=%s retry=%s",
                run["id"],
                error.code,
                retry,
            )
        return True
    with engine.begin() as c:
        current = result_run(c, run["id"], fence)
        if current is None or current["cancelled"] or current["state"] != "PROPOSING":
            return True
        analysis = result.analysis
        # Every model-produced reference is validated before anything is persisted. A
        # failure raises inside this transaction, so no finding, analysis, action, or
        # decision from the rejected result survives, and nothing reaches the guard.
        if analysis.proposal is not None:
            validate_proposal_evidence(c, run, analysis.proposal)
        offsets = validated_finding_offsets(
            c, run, analysis, {s["id"]: s["content"] for s in sources}
        )
        producer = producer_provenance(run["id"], result) if analysis.proposal is not None else None
        metadata = asdict(result)
        metadata.pop("analysis")
        event(c, current, "MODEL_COMPLETED", metadata)
        for finding, start in zip(analysis.findings, offsets, strict=True):
            execute(
                c,
                """
                INSERT INTO findings(
                    id,workspace_id,run_id,node_id,origin,family,explanation,
                    start_offset,end_offset,version
                ) VALUES(
                    :id,:w,:r,:n,'model',:family,:explanation,
                    :start,:end,:version
                )
                """,
                {
                    "id": uid(),
                    "w": run["workspace_id"],
                    "r": run["id"],
                    "n": str(finding.evidence_id),
                    "family": finding.family,
                    "explanation": finding.explanation,
                    "start": start,
                    "end": start + len(finding.quote),
                    "version": result.prompt_version,
                },
            )
        execute(
            c,
            """
            UPDATE runs SET analysis=CAST(:a AS jsonb),
                uncertain=uncertain OR :u,failure=NULL WHERE id=:r
            """,
            {
                "a": json.dumps({"summary": analysis.summary, **metadata}),
                "u": analysis.uncertain or bool(analysis.findings),
                "r": run["id"],
            },
        )
        if analysis.proposal is None:
            execute(
                c,
                "UPDATE runs SET state='NO_ACTION',lease_until=NULL WHERE id=:r",
                {"r": run["id"]},
            )
            event(c, current, "NO_ACTION", {})
        else:
            if producer is None:
                raise DomainError("lineage_write_failure")
            try:
                execute(
                    c,
                    """
                    INSERT INTO actions(
                        id,workspace_id,run_id,proposal,digest,
                        producer_provider,producer_model,producer_prompt_version,
                        producer_response_id
                    ) VALUES(
                        :id,:w,:r,CAST(:p AS jsonb),:d,
                        :provider,:model,:prompt_version,:response_id
                    )
                    """,
                    {
                        "id": uid(),
                        "w": run["workspace_id"],
                        "r": run["id"],
                        "p": analysis.proposal.model_dump_json(),
                        "d": action_digest(run["id"], envelope, analysis.proposal),
                        **producer,
                    },
                )
            except DBAPIError as error:
                # The application validated the producer trio first. A database producer
                # check that still rejects it is a required-lineage failure. Anything else
                # about this insert keeps its general classification.
                if is_lineage_integrity_failure(error, PRODUCER_WRITE):
                    raise DomainError("lineage_write_failure") from None
                raise
            execute(
                c,
                """
                UPDATE runs SET proposals=proposals+1,state='AUTHORIZING',
                    lease_until=NULL WHERE id=:r
                """,
                {"r": run["id"]},
            )
            event(c, current, "ACTION_PROPOSED", {"tool": analysis.proposal.tool})
    return True


def tick(engine: Engine, provider: Provider) -> bool:
    claim = Claim()
    try:
        return advance(engine, provider, claim)
    except DomainError as error:
        if error.code in {"not_found", "stale_worker"}:
            logger.warning("worker_skipped run_id=%s reason=%s", claim.run_id, error.code)
            return False
        logger.warning("worker_fail_closed run_id=%s reason=%s", claim.run_id, error.code)
        return quarantine(engine, claim, error.code)
    except Exception:
        logger.exception("worker_unhandled run_id=%s", claim.run_id)
        try:
            return quarantine(engine, claim, "worker_failure")
        except Exception:
            logger.exception("worker_quarantine_failed run_id=%s", claim.run_id)
            raise


def run_worker(
    engine: Engine,
    provider: Provider,
    *,
    once: bool = False,
    stop: Event | None = None,
) -> None:
    """Process claimed runs until idle, once, or shutdown. In-flight work finishes first."""
    pause = stop if stop is not None else Event()
    delay = 1.0
    while not pause.is_set():
        try:
            progressed = tick(engine, provider)
        except Exception:
            logger.exception("worker_tick_failed")
            if once or pause.wait(delay):
                if once:
                    raise
                return
            delay = min(5.0, delay * 2)
            continue
        delay = 1.0
        if once or (not progressed and pause.wait(1.0)):
            return
