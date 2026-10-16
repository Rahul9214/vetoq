"""Authenticated, typed, read-only lineage routes.

Each route resolves the run through the one canonical visibility rule inside the Slice D read
service, then projects the assembled result. The routes decide nothing about lineage meaning,
accept no bound or depth from a caller, write nothing, and are never an input to
authorization. A node or action id selects within the trusted run and nothing else, and every
refusal is the same non-enumerating `404 not_found`.
"""

from time import perf_counter

from fastapi import APIRouter, Request, Response

from vetoq import lineage_observe, lineage_views
from vetoq.auth import correlation
from vetoq.lineage_model import DEFAULT_BOUNDS, LineageBounds, RunLineage
from vetoq.lineage_read import build_run_lineage
from vetoq.lineage_views import ActionLineageView, Direction, NodeLineageView
from vetoq.routes import Principal, engine, fail
from vetoq.workflow import DomainError

router = APIRouter(prefix="/api/v1")

# The server owns every bound. No route parameter can raise, lower, or disable them.
SERVER_BOUNDS: LineageBounds = DEFAULT_BOUNDS


def _read(request: Request, response: Response, actor: str, run_id: str) -> RunLineage:
    response.headers["Cache-Control"] = "no-store"
    try:
        return build_run_lineage(engine(request), actor, run_id, SERVER_BOUNDS)
    except DomainError as error:
        fail(error)


def _completed(
    request: Request, kind: str, run_id: str, started: float, lineage: RunLineage
) -> None:
    lineage_observe.read_completed(
        correlation_id=correlation(request),
        kind=kind,
        run_id=run_id,
        duration_ms=int((perf_counter() - started) * 1000),
        lineage=lineage,
    )


@router.get("/runs/{run_id}/lineage", response_model=RunLineage)
def get_run_lineage(
    run_id: str, actor: Principal, request: Request, response: Response
) -> RunLineage:
    started = perf_counter()
    lineage = lineage_views.canonical(_read(request, response, actor, run_id))
    _completed(request, "run", run_id, started, lineage)
    return lineage


@router.get("/runs/{run_id}/lineage/nodes/{node_id}", response_model=NodeLineageView)
def get_node_lineage(
    run_id: str,
    node_id: str,
    actor: Principal,
    request: Request,
    response: Response,
    direction: Direction = "both",
) -> NodeLineageView:
    started = perf_counter()
    lineage = _read(request, response, actor, run_id)
    try:
        view = lineage_views.node_view(lineage, node_id, direction, SERVER_BOUNDS)
    except DomainError as error:
        fail(error)
    _completed(request, "node", run_id, started, lineage)
    return view


@router.get("/runs/{run_id}/lineage/actions/{action_id}", response_model=ActionLineageView)
def get_action_lineage(
    run_id: str, action_id: str, actor: Principal, request: Request, response: Response
) -> ActionLineageView:
    started = perf_counter()
    lineage = _read(request, response, actor, run_id)
    try:
        view = lineage_views.action_view(lineage, action_id)
    except DomainError as error:
        fail(error)
    _completed(request, "action", run_id, started, lineage)
    return view
