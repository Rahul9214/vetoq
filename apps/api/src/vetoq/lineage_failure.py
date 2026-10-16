"""Classifies which database failures mean required structural lineage was not persisted.

`lineage_write_failure` is a narrow code. It means one specific, required lineage write was
rejected by a lineage integrity rule in the schema. It never means a general database
failure: timeouts, cancellations, lock failures, lost connections, and shutdowns are
`OperationalError` and keep their existing worker-failure handling. An integrity error on
any other table or constraint, such as the ticket, is not a lineage failure either. A
constraint that merely exists in a lineage migration is not a lineage failure unless it
guards one of the writes below. For example, the `workspaces` policy revision shape check
is ordinary validation, not lineage.

Identity comes from the server's structured diagnostics, never from message text:

* SQLSTATE class 23 (integrity constraint violation) on the write's own table, and only
  for a named lineage constraint; or
* SQLSTATE `P0001` (`RAISE EXCEPTION`) whose primary message is exactly one of the machine
  codes that a lineage trigger raises for that write. The codes are unique to those
  triggers, and the primary message is not translated by `lc_messages`.

The names below are the identities created by migrations `0005_provenance_lineage` and
`0006_lineage_enforcement`. A later migration that renames or replaces one must update this
module and its tests.
"""

from dataclasses import dataclass

import psycopg
from sqlalchemy.exc import DBAPIError

INTEGRITY_CONSTRAINT_CLASS = "23"
RAISE_EXCEPTION = "P0001"


@dataclass(frozen=True)
class LineageWrite:
    """The integrity identities of one required lineage write."""

    table: str
    constraints: frozenset[str]
    trigger_codes: frozenset[str]


# INSERT INTO guard_decisions: one structural record of a guard evaluation.
DECISION_WRITE = LineageWrite(
    table="guard_decisions",
    constraints=frozenset(
        {
            "guard_decision_ordinal",
            "guard_decision_verdict",
            "guard_decision_reasons",
            "guard_decision_digest",
            "guard_decision_policy_revision",
            "guard_decision_version",
            "guard_decision_review_link",
            "guard_decisions_unique_ordinal",
            "guard_decisions_unique_action_decision",
            "guard_decisions_action_digest_fk",
            "guard_decisions_review_fk",
        }
    ),
    trigger_codes=frozenset(
        {"guard_decision_ordinal_invalid", "guard_decision_review_link_required"}
    ),
)

# INSERT INTO executions: only the link to the authorizing ALLOW decision. Every other
# executions constraint (action, ticket, one execution per action) is not lineage.
EXECUTION_LINK = LineageWrite(
    table="executions",
    constraints=frozenset({"executions_guard_decision_fk"}),
    trigger_codes=frozenset(
        {"invalid_execution_guard_decision", "execution_guard_decision_required"}
    ),
)

# INSERT INTO actions: the database backstop for the producer columns that the
# application validates first. Evidence and immutability rules are not part of this write.
PRODUCER_WRITE = LineageWrite(
    table="actions",
    constraints=frozenset(
        {
            "action_producer_triplet",
            "action_producer_provider_length",
            "action_producer_model_length",
            "action_producer_prompt_version_length",
            "action_producer_response_id_length",
            "action_producer_response_requires_trio",
        }
    ),
    trigger_codes=frozenset({"action_producer_required"}),
)


def is_lineage_integrity_failure(error: DBAPIError, write: LineageWrite) -> bool:
    """True only for a lineage integrity rule rejecting this exact required write."""

    cause = error.orig
    if not isinstance(cause, psycopg.Error):
        return False
    sqlstate = cause.sqlstate
    if sqlstate is None:
        return False
    diag = cause.diag
    if sqlstate == RAISE_EXCEPTION:
        return diag.message_primary in write.trigger_codes
    if not sqlstate.startswith(INTEGRITY_CONSTRAINT_CLASS):
        return False
    return diag.table_name == write.table and diag.constraint_name in write.constraints
