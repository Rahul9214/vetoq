"""M004 Slice C2: strict database enforcement of the lineage rules the writers satisfy.

`0005_provenance_lineage` was tolerant on purpose: every new column was nullable and no
rule required a link. The runtime writers added in Slice C1 now set every one of those
facts, so this revision makes PostgreSQL enforce them for NEW rows.

Historical truth is preserved. Nothing here backfills, rewrites, or deletes a row, and
no column becomes NOT NULL. A row that predates this revision keeps its NULLs forever,
including an in-flight review or execution that is still legitimately completed by the
current writer. The rules are INSERT-time rules and transition rules. They never demand
that an old row become historically complete.

What this revision enforces:

* `workspaces.policy_revision` is trimmed and 1 to 80 characters, the shape that
  `guard_decisions.policy_revision_observed` already requires, so a malformed source
  value is rejected where it is written and never turns a normal guard decision into a
  lineage persistence failure. The value is not changed.
* A new review carries `requested_at`, and by commit has the REVIEW guard decision that
  references it.
* A review decision, and a review consumption, are one-way transitions that record their
  own timestamp. A decided or consumed review cannot change again.
* A new execution carries the link to the exact ALLOW decision that authorized it. The
  link no longer cascades from the decision, so deleting a decision can never erase
  execution history. The foreign key is deferred, so a parent run or action cascade that
  removes both rows in one transaction still succeeds.
* A new action carries the producer provider, model, and prompt version. A response id
  never exists without them. The response id stays optional.
* A guard decision for an action that has a review carries that exact review.

Lineage describes what happened and is never an authorization input. Nothing here is read
by the Action Guard, `authorize()`, or any model call.
"""

from alembic import op

revision = "0006_lineage_enforcement"
down_revision = "0005_provenance_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _workspace_policy_revision_shape()
    _review_requested_at_and_decision()
    _review_transitions()
    _execution_link()
    _action_producer()
    _decision_review_link()


def _workspace_policy_revision_shape() -> None:
    # The same shape guard_decisions.policy_revision_observed requires. It is validated
    # against existing rows, so an incompatible historical value stops the migration
    # instead of being rewritten. The operator preflight reports such a value first.
    op.execute(
        """
        ALTER TABLE workspaces
          ADD CONSTRAINT workspaces_policy_revision_shape CHECK (
            policy_revision = btrim(policy_revision)
            AND char_length(policy_revision) BETWEEN 1 AND 80
          )
        """
    )


def _review_requested_at_and_decision() -> None:
    # Not a NOT NULL column: a historical review has no request time and stays truthful.
    op.execute(
        """
        CREATE FUNCTION require_review_requested_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.requested_at IS NULL THEN
            RAISE EXCEPTION 'review_requested_at_required';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER review_requested_at_required
        BEFORE INSERT ON reviews
        FOR EACH ROW EXECUTE FUNCTION require_review_requested_at()
        """
    )
    # Deferred, because the writer inserts the review first and its REVIEW decision second
    # in one transaction. Only a review inserted in the committing transaction is checked.
    # A review removed in the same transaction (a run or action cascade) is skipped.
    op.execute(
        """
        CREATE FUNCTION enforce_review_has_review_decision() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM reviews WHERE id = NEW.id) THEN
            RETURN NULL;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM guard_decisions
            WHERE workspace_id = NEW.workspace_id
              AND run_id = NEW.run_id
              AND action_id = NEW.action_id
              AND review_id = NEW.id
              AND verdict = 'REVIEW'
          ) THEN
            RAISE EXCEPTION 'review_without_review_decision';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER review_has_review_decision
        AFTER INSERT ON reviews
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_review_has_review_decision()
        """
    )


def _review_transitions() -> None:
    # Identity, digest, expiry, and the request time stay frozen. The decision and the
    # consumption are each a one-way transition that must record its own timestamp.
    # Nothing here requires an old row to already carry requested_at or decided_at:
    # a historical review may be decided or consumed by the current writer, and only the
    # new transition is checked.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_review() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.id <> OLD.id OR NEW.workspace_id <> OLD.workspace_id
             OR NEW.run_id <> OLD.run_id OR NEW.action_id <> OLD.action_id
             OR NEW.digest <> OLD.digest OR NEW.expires_at <> OLD.expires_at
             OR NEW.requested_at IS DISTINCT FROM OLD.requested_at THEN
            RAISE EXCEPTION 'immutable_review';
          END IF;

          IF OLD.decision IS NULL THEN
            IF NOT (
              (NEW.decision IS NULL AND NEW.reviewer IS NULL AND NEW.decided_at IS NULL)
              OR (
                NEW.decision IS NOT NULL
                AND NEW.reviewer IS NOT NULL
                AND NEW.decided_at IS NOT NULL
              )
            ) THEN
              RAISE EXCEPTION 'invalid_review_decision_transition';
            END IF;
          ELSIF NEW.decision IS DISTINCT FROM OLD.decision
             OR NEW.reviewer IS DISTINCT FROM OLD.reviewer
             OR NEW.decided_at IS DISTINCT FROM OLD.decided_at THEN
            RAISE EXCEPTION 'invalid_review_decision_transition';
          END IF;

          IF OLD.consumed THEN
            IF NEW.consumed IS DISTINCT FROM OLD.consumed
               OR NEW.consumed_at IS DISTINCT FROM OLD.consumed_at THEN
              RAISE EXCEPTION 'invalid_review_consumption_transition';
            END IF;
          ELSIF NEW.consumed THEN
            IF NEW.consumed_at IS NULL OR NEW.decision IS DISTINCT FROM 'approve' THEN
              RAISE EXCEPTION 'invalid_review_consumption_transition';
            END IF;
          ELSIF NEW.consumed_at IS NOT NULL THEN
            RAISE EXCEPTION 'invalid_review_consumption_transition';
          END IF;
          RETURN NEW;
        END $$
        """
    )


def _execution_link() -> None:
    # 0005 cascaded from the decision, which could erase execution history by deleting one
    # decision. NO ACTION refuses that. DEFERRABLE INITIALLY DEFERRED is required so a
    # run or action cascade, which deletes the execution and its decisions in one
    # transaction, does not fail on the order in which PostgreSQL removes them. The same
    # constraint name is kept so existing identities stay stable.
    op.execute("ALTER TABLE executions DROP CONSTRAINT executions_guard_decision_fk")
    op.execute(
        """
        ALTER TABLE executions
          ADD CONSTRAINT executions_guard_decision_fk
          FOREIGN KEY (workspace_id, run_id, action_id, guard_decision_id)
          REFERENCES guard_decisions (workspace_id, run_id, action_id, id)
          MATCH SIMPLE ON DELETE NO ACTION
          DEFERRABLE INITIALLY DEFERRED
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN executions.guard_decision_id IS
          'The authorizing ALLOW guard decision. Required for every execution inserted '
          'from revision 0006. NULL only on an execution that predates it, meaning not recorded.'
        """
    )
    # Same exactness as 0005 (same workspace, run, action, verdict ALLOW, same digest),
    # now with a required link. A missing link is a rejected insert, not a tolerated NULL.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_execution_authorization() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          decision guard_decisions%ROWTYPE;
        BEGIN
          IF NEW.guard_decision_id IS NULL THEN
            RAISE EXCEPTION 'execution_guard_decision_required';
          END IF;
          SELECT * INTO decision FROM guard_decisions
          WHERE workspace_id = NEW.workspace_id
            AND run_id = NEW.run_id
            AND action_id = NEW.action_id
            AND id = NEW.guard_decision_id;
          IF NOT FOUND OR decision.verdict <> 'ALLOW' OR decision.action_digest <> NEW.digest THEN
            RAISE EXCEPTION 'invalid_execution_guard_decision';
          END IF;
          RETURN NEW;
        END $$
        """
    )


def _action_producer() -> None:
    # An INSERT-time rule, not a column NOT NULL: a historical action keeps NULL. The
    # response id stays optional but cannot exist without the trio.
    op.execute(
        """
        CREATE FUNCTION require_action_producer() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.producer_provider IS NULL
             OR NEW.producer_model IS NULL
             OR NEW.producer_prompt_version IS NULL THEN
            RAISE EXCEPTION 'action_producer_required';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER action_producer_required
        BEFORE INSERT ON actions
        FOR EACH ROW EXECUTE FUNCTION require_action_producer()
        """
    )
    op.execute(
        """
        ALTER TABLE actions
          ADD CONSTRAINT action_producer_response_requires_trio CHECK (
            producer_response_id IS NULL
            OR (
              producer_provider IS NOT NULL
              AND producer_model IS NOT NULL
              AND producer_prompt_version IS NOT NULL
            )
          )
        """
    )


def _decision_review_link() -> None:
    # A decision for an action that has a review must carry that exact review. Straight
    # ALLOW and BLOCK decisions, where no review exists, carry none. The link is read from
    # the review row, never inferred from the ordinal.
    op.execute(
        """
        CREATE FUNCTION enforce_guard_decision_review_link() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          linked text;
        BEGIN
          SELECT id INTO linked FROM reviews
          WHERE workspace_id = NEW.workspace_id
            AND run_id = NEW.run_id
            AND action_id = NEW.action_id;
          IF FOUND AND NEW.review_id IS DISTINCT FROM linked THEN
            RAISE EXCEPTION 'guard_decision_review_link_required';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_decision_review_link_required
        BEFORE INSERT ON guard_decisions
        FOR EACH ROW EXECUTE FUNCTION enforce_guard_decision_review_link()
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
