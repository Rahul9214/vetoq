"""M004 Slice B: additive provenance and lineage structure with tolerant guards.

This revision adds the append-only `guard_decisions` table, review timestamp
columns, nullable action producer columns, the nullable execution
authorization link, immutability guards, action evidence validation, derived
node parent integrity, and lookup indexes.

It is deliberately tolerant. The Module 003 writers keep working unchanged:
no row is backfilled, every new column on an existing table is nullable, and
historical rows stay truthful through NULL. The strict review transition rules
and any "must already be linked" rules belong to a later revision that ships
only after compatible writers exist. Lineage describes what happened. Nothing
here is an authorization input.

Guard reason cardinality is 1..16. `guard()` returns exactly one of: a BLOCK
whose reasons list is non-empty (it is returned only under `if reasons:`), or
a REVIEW, BLOCK, or ALLOW whose reasons list is a one-element literal. The
largest list is eleven reasons, so no valid decision has zero reasons.

The evidence-id maximum below equals `BUDGETS.proposal_evidence_ids`. A test
reads this function definition and compares it with the runtime budget.
"""

from alembic import op

revision = "0005_provenance_lineage"
down_revision = "0004_edge_steps"
branch_labels = None
depends_on = None

UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def upgrade() -> None:
    _action_columns_and_keys()
    _review_columns_and_keys()
    _guard_decisions()
    _execution_link()
    _immutability_guards()
    _action_evidence_validation()
    _derived_node_parent_integrity()
    _indexes()


def _action_columns_and_keys() -> None:
    op.execute(
        """
        ALTER TABLE actions
          ADD COLUMN producer_provider text,
          ADD COLUMN producer_model text,
          ADD COLUMN producer_prompt_version text,
          ADD COLUMN producer_response_id text
        """
    )
    # Historical and in-flight rows keep NULL. The first three are all NULL or
    # all set; the response id is independent because a provider may omit it.
    op.execute(
        """
        ALTER TABLE actions
          ADD CONSTRAINT action_producer_triplet CHECK (
            (
              producer_provider IS NULL
              AND producer_model IS NULL
              AND producer_prompt_version IS NULL
            )
            OR (
              producer_provider IS NOT NULL
              AND producer_model IS NOT NULL
              AND producer_prompt_version IS NOT NULL
            )
          ),
          ADD CONSTRAINT action_producer_provider_length CHECK (
            producer_provider IS NULL OR (
              producer_provider = btrim(producer_provider)
              AND char_length(producer_provider) BETWEEN 1 AND 120
            )
          ),
          ADD CONSTRAINT action_producer_model_length CHECK (
            producer_model IS NULL OR (
              producer_model = btrim(producer_model)
              AND char_length(producer_model) BETWEEN 1 AND 120
            )
          ),
          ADD CONSTRAINT action_producer_prompt_version_length CHECK (
            producer_prompt_version IS NULL OR (
              producer_prompt_version = btrim(producer_prompt_version)
              AND char_length(producer_prompt_version) BETWEEN 1 AND 120
            )
          ),
          ADD CONSTRAINT action_producer_response_id_length CHECK (
            producer_response_id IS NULL OR (
              producer_response_id = btrim(producer_response_id)
              AND char_length(producer_response_id) BETWEEN 1 AND 200
            )
          )
        """
    )
    # Binds a guard decision to the exact immutable proposal digest.
    op.execute(
        """
        ALTER TABLE actions
          ADD CONSTRAINT actions_unique_digest_binding
          UNIQUE (workspace_id, run_id, id, digest)
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN actions.producer_provider IS
          'Provider that produced the proposal, set at insert only. NULL means not recorded.';
        COMMENT ON COLUMN actions.producer_model IS
          'Requested model identifier, not a verified served model. NULL means not recorded.';
        COMMENT ON COLUMN actions.producer_prompt_version IS
          'Prompt contract version at insert. NULL means not recorded.';
        COMMENT ON COLUMN actions.producer_response_id IS
          'Provider response id when one was returned. NULL means none or not recorded.';
        """
    )
    # Producer fields are insert-time evidence and stay outside the action
    # digest. verdict and reasons remain the mutable latest-evaluation cache.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_action() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.proposal IS DISTINCT FROM OLD.proposal OR NEW.digest <> OLD.digest
             OR NEW.run_id <> OLD.run_id OR NEW.workspace_id <> OLD.workspace_id
             OR NEW.producer_provider IS DISTINCT FROM OLD.producer_provider
             OR NEW.producer_model IS DISTINCT FROM OLD.producer_model
             OR NEW.producer_prompt_version IS DISTINCT FROM OLD.producer_prompt_version
             OR NEW.producer_response_id IS DISTINCT FROM OLD.producer_response_id THEN
            RAISE EXCEPTION 'immutable_action';
          END IF;
          RETURN NEW;
        END $$
        """
    )


def _review_columns_and_keys() -> None:
    op.execute(
        """
        ALTER TABLE reviews
          ADD COLUMN requested_at timestamptz,
          ADD COLUMN decided_at timestamptz,
          ADD COLUMN consumed_at timestamptz
        """
    )
    # Tolerant only. "decision implies decided_at" and "consumed implies
    # consumed_at" are not required until the writers set those timestamps.
    op.execute(
        """
        ALTER TABLE reviews
          ADD CONSTRAINT review_decided_at_requires_decision CHECK (
            decided_at IS NULL OR (decision IS NOT NULL AND reviewer IS NOT NULL)
          ),
          ADD CONSTRAINT review_consumed_at_requires_consumed CHECK (
            consumed_at IS NULL OR consumed = true
          )
        """
    )
    op.execute(
        """
        ALTER TABLE reviews
          ADD CONSTRAINT reviews_unique_action_review
          UNIQUE (workspace_id, run_id, action_id, id)
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN reviews.requested_at IS
          'Creation time of the review request. NULL on historical rows. Never backfilled.';
        COMMENT ON COLUMN reviews.decided_at IS
          'Time of the reviewer decision. NULL means not recorded.';
        COMMENT ON COLUMN reviews.consumed_at IS
          'Time the approval was consumed. NULL means not recorded.';
        """
    )


def _guard_decisions() -> None:
    # Used by a CHECK. It must return a non-NULL boolean because a CHECK treats
    # NULL as satisfied. Empty, NULL-element, and multi-dimension arrays fail.
    op.execute(
        """
        CREATE FUNCTION guard_reasons_valid(reasons text[]) RETURNS boolean
        LANGUAGE sql IMMUTABLE AS $$
          SELECT COALESCE(
            array_ndims(reasons) = 1
            AND cardinality(reasons) BETWEEN 1 AND 16
            AND NOT EXISTS (
              SELECT 1 FROM unnest(reasons) AS item
              WHERE item IS NULL OR item !~ '^[A-Z0-9_]{1,64}$'
            ),
            false
          )
        $$
        """
    )
    op.execute(
        """
        CREATE TABLE guard_decisions (
          id text PRIMARY KEY,
          workspace_id text NOT NULL,
          run_id text NOT NULL,
          action_id text NOT NULL,
          ordinal integer NOT NULL,
          verdict text NOT NULL,
          reasons text[] NOT NULL,
          action_digest text NOT NULL,
          policy_revision_observed text NOT NULL,
          guard_version text NOT NULL,
          review_id text,
          evaluated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT guard_decision_ordinal CHECK (ordinal >= 1),
          CONSTRAINT guard_decision_verdict CHECK (verdict IN ('ALLOW', 'REVIEW', 'BLOCK')),
          CONSTRAINT guard_decision_reasons CHECK (guard_reasons_valid(reasons)),
          CONSTRAINT guard_decision_digest CHECK (action_digest ~ '^[0-9a-f]{64}$'),
          CONSTRAINT guard_decision_policy_revision CHECK (
            policy_revision_observed = btrim(policy_revision_observed)
            AND char_length(policy_revision_observed) BETWEEN 1 AND 80
          ),
          CONSTRAINT guard_decision_version CHECK (
            guard_version = btrim(guard_version)
            AND char_length(guard_version) BETWEEN 1 AND 80
          ),
          CONSTRAINT guard_decision_review_link CHECK (
            verdict <> 'REVIEW' OR review_id IS NOT NULL
          ),
          CONSTRAINT guard_decisions_unique_ordinal
            UNIQUE (workspace_id, run_id, action_id, ordinal),
          CONSTRAINT guard_decisions_unique_action_decision
            UNIQUE (workspace_id, run_id, action_id, id),
          CONSTRAINT guard_decisions_action_digest_fk
            FOREIGN KEY (workspace_id, run_id, action_id, action_digest)
            REFERENCES actions (workspace_id, run_id, id, digest) ON DELETE CASCADE,
          CONSTRAINT guard_decisions_review_fk
            FOREIGN KEY (workspace_id, run_id, action_id, review_id)
            REFERENCES reviews (workspace_id, run_id, action_id, id)
            MATCH SIMPLE ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        COMMENT ON TABLE guard_decisions IS
          'Append-only history of persisted Action Guard evaluations. Output evidence only. '
          'Never an input to the guard. Ordinal orders history and has no semantic meaning.'
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_guard_decision() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable_guard_decision';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_guard_decision
        BEFORE UPDATE ON guard_decisions
        FOR EACH ROW EXECUTE FUNCTION protect_guard_decision()
        """
    )
    # A gap, duplicate, or stale ordinal fails. It is never repaired here.
    op.execute(
        """
        CREATE FUNCTION enforce_guard_decision_ordinal() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          expected integer;
        BEGIN
          SELECT COALESCE(MAX(ordinal), 0) + 1 INTO expected
          FROM guard_decisions
          WHERE workspace_id = NEW.workspace_id
            AND run_id = NEW.run_id
            AND action_id = NEW.action_id;
          IF NEW.ordinal IS DISTINCT FROM expected THEN
            RAISE EXCEPTION 'guard_decision_ordinal_invalid';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER guard_decision_ordinal_contiguous
        BEFORE INSERT ON guard_decisions
        FOR EACH ROW EXECUTE FUNCTION enforce_guard_decision_ordinal()
        """
    )


def _execution_link() -> None:
    op.execute("ALTER TABLE executions ADD COLUMN guard_decision_id text")
    # MATCH SIMPLE: a NULL link is not checked, which keeps historical and
    # current-writer rows valid. CASCADE matches every other FK in the run
    # graph, and a decision is only ever deleted with its action or review.
    op.execute(
        """
        ALTER TABLE executions
          ADD CONSTRAINT executions_guard_decision_fk
          FOREIGN KEY (workspace_id, run_id, action_id, guard_decision_id)
          REFERENCES guard_decisions (workspace_id, run_id, action_id, id)
          MATCH SIMPLE ON DELETE CASCADE
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN executions.guard_decision_id IS
          'The authorizing ALLOW guard decision. NULL means not recorded.'
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_execution_authorization() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          decision guard_decisions%ROWTYPE;
        BEGIN
          IF NEW.guard_decision_id IS NULL THEN
            RETURN NEW;
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
    op.execute(
        """
        CREATE TRIGGER execution_authorization_link
        BEFORE INSERT ON executions
        FOR EACH ROW EXECUTE FUNCTION enforce_execution_authorization()
        """
    )


def _immutability_guards() -> None:
    # Reviews: identity, digest, expiry, and the creation timestamp are frozen.
    # decision, reviewer, consumed, decided_at, and consumed_at stay writable
    # because the current writers use them. Strict transitions come later.
    op.execute(
        """
        CREATE FUNCTION protect_review() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.id <> OLD.id OR NEW.workspace_id <> OLD.workspace_id
             OR NEW.run_id <> OLD.run_id OR NEW.action_id <> OLD.action_id
             OR NEW.digest <> OLD.digest OR NEW.expires_at <> OLD.expires_at
             OR NEW.requested_at IS DISTINCT FROM OLD.requested_at THEN
            RAISE EXCEPTION 'immutable_review';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_review
        BEFORE UPDATE ON reviews
        FOR EACH ROW EXECUTE FUNCTION protect_review()
        """
    )
    # Executions: every column except verified_at is frozen, including any
    # column added later. verified_at moves from NULL to a timestamp once.
    op.execute(
        """
        CREATE FUNCTION protect_execution() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (to_jsonb(NEW) - 'verified_at') IS DISTINCT FROM (to_jsonb(OLD) - 'verified_at') THEN
            RAISE EXCEPTION 'immutable_execution';
          END IF;
          IF OLD.verified_at IS NOT NULL AND NEW.verified_at IS DISTINCT FROM OLD.verified_at THEN
            RAISE EXCEPTION 'immutable_execution';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_execution
        BEFORE UPDATE ON executions
        FOR EACH ROW EXECUTE FUNCTION protect_execution()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_ticket() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable_ticket';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_ticket
        BEFORE UPDATE ON tickets
        FOR EACH ROW EXECUTE FUNCTION protect_ticket()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_finding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable_finding';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER immutable_finding
        BEFORE UPDATE ON findings
        FOR EACH ROW EXECUTE FUNCTION protect_finding()
        """
    )


def _action_evidence_validation() -> None:
    # Shape, bound, and same-run existence only. Completeness, expiry, and
    # authorization stay with the Action Guard. Duplicate ids are permitted
    # and the proposal is never rewritten.
    op.execute(
        f"""
        CREATE FUNCTION enforce_action_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          max_evidence_ids CONSTANT integer := 16;
          evidence jsonb := NEW.proposal -> 'evidence_ids';
        BEGIN
          IF evidence IS NULL OR jsonb_typeof(evidence) <> 'array' THEN
            RAISE EXCEPTION 'invalid_action_evidence';
          END IF;
          IF jsonb_array_length(evidence) NOT BETWEEN 1 AND max_evidence_ids THEN
            RAISE EXCEPTION 'invalid_action_evidence';
          END IF;
          IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(evidence) AS item
            WHERE jsonb_typeof(item) <> 'string' OR (item #>> '{{}}') !~ '{UUID_PATTERN}'
          ) THEN
            RAISE EXCEPTION 'invalid_action_evidence';
          END IF;
          IF EXISTS (
            SELECT 1 FROM jsonb_array_elements_text(evidence) AS reference(node_id)
            WHERE NOT EXISTS (
              SELECT 1 FROM content_nodes n
              WHERE n.id = reference.node_id
                AND n.workspace_id = NEW.workspace_id
                AND n.run_id = NEW.run_id
            )
          ) THEN
            RAISE EXCEPTION 'invalid_action_evidence_reference';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER action_evidence_valid
        BEFORE INSERT ON actions
        FOR EACH ROW EXECUTE FUNCTION enforce_action_evidence()
        """
    )


def _derived_node_parent_integrity() -> None:
    # Deferred so a node and its edge can be inserted in either order inside
    # one transaction. A node removed in the same transaction (retention
    # cascade) is skipped, as in 0004.
    op.execute(
        """
        CREATE FUNCTION enforce_derived_node_parent() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM content_nodes WHERE id = NEW.id) THEN
            RETURN NULL;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM content_edges
            WHERE workspace_id = NEW.workspace_id
              AND run_id = NEW.run_id
              AND child_id = NEW.id
          ) THEN
            RAISE EXCEPTION 'derived_node_without_parent';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER content_nodes_derived_parent
        AFTER INSERT ON content_nodes
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW WHEN (NEW.origin = 'derived')
        EXECUTE FUNCTION enforce_derived_node_parent()
        """
    )


def _indexes() -> None:
    op.execute("CREATE INDEX findings_node_lookup ON findings (workspace_id, run_id, node_id)")
    op.execute(
        """
        CREATE INDEX content_edges_parent_lookup
        ON content_edges (workspace_id, run_id, parent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX content_edges_child_lookup
        ON content_edges (workspace_id, run_id, child_id)
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
