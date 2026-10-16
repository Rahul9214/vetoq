"""The one canonical read-visibility rule for runs and everything scoped to a run.

A principal may read a run only with an active membership in the run's workspace, in an
active workspace. Every other case, including a missing run, a foreign workspace, an
inactive membership, and an inactive workspace, is the same non-enumerating `not_found`.

The client supplies a run id as a selector and nothing else. The returned row is the
trusted persisted run. Every later read of run-scoped data must use that row's
`workspace_id` and `id`, never an identifier supplied by the client.

This helper is for reads. The mutation routes (`decide_review`, `cancel`) keep their own
recorded checks.
"""

from typing import Any

from sqlalchemy import Connection

from vetoq.db import one
from vetoq.workflow import DomainError


def visible_run(connection: Connection, run_id: str, principal: str) -> dict[str, Any]:
    run = one(
        connection,
        """
        SELECT r.* FROM runs r
        JOIN workspaces w ON w.id=r.workspace_id
        JOIN memberships m ON m.workspace_id=r.workspace_id
        WHERE r.id=:id AND m.principal=:principal AND m.active AND w.active
        """,
        {"id": run_id, "principal": principal},
    )
    if run is None:
        raise DomainError("not_found", 404)
    return run
