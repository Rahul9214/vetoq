# ADR 0004 — Run-scoped relational lineage in PostgreSQL

Status: accepted on 15 October 2026 for the M004 specification. Implemented through M004 GREEN B. Schema head is `0007_lineage_execution_lookup`. Subordinate to [PRODUCT_CONTRACT.md](../PRODUCT_CONTRACT.md) and [SECURITY_INVARIANTS.md](../SECURITY_INVARIANTS.md). The normative rules are [the Module 004 specification](../modules/004-provenance-lineage.md).

## Decision

M004 builds provenance and execution lineage as **run-scoped relational lineage in PostgreSQL**. It joins the relationships that already exist as foreign keys. It adds persistence only where a causal relationship is genuinely missing, and it serves a server-built, bounded read model.

The approved additions are:

- an append-only `guard_decisions` relation that records Action Guard output;
- a structural link from each execution to the guard decision that authorized it;
- structural links from the initial REVIEW decision and the post-review decision to the same review;
- relational review timestamps (`requested_at`, `decided_at`, `consumed_at`);
- immutability for tickets, executions (except `verified_at` once), reviews, and findings;
- validation of proposal and model-finding evidence ids at the workflow and database boundaries;
- four nullable producer-provenance columns on `actions`; and
- a canonical read-visibility rule that requires an active workspace.

Lineage is evidence of what happened. It is never an authorization input. The Action Guard does not read it, and a lineage write failure is fail-closed: the supporting transition and any business side effect do not commit.

Lineage is run-centric. Every read is scoped by workspace and run. There is no cross-run graph, no cross-workspace traversal, and no global provenance graph.

M004 does not extend content retention and adds no retention policy for runs, actions, reviews, tickets, or executions. The broader retention policy remains unresolved later security and operations work.

## Why

The current model already enforces most content, finding, action, review, ticket, and execution relationships. Its gaps are specific:

- Guard evaluations overwrite `actions.verdict`, so decision history, the observed policy revision, and the link between a decision and its review exist only in audit JSON.
- Proposal evidence ids are JSON and nothing in the database ties them to this run.
- Review, execution, and ticket rows have no update guards and no review timestamps.
- The producer of a proposal is not recorded per action.
- Read routes disagree about whether an inactive workspace is readable.

Per-run cardinality is small and frozen by the M003 budgets. PostgreSQL composite foreign keys already carry the tenancy pattern this system relies on. A relational extension closes the gaps without new infrastructure. Audit stays valuable as chronology but cannot be the canonical store of structure, because it is retained for a shorter window and its links are JSON.

## Consequences

- A forward migration sequence of two revisions: `0005_provenance_lineage` (additive structure and tolerant guards) and `0006_lineage_enforcement` (strict invariants after compatible writers exist). Slice F1 later added `0007_lineage_execution_lookup`, an additive run-scoped executions lookup index. It does not change a constraint, trigger, or row. None of these revisions has a destructive downgrade.
- The guard decision writer is enforcement-adjacent. It lands in Slice C with its own review. It records output only and changes no guard rule.
- Guard decision identity is the action plus a non-semantic ordinal. No verdict-specific uniqueness is frozen, because the current at-most-two evaluation count is an observation and not an invariant.
- The first guard version label is `action-guard/1`. It is a version label, not an attestation.
- A narrow `lineage_write_failure` code covers only failures to persist or validate required structural lineage.
- Historical rows stay `not_recorded`. Nothing is backfilled from audit.
- The lineage response excludes content bodies, finding explanations, ticket text, and model free text.
- The visibility change makes run detail, events, content, and ticket reads return a non-enumerating 404 for an inactive workspace. It does not change `decide_review` or `cancel`.
- The proposal and finding evidence validation turns malformed model evidence into an `invalid_model_evidence` run failure and not a persisted policy BLOCK.
- No UI is part of M004 slices A to G. No scale claim is made.

## Alternatives rejected

- A graph database such as Neo4j, or any new infrastructure such as Kafka, Redis, an event bus, a vector database, or a service. Repository evidence shows per-run PostgreSQL cardinality is small and bounded.
- A generic polymorphic `lineage_edges` table. It would lose foreign-key integrity and duplicate relationships that already exist.
- A cross-run or global provenance graph. It is not approved and changes the tenancy and retention model.
- Reconstructing structure from audit JSON. It is retained for a shorter window and is not a structural store.
- Tombstone content nodes, a second content body, or a new retention window in M004.
- A materialized lineage read table. There is no demonstrated need and it would duplicate mutable truth.
- Verdict-specific uniqueness on guard decisions, or an exactly-two-evaluations rule, before the workflow is proven to guarantee it.
- Deferring all producer provenance to M005. The minimal per-action fact is cheap and available. Agent roles, topology, and reasoning traces remain M005.
- Applying every strict trigger in one revision. The strict review rules would break the current writers until they change.
- Putting the visibility fix on mutation routes in this module. That changes review semantics and needs its own change control.
