"""M004 Slice F1: run-scoped lookup index for lineage executions reads.

The lineage reader loads executions with:

    WHERE workspace_id=:workspace AND run_id=:run
    ORDER BY committed_at, id LIMIT :limit

Primary key and unique action/ticket indexes cannot serve that filter. This revision
adds only `executions_workspace_run_idx` on `(workspace_id, run_id)`. It changes no
row, constraint, foreign key, trigger, or lineage meaning. The Action Guard does not
read it.

The two-column index is the approved filter path. `committed_at` and `id` stay out of
the index: they are the sort, not the tenant/run predicate.
"""

from alembic import op

revision = "0007_lineage_execution_lookup"
down_revision = "0006_lineage_enforcement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX executions_workspace_run_idx
          ON executions (workspace_id, run_id)
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
