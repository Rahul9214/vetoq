"""Authenticated, workspace-scoped Module 002 HTTP API."""

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import Engine

from vetoq.auth import principal
from vetoq.contracts import TERMINAL, ReviewDecision, Submission
from vetoq.db import execute, one, rows
from vetoq.workflow import DomainError, event, locked_run, now, submit

router = APIRouter(prefix="/api/v1")
Principal = Annotated[str, Depends(principal)]


def engine(request: Request) -> Engine:
    configured = request.app.state.engine
    if configured is None:
        raise HTTPException(503, "database_not_configured")
    return cast(Engine, configured)


def fail(error: DomainError) -> None:
    raise HTTPException(error.status, error.code) from None


def visible_run(connection: Any, run_id: str, actor: str) -> dict[str, Any]:
    run = one(
        connection,
        """
        SELECT r.* FROM runs r
        JOIN memberships m ON m.workspace_id=r.workspace_id
        WHERE r.id=:id AND m.principal=:principal AND m.active
        """,
        {"id": run_id, "principal": actor},
    )
    if run is None:
        raise DomainError("not_found", 404)
    return run


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
    try:
        run_id = submit(engine(request), actor, body, idempotency_key)
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
        findings = rows(
            connection,
            """
            SELECT f.id,f.origin,f.family,f.explanation,f.start_offset,f.end_offset,
                   f.node_id,f.version
            FROM findings f WHERE f.run_id=:run ORDER BY f.origin,f.id
            """,
            {"run": run_id},
        )
        action = one(
            connection,
            """
            SELECT id,proposal,digest,verdict,reasons,created_at
            FROM actions WHERE run_id=:run ORDER BY created_at DESC,id DESC LIMIT 1
            """,
            {"run": run_id},
        )
        review = (
            one(
                connection,
                """
                SELECT id,digest,expires_at,decision,consumed
                FROM reviews WHERE action_id=:action
                """,
                {"action": action["id"]},
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
            WHERE t.run_id=:run
            """,
            {"run": run_id},
        )
        sources = rows(
            connection,
            """
            SELECT id,origin,supplier,digest,trust,complete,created_at,expires_at
            FROM content_nodes WHERE run_id=:run ORDER BY created_at,id
            """,
            {"run": run_id},
        )
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
            visible_run(connection, run_id, actor)
        except DomainError as error:
            fail(error)
        items = rows(
            connection,
            """
            SELECT sequence,actor,type,detail,created_at FROM audit_events
            WHERE run_id=:run AND sequence>:after ORDER BY sequence LIMIT 100
            """,
            {"run": run_id, "after": max(0, after)},
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
            visible_run(connection, run_id, actor)
        except DomainError as error:
            fail(error)
        item = one(
            connection,
            """
            SELECT id,origin,supplier,digest,content,trust,complete,expires_at
            FROM content_nodes WHERE run_id=:run AND id=:node
            """,
            {"run": run_id, "node": node_id},
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
                    UPDATE reviews SET decision=:decision,reviewer=:reviewer WHERE id=:review
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
        ticket = one(
            connection,
            """
            SELECT t.id,t.workspace_id,t.run_id,t.title,t.body,t.created_at,e.verified_at
            FROM tickets t
            JOIN memberships m ON m.workspace_id=t.workspace_id
            LEFT JOIN executions e ON e.ticket_id=t.id
            WHERE t.id=:ticket AND m.principal=:principal AND m.active
            """,
            {"ticket": ticket_id, "principal": actor},
        )
    if ticket is None:
        raise HTTPException(404, "not_found")
    return ticket
