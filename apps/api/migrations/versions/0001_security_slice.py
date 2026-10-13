"""Module 002: eleven business tables and database security constraints."""

from alembic import op

from vetoq.schema import DDL

revision = "0001_security_slice"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(DDL)


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
