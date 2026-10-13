"""Indexes for the worker claim scan and unresolved-review expiry."""

from alembic import op

revision = "0002_worker_claim"
down_revision = "0001_security_slice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Eligible runs are a small non-terminal subset ordered by age. The state-leading
    # runnable index cannot return that mixed set in created_at order without a sort.
    op.execute(
        """
        CREATE INDEX runs_claimable ON runs (created_at)
        WHERE state IN (
            'QUEUED','PROPOSING','AUTHORIZING','VERIFYING','AWAITING_REVIEW'
        )
        """
    )
    # Expired open reviews are selected by run and expiry, not by action id.
    op.execute(
        """
        CREATE INDEX reviews_unresolved_expiry ON reviews (run_id, expires_at)
        WHERE decision IS NULL
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
