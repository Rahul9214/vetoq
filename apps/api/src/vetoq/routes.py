"""Authenticated, workspace-scoped HTTP API."""

from datetime import datetime
from typing import Annotated, Any, NoReturn, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import Connection, Engine

from vetoq.auth import principal
from vetoq.contracts import POLICY, TERMINAL, DeclaredSubmission, ReviewDecision, Submission
from vetoq.db import execute, one, rows
from vetoq.ingestion.contracts import TransformStep, recorded_transform_steps
from vetoq.visibility import visible_run
from vetoq.workflow import (
    DomainError,
    accept_declared_submission,
    event,
    locked_run,
    now,
)

router = APIRouter(prefix="/api/v1")
Principal = Annotated[str, Depends(principal)]


def engine(request: Request) -> Engine:
    configured = request.app.state.engine
    if configured is None:
        raise HTTPException(503, "database_not_configured")
    return cast(Engine, configured)


def run_edges(connection: Connection, workspace_id: str, run_id: str) -> list[dict[str, Any]]:
    """Return summary edges plus the recorded step chain.

    A null ``transform_step_count`` stays ``transform_steps: null``. The
    summary transform is not copied into that list.
    """

    records = rows(
        connection,
        """
        SELECT e.id, e.parent_id, e.child_id, e.transform, e.version, e.lossy,
               e.transform_step_count, s.step_index,
               s.transform AS step_transform, s.version AS step_version
        FROM content_edges e
        LEFT JOIN content_edge_steps s ON s.edge_id = e.id
        WHERE e.workspace_id = :workspace AND e.run_id = :run
        ORDER BY e.parent_id, e.child_id, s.step_index
        """,
        {"workspace": workspace_id, "run": run_id},
    )
    ordered: list[str] = []
    grouped: dict[str, dict[str, Any]] = {}
    collected: dict[str, list[TransformStep]] = {}
    for record in records:
        edge_id = str(record["id"])
        if edge_id not in grouped:
            ordered.append(edge_id)
            grouped[edge_id] = {
                "parent_id": record["parent_id"],
                "child_id": record["child_id"],
                "transform": record["transform"],
                "version": record["version"],
                "lossy": record["lossy"],
                "_count": record["transform_step_count"],
            }
            collected[edge_id] = []
        if record["step_index"] is None:
            continue
        collected[edge_id].append(
            TransformStep(str(record["step_transform"]), str(record["step_version"]))
        )
    edges: list[dict[str, Any]] = []
    for edge_id in ordered:
        payload = grouped[edge_id]
        count = payload.pop("_count")
        recorded = recorded_transform_steps(
            None if count is None else int(count),
            collected[edge_id],
        )
        payload["transform_steps"] = (
            None
            if recorded is None
            else [{"transform": step.transform, "version": step.version} for step in recorded]
        )
        edges.append(payload)
    return edges


def fail(error: DomainError) -> NoReturn:
    raise HTTPException(error.status, error.code) from None


@router.get("/me")
def me(actor: Principal, request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        memberships = [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "role": str(row["role"]),
                "policy_revision": str(row["policy_revision"]),
            }
            for row in rows(
                connection,
                """
                SELECT w.id,w.name,m.role,w.policy_revision
                FROM memberships m JOIN workspaces w ON w.id=m.workspace_id
                WHERE m.principal=:principal AND m.active AND w.active
                ORDER BY w.name
                """,
                {"principal": actor},
            )
        ]
    return {
        "principal": actor,
        "access": "active" if memberships else "not_provisioned",
        "workspaces": memberships,
        "template": {
            "id": "support-triage/1",
            "tool": "tickets.create",
            "destination": "local-ticket-store",
            "max_writes": 1,
            "expires_minutes": 30,
        },
    }


@router.post("/runs", status_code=202)
def create_run(
    body: Submission,
    actor: Principal,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", max_length=128)],
) -> dict[str, str]:
    declared = DeclaredSubmission(
        workspace_id=body.workspace_id,
        template=POLICY,
        goal=body.goal,
        source=body.source,
        media_type=body.media_type,
        confirmed=True,
    )
    try:
        run_id = accept_declared_submission(engine(request), actor, declared, idempotency_key)
    except DomainError as error:
        fail(error)
    return {"id": run_id}


@router.get("/runs")
def list_runs(
    actor: Principal,
    request: Request,
    workspace_id: str,
    before: datetime | None = None,
) -> dict[str, Any]:
    with engine(request).connect() as connection:
        membership = one(
            connection,
            """
            SELECT 1 FROM memberships m JOIN workspaces w ON w.id=m.workspace_id
            WHERE m.workspace_id=:workspace AND m.principal=:principal
              AND m.active AND w.active
            """,
            {"workspace": workspace_id, "principal": actor},
        )
        if membership is None:
            raise HTTPException(404, "not_found")
        items = rows(
            connection,
            """
            SELECT id,state,created_at,expires_at,writes,proposals,failure,
                   envelope->>'goal' AS goal
            FROM runs
            WHERE workspace_id=:workspace
              AND (CAST(:before AS timestamptz) IS NULL
                   OR created_at < CAST(:before AS timestamptz))
            ORDER BY created_at DESC LIMIT 25
            """,
            {"workspace": workspace_id, "before": before},
        )
    cursor = items[-1]["created_at"].isoformat() if len(items) == 25 else None
    return {"items": items, "next_cursor": cursor}


@router.get("/runs/{run_id}")
def get_run(run_id: str, actor: Principal, request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        try:
            run = visible_run(connection, run_id, actor)
        except DomainError as error:
            fail(error)
        # The visible run is the trusted scope. Its workspace and id qualify every query.
        scope = {"workspace": run["workspace_id"], "run": run["id"]}
        findings = rows(
            connection,
            """
            SELECT f.id,f.origin,f.family,f.explanation,f.start_offset,f.end_offset,
                   f.node_id,f.version
            FROM findings f
            WHERE f.workspace_id=:workspace AND f.run_id=:run ORDER BY f.origin,f.id
            """,
            scope,
        )
        action = one(
            connection,
            """
            SELECT id,proposal,digest,verdict,reasons,created_at
            FROM actions WHERE workspace_id=:workspace AND run_id=:run
            ORDER BY created_at DESC,id DESC LIMIT 1
            """,
            scope,
        )
        review = (
            one(
                connection,
                """
                SELECT id,digest,expires_at,decision,consumed
                FROM reviews
                WHERE workspace_id=:workspace AND run_id=:run AND action_id=:action
                """,
                {**scope, "action": action["id"]},
            )
            if action
            else None
        )
        actor_membership = one(
            connection,
            """
            SELECT role,active FROM memberships
            WHERE workspace_id=:workspace AND principal=:principal
            """,
            {"workspace": run["workspace_id"], "principal": actor},
        )
        ticket = one(
            connection,
            """
            SELECT t.id,t.title,t.created_at,e.verified_at
            FROM tickets t LEFT JOIN executions e ON e.ticket_id=t.id
            WHERE t.workspace_id=:workspace AND t.run_id=:run
            """,
            scope,
        )
        sources = rows(
            connection,
            """
            SELECT id,origin,supplier,digest,trust,complete,created_at,expires_at,
                   declared_media_type,representation_kind,charset,byte_size,
                   parser_id,parser_version
            FROM content_nodes WHERE workspace_id=:workspace AND run_id=:run
            ORDER BY created_at,id
            """,
            scope,
        )
        edges = run_edges(connection, str(run["workspace_id"]), str(run["id"]))
    return {
        "id": run["id"],
        "workspace_id": run["workspace_id"],
        "state": run["state"],
        "created_at": run["created_at"],
        "expires_at": run["expires_at"],
        "goal_lock": run["envelope"],
        "analysis": run["analysis"],
        "failure": run["failure"],
        "findings": findings,
        "action": action,
        "review": (
            {
                **review,
                "eligible": bool(
                    review["decision"] is None
                    and not review["consumed"]
                    and review["expires_at"] > now()
                    and actor != run["principal"]
                    and actor_membership
                    and actor_membership["active"]
                    and actor_membership["role"] == "reviewer"
                ),
            }
            if review
            else None
        ),
        "ticket": ticket,
        "sources": sources,
        "edges": edges,
    }


@router.get("/runs/{run_id}/events")
def get_events(
    run_id: str,
    actor: Principal,
    request: Request,
    after: int = 0,
) -> dict[str, Any]:
    with engine(request).connect() as connection:
        try:
            run = visible_run(connection, run_id, actor)
        except DomainError as error:
            fail(error)
        items = rows(
            connection,
            """
            SELECT sequence,actor,type,detail,created_at FROM audit_events
            WHERE workspace_id=:workspace AND run_id=:run AND sequence>:after
            ORDER BY sequence LIMIT 100
            """,
            {"workspace": run["workspace_id"], "run": run["id"], "after": max(0, after)},
        )
    return {"items": items, "next_cursor": items[-1]["sequence"] if items else after}


@router.get("/runs/{run_id}/content/{node_id}")
def get_content(
    run_id: str,
    node_id: str,
    actor: Principal,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    with engine(request).connect() as connection:
        try:
            run = visible_run(connection, run_id, actor)
        except DomainError as error:
            fail(error)
        item = one(
            connection,
            """
            SELECT id,origin,supplier,digest,content,trust,complete,expires_at,
                   declared_media_type,representation_kind,charset,byte_size,
                   parser_id,parser_version
            FROM content_nodes WHERE workspace_id=:workspace AND run_id=:run AND id=:node
            """,
            {"workspace": run["workspace_id"], "run": run["id"], "node": node_id},
        )
        if item is None:
            raise HTTPException(404, "not_found")
        if item["expires_at"] <= now():
            raise HTTPException(410, "content_expired")
    return item


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str, actor: Principal, request: Request) -> dict[str, str]:
    state = ""
    try:
        with engine(request).begin() as connection:
            run = locked_run(connection, run_id)
            if run["principal"] != actor:
                raise DomainError("not_found", 404)
            state = str(run["state"])
            if state not in TERMINAL:
                execute(
                    connection,
                    """
                    UPDATE runs SET cancelled=true,state='CANCELLED',lease_until=NULL
                    WHERE id=:run
                    """,
                    {"run": run_id},
                )
                event(connection, run, "CANCELLED", {}, actor)
                state = "CANCELLED"
    except DomainError as error:
        fail(error)
    return {"state": state}


@router.post("/reviews/{review_id}/decision")
def decide_review(
    review_id: str,
    body: ReviewDecision,
    actor: Principal,
    request: Request,
) -> dict[str, str]:
    prohibited = False
    try:
        with engine(request).begin() as connection:
            reference = one(
                connection,
                "SELECT run_id FROM reviews WHERE id=:review",
                {"review": review_id},
            )
            if reference is None:
                raise DomainError("not_found", 404)
            run = locked_run(connection, reference["run_id"])
            membership = one(
                connection,
                """
                SELECT * FROM memberships
                WHERE workspace_id=:workspace AND principal=:principal FOR UPDATE
                """,
                {"workspace": run["workspace_id"], "principal": actor},
            )
            review = one(
                connection,
                "SELECT * FROM reviews WHERE id=:review FOR UPDATE",
                {"review": review_id},
            )
            if (
                not membership
                or not membership["active"]
                or membership["role"] != "reviewer"
                or review is None
            ):
                raise DomainError("not_found", 404)
            if actor == run["principal"]:
                event(
                    connection,
                    run,
                    "SELF_REVIEW_PROHIBITED",
                    {"review_id": review_id, "reason": "self_review_prohibited"},
                    actor,
                )
                prohibited = True
            elif (
                review["decision"] is not None
                or review["consumed"]
                or review["expires_at"] <= now()
                or review["digest"] != body.digest
                or run["state"] != "AWAITING_REVIEW"
            ):
                raise DomainError("review_stale", 409)
            else:
                execute(
                    connection,
                    """
                    UPDATE reviews SET decision=:decision,reviewer=:reviewer,decided_at=now()
                    WHERE id=:review
                    """,
                    {"decision": body.decision, "reviewer": actor, "review": review_id},
                )
                state = "AUTHORIZING" if body.decision == "approve" else "BLOCKED"
                execute(
                    connection,
                    "UPDATE runs SET state=:state,lease_until=NULL WHERE id=:run",
                    {"state": state, "run": run["id"]},
                )
                event(
                    connection,
                    run,
                    "REVIEW_DECIDED",
                    {"review_id": review_id, "decision": body.decision},
                    actor,
                )
    except DomainError as error:
        fail(error)
    if prohibited:
        fail(DomainError("self_review_prohibited", 403))
    return {"state": state}


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, actor: Principal, request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        # A ticket is read through the run it belongs to, by the one canonical rule. There is
        # no separate membership-only path, and every refusal is the same 404.
        reference = one(
            connection, "SELECT run_id FROM tickets WHERE id=:ticket", {"ticket": ticket_id}
        )
        if reference is None:
            raise HTTPException(404, "not_found")
        try:
            run = visible_run(connection, str(reference["run_id"]), actor)
        except DomainError as error:
            fail(error)
        ticket = one(
            connection,
            """
            SELECT t.id,t.workspace_id,t.run_id,t.title,t.body,t.created_at,e.verified_at
            FROM tickets t
            LEFT JOIN executions e ON e.ticket_id=t.id
            WHERE t.id=:ticket AND t.workspace_id=:workspace AND t.run_id=:run
            """,
            {"ticket": ticket_id, "workspace": run["workspace_id"], "run": run["id"]},
        )
    if ticket is None:
        raise HTTPException(404, "not_found")
    return ticket
