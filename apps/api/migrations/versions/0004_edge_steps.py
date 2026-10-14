"""Ordered transform steps for one content edge.

Historical edges keep transform_step_count NULL. That means the chain was
not recorded. This revision does not backfill a step from the edge summary.
"""

from alembic import op

revision = "0004_edge_steps"
down_revision = "0003_secure_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE content_edges
          ADD COLUMN transform_step_count smallint
        """
    )
    op.execute(
        """
        ALTER TABLE content_edges
          ADD CONSTRAINT content_edge_step_count CHECK (
            transform_step_count IS NULL
            OR transform_step_count BETWEEN 1 AND 4
          )
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN content_edges.transform_step_count IS
          'NULL means the chain was not recorded. '
          '1..4 is the exact step-row count. Not the edge summary.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN content_edges.transform IS
          'Summary name of the whole parent-to-child derivation. Not defined as the last step.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN content_edges.version IS
          'Version of the summary transform. Not defined as the last step version.'
        """
    )
    op.execute(
        """
        CREATE TABLE content_edge_steps (
          edge_id text NOT NULL,
          step_index integer NOT NULL,
          transform text NOT NULL,
          version text NOT NULL,
          PRIMARY KEY (edge_id, step_index),
          FOREIGN KEY (edge_id) REFERENCES content_edges(id) ON DELETE CASCADE,
          CONSTRAINT content_edge_step_index CHECK (step_index BETWEEN 1 AND 4),
          CONSTRAINT content_edge_step_transform CHECK (
            transform = btrim(transform) AND char_length(transform) BETWEEN 1 AND 80
          ),
          CONSTRAINT content_edge_step_version CHECK (
            version = btrim(version) AND char_length(version) BETWEEN 1 AND 80
          )
        )
        """
    )
    op.execute(
        """
        COMMENT ON TABLE content_edge_steps IS
          'Ordered interpretation history for one edge. Not authority.'
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_edge() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable_edge';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_edge
        BEFORE UPDATE ON content_edges
        FOR EACH ROW EXECUTE FUNCTION protect_edge()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_edge_step() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable_edge_step';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_edge_step
        BEFORE UPDATE ON content_edge_steps
        FOR EACH ROW EXECUTE FUNCTION protect_edge_step()
        """
    )
    # Deferred so a chain can be inserted, and so node/edge cascade deletes
    # are not rejected while their steps are still being removed.
    op.execute(
        """
        CREATE FUNCTION enforce_recorded_edge_steps() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          target text;
          recorded smallint;
          actual integer;
          low integer;
          high integer;
        BEGIN
          IF TG_TABLE_NAME = 'content_edges' THEN
            IF TG_OP = 'DELETE' THEN
              RETURN NULL;
            END IF;
            target := NEW.id;
          ELSIF TG_OP = 'DELETE' THEN
            target := OLD.edge_id;
          ELSE
            target := NEW.edge_id;
          END IF;

          SELECT transform_step_count INTO recorded
          FROM content_edges WHERE id = target;
          IF NOT FOUND THEN
            RETURN NULL;
          END IF;

          SELECT count(*)::integer, min(step_index), max(step_index)
            INTO actual, low, high
          FROM content_edge_steps
          WHERE edge_id = target;

          IF recorded IS NULL THEN
            IF actual <> 0 THEN
              RAISE EXCEPTION 'edge_steps_incomplete';
            END IF;
            RETURN NULL;
          END IF;

          IF actual <> recorded OR low IS DISTINCT FROM 1 OR high IS DISTINCT FROM recorded THEN
            RAISE EXCEPTION 'edge_steps_incomplete';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER content_edges_steps_complete
        AFTER INSERT ON content_edges
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_recorded_edge_steps()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER content_edge_steps_complete
        AFTER INSERT OR DELETE ON content_edge_steps
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_recorded_edge_steps()
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
