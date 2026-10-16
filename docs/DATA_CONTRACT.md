# Data contract

This document describes the schema that is applied today. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md). Declared-format parsers for the five live types are implemented. Unsupported formats fail closed.

## Applied revisions

| Revision                        | Contents                                                                                                                                                                                                         |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0001_security_slice`           | Eleven tables, ownership keys, and immutability triggers                                                                                                                                                         |
| `0002_worker_claim`             | `runs_claimable` and `reviews_unresolved_expiry`                                                                                                                                                                 |
| `0003_secure_ingestion`         | Nullable content-node ingestion metadata                                                                                                                                                                         |
| `0004_edge_steps`               | Ordered transform steps for one content edge                                                                                                                                                                     |
| `0005_provenance_lineage`       | Additive lineage structure and tolerant database integrity: `guard_decisions` (written by the runtime from Slice C1), nullable producer, review-timestamp, and execution-link columns                            |
| `0006_lineage_enforcement`      | Strict database rules for new rows only: producer trio, review request time and decision link, review transitions, required execution link with NO ACTION semantics, decision review link, policy-revision shape |
| `0007_lineage_execution_lookup` | Additive `executions_workspace_run_idx` on `executions (workspace_id, run_id)` for the lineage reader's run-scoped filter. No row, constraint, or trigger change                                                 |

Readiness requires `0007_lineage_execution_lookup`. Do not rewrite an applied migration. The next schema change is a new revision. `0002_worker_claim`, `0003_secure_ingestion`, `0004_edge_steps`, `0005_provenance_lineage`, `0006_lineage_enforcement`, and `0007_lineage_execution_lookup` have no destructive downgrade.

## Tables

| Table                | Ownership                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `workspaces`         | Tenant boundary. `active` and `policy_revision` (trimmed, 1 to 80 characters, `0006`)                                          |
| `memberships`        | Principal role `operator` or `reviewer` in one workspace                                                                       |
| `runs`               | One Goal Lock (`envelope`), state, budgets, lease, and fence                                                                   |
| `content_nodes`      | Untrusted original or derived text for one run                                                                                 |
| `content_edges`      | Parent-to-child summary transform, version, lossiness, and optional step count                                                 |
| `content_edge_steps` | Ordered transform and version for one recorded edge                                                                            |
| `findings`           | Deterministic or model evidence span on one node                                                                               |
| `actions`            | One persisted proposal, digest, optional latest-verdict cache, and nullable producer provenance (`0005`)                       |
| `guard_decisions`    | Append-only history of persisted Action Guard evaluations. Output evidence only (`0005`; written by the runtime from Slice C1) |
| `reviews`            | One review row per action, with nullable `requested_at`, `decided_at`, and `consumed_at` (`0005`)                              |
| `tickets`            | At most one local ticket per run and per action                                                                                |
| `executions`         | At most one receipt per action, with optional `verified_at` and a nullable link to the authorizing ALLOW decision (`0005`)     |
| `audit_events`       | Append-only sequence per run                                                                                                   |

Foreign keys keep content, findings, actions, reviews, tickets, and executions inside the run and workspace. A run references the membership that accepted it.

## Immutable fields

Database triggers reject changes to the Goal Lock envelope, principal, workspace, expiry, submission key, and submission digest. They reject changes to action proposal, digest, run, and workspace. Content node updates are rejected. Content edge updates are rejected. Transform-step updates are rejected. Audit events cannot be updated, and they cannot be deleted before the retention window. These triggers are application-level durability. They are not a control against a database administrator.

Schema `0005_provenance_lineage` adds these database facts. Each is tolerant of historical NULLs. Schema `0006_lineage_enforcement` then tightens them for new rows only, as listed after this block:

- `guard_decisions` rows cannot be updated. The `ordinal` of a new row must be exactly one greater than the action's current maximum, so a gap, duplicate, or stale ordinal is rejected. Verdict, reasons (1 to 16 stable codes), action digest, observed policy revision, guard version, and review link are checked. A REVIEW decision requires a review. A decision references its action only through the action's immutable digest, and its review only within the same action. Deleting an action or review deletes its decisions.
- An execution that carries a `guard_decision_id` must reference an ALLOW decision of the same action whose digest equals the execution digest. A NULL link on a historical execution means not recorded. The `0005` link was `ON DELETE CASCADE`. `0006` replaced it (see below).
- Action producer columns are immutable, and so are the proposal, digest, run, and workspace. The three required producer columns are all NULL or all set, trimmed, and 1 to 120 characters. The response id is independent, trimmed, and 1 to 200 characters. All stay outside the action digest. `verdict` and `reasons` remain a mutable latest-evaluation cache.
- Review identity, workspace, run, action, digest, `expires_at`, and `requested_at` are immutable. `decided_at` needs a decision and reviewer. `consumed_at` needs `consumed`. Decision, reviewer, consumed, and their timestamps stay writable.
- Executions are immutable except `verified_at`, which can move from NULL to a timestamp once. Tickets and findings cannot be updated.
- An action cannot be inserted unless its proposal has 1 to 16 evidence ids, each a UUID of a content node in the same workspace and run. Duplicates are allowed and the proposal is never rewritten.
- A derived content node must have a parent edge by commit.

Schema `0006_lineage_enforcement` adds these strict rules. Each applies to new rows and new transitions only. No existing row was rewritten, no column became `NOT NULL`, and a historical NULL stays valid:

- `workspaces.policy_revision` must be trimmed and 1 to 80 characters (`workspaces_policy_revision_shape`), the same shape `guard_decisions.policy_revision_observed` requires. The constraint was validated against every existing row. The trim is PostgreSQL's `btrim`, which removes spaces.
- A new action must carry `producer_provider`, `producer_model`, and `producer_prompt_version` (trigger `action_producer_required`). A `producer_response_id` stays optional and cannot exist without the trio (`action_producer_response_requires_trio`). Producer fields stay immutable and outside the action digest.
- A new review must carry `requested_at` (trigger `review_requested_at_required`). By commit, every new review must have a `guard_decisions` row of the same workspace, run, and action with `verdict = 'REVIEW'` and `review_id` equal to the review (deferred constraint trigger `review_has_review_decision`).
- Review transitions are one-way. While undecided, the decision, reviewer, and `decided_at` stay all NULL or become all non-NULL together, and once decided they never change. While unconsumed, `consumed` and `consumed_at` stay unset or become `true` and non-NULL together, only on an `approve` decision, and once consumed they never change. A historical review with a NULL `requested_at`, or a decision without `decided_at`, or a consumption without `consumed_at`, is not rewritten, and the current writer can still decide and consume it.
- A new execution must carry a `guard_decision_id`. The link must still reference an ALLOW decision of the same workspace, run, and action whose digest equals the execution digest. `executions_guard_decision_fk` is `ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`, so deleting a guard decision directly is rejected and the execution survives. A run or action deletion still cascades through decisions and executions together. Retention is unchanged.
- A new guard decision for an action that already has a review must carry that exact review (trigger `guard_decision_review_link_required`). A straight ALLOW or BLOCK for an action with no review carries none.

The `runs.state` check constraint still lists `INSPECTING`. The workflow does not persist that value. Do not treat the constraint name as evidence that an inspection state exists.

## Goal Lock and digests

`runs.envelope` is the confirmed `GoalLock`: version, template `support-triage/1`, principal, workspace, source id and digest, goal text, `tickets.create` version 1, destination `local-ticket-store`, expiry, policy revision `support-triage/1`, and the write, proposal, and continuation budgets.

The action digest is SHA-256 over canonical JSON of version, run id, envelope, and proposal. The submission digest identifies the accepted input for idempotency.

## Idempotency, review, and audit

- One submission key per workspace and principal. The same key and digest returns the original run. A different digest conflicts.
- One execution per action and one ticket per run.
- A review is consumed in the same transaction that writes the ticket. A consumed or expired approval cannot authorize another write.
- Audit sequence is assigned per run as one greater than the current maximum. Clients read events with `sequence > after`.

## Provenance graph

Nodes store origin, supplier, digest, content, `trust = untrusted`, completeness, and expiry. Edges store the transform. The implemented graph is per run. M004 lineage is also run-scoped. A cross-run, cross-workspace, or global lineage graph is not approved and would require separate change control. See [the M004 lineage design](#m004-lineage-design).

## Retention

The retention command deletes content nodes whose expiry has passed and audit events older than 30 days. The run-delete trigger also refuses deletion of a run newer than 24 hours. This is an operator command, not a background service.

M004 does not extend this retention, add tombstones, or create a second body store. It adds no retention policy for runs, actions, reviews, tickets, or executions. A broader retention policy is unresolved later security and operations work. When a run's lineage is read after retention, a missing original is never reported as deleted by retention, because no persisted fact records what deleted it (the `retain` command only deletes). It is `inconsistent` if it could not yet have been eligible for retention, and `unverifiable` if it was eligible. See [the Module 004 specification](modules/004-provenance-lineage.md).

## M004 lineage design

Status vocabulary: IMPLEMENTED TODAY, APPROVED DESIGN, OPEN LATER WORK. The schema, writers, enforcement, read service, typed endpoints, shield, and executions lookup index are IMPLEMENTED TODAY as stated below. PROV-001 and LINE-001 are IMPLEMENTED for their approved GREEN B sentences. There is no lineage UI. This section is a summary. [The Module 004 specification](modules/004-provenance-lineage.md) is the detailed authority for M004.

- **Scope.** Lineage is run-scoped relational data in PostgreSQL. Lineage is output evidence. It is never an input to the Goal Lock, policy, Action Guard, review eligibility, dispatcher, or a model call.
- **Guard decisions.** The append-only `guard_decisions` table records each persisted Action Guard evaluation: action, ordinal, verdict, reasons, action digest, observed policy revision, guard version label `action-guard/1`, review link, and time. The ordinal orders the history and has no semantic meaning. Nothing in the contract limits an action to one ALLOW, one REVIEW, or two evaluations. A write failure fails closed. The label changes when guard behavior could change the verdict or reasons for the same effective inputs. The reason-count bound is not frozen. Slice B proves it from the guard code and tests.
- **Review linkage.** A REVIEW decision, its review, the reviewer decision, and the post-review ALLOW or BLOCK decision are linked structurally. Both decisions reference the same review. An execution references the authorizing ALLOW decision, nullable for legacy rows. Audit events are not used to infer links.
- **Review timestamps.** `requested_at`, `decided_at`, and `consumed_at` exist and the runtime writes them for new reviews. A legacy NULL is not fabricated.
- **Immutability.** Tickets are immutable. Executions are structurally immutable except `verified_at`, which may go from NULL to a timestamp once. Review identity, digest, and `expires_at` are immutable. Findings are update-immutable.
- **Proposal evidence.** Proposal evidence ids (1 to 16) are validated in the workflow and in the database against the same workspace and run, before an executable action is persisted. A failure is `invalid_model_evidence`, not a policy BLOCK. Duplicate ids are tolerated and the proposal is never rewritten. A model finding that cites evidence ids is rejected the same way.
- **Producer provenance.** Nullable action columns `producer_provider`, `producer_model` (the requested identifier), `producer_prompt_version`, and `producer_response_id` exist, and the runtime writes them for new model-produced actions. The response id is optional: an empty, whitespace-only, or over-200-character id is stored as NULL, never truncated, and never fails the run. The first three are required in PostgreSQL for every new action since migration `0006`. A NULL `producer_provider` is not a universal definition of a legacy row. They record no agent roles, topology, or reasoning traces.
- **Findings.** Relationships are `observed_in` and `findings_on_cited_evidence`, which describe structural co-location only.
- **Free text.** No model free text, explanation, or private reasoning is stored as lineage.
- **No audit backfill.** Historical runs are reported as not recorded. Lineage is not reconstructed from audit events.
- **Migrations.** `0005_provenance_lineage` is additive with tolerant guards. `0006_lineage_enforcement` is strict for new rows and was applied after the writers existed. `0007_lineage_execution_lookup` adds `executions_workspace_run_idx` on `(workspace_id, run_id)` so the lineage executions read has an index path. None has a destructive downgrade.
- **Failure vocabulary.** `lineage_write_failure` means one required structural lineage write was rejected by a lineage integrity rule, or the required producer provider, model, or prompt version was unusable. The runtime classifies it from PostgreSQL's SQLSTATE and diagnostics: an integrity violation (class 23) of a named lineage constraint on the write's own table, or `RAISE EXCEPTION` (`P0001`) with the exact machine code of a lineage trigger. The covered writes are the `guard_decisions` insert (including its review link), the execution authorization link (including its required presence), and the producer columns (including the required trio). The policy-revision shape check and the review request-time rule are not lineage writes and never classify as `lineage_write_failure`. It does not cover a statement timeout, cancellation, lock failure, lost connection, shutdown, a ticket or other execution failure, a provider failure, or `invalid_model_evidence`. Those keep their existing codes, and no write survives any of them.
- **Retention states.** Content state is `available`, `expired_body_pending_deletion`, `inconsistent`, or `unverifiable`. `removed_by_retention` is reserved and currently unreachable, because no persisted fact proves that retention performed a deletion.

## Migration policy

Never edit `0001_security_slice` or `0002_worker_claim` to clean history. Add a forward revision. Do not point Alembic at the development database when the intent is the test database.

## Ingestion metadata

Normative ingestion rules are [the Module 003 specification](modules/003-universal-secure-ingestion.md). `0003_secure_ingestion` adds nullable `declared_media_type`, `representation_kind`, `parser_id`, `parser_version`, `charset`, and `byte_size` on `content_nodes`. NULL means the fact was not recorded. Historical rows are not backfilled. `validated_media_type` and `channel` are not columns. Non-null values are constrained to the allowlists in that migration. A derived representation kind requires a parser id and version together. The existing content trigger still rejects every update, so this metadata is immutable once written. The live `POST /runs` insert writes those columns on the original. A historical Module 002 row stays null and is not rewritten. The worker writes derived nodes, edges, and steps after it claims a staged original. A null `transform_step_count` is read as no step list.

`content` remains `text NOT NULL`. `trust` remains `untrusted`. `content_edges.transform` and `version` are the summary of the whole parent-to-child derivation. They are not defined as the last step. `transform_step_count` NULL means the ordered chain was not recorded. A value from 1 through 4 means exactly that many `content_edge_steps` rows, with contiguous indexes from 1. Historical edges stay NULL. They are not backfilled from the summary. The worker inserts the count and the actual steps for a new recorded derivation. It does not invent a step from the summary. A new Base64 edge records one `base64` / `1` step. A decoded node records `decoded_text` with parser `bounded-decoder` version `1`. Parser id and parser version stay on the child node and are independent of the step list. Reading a null count yields no step list. It does not yield an empty list and it does not infer steps from the summary. The Goal Lock envelope keeps one `source_id` and one `source_digest`. `source_digest` is SHA-256 of the UTF-8 encoding of the validated source string, not of the HTTP JSON bytes, and not of a derived representation. The normalized declared media type is not an envelope field and it is not authority. Parser version is not part of `source_digest` or the submission digest. An accepted run is not reprocessed when a parser version changes. No `bytea`, object store, or filesystem payload is added. Retention of nodes and audit events is unchanged. Deleting a node deletes its edges and those edges' steps. Steps have no retention timestamp. The one ingestion budget source includes `transform_steps_per_edge` = 4. The database checks repeat that bound.
