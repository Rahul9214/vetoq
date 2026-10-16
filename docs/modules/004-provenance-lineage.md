# Module 004 — Provenance graph and execution lineage

**GREEN B / COMPLETE, 16 October 2026.** Schema head is `0007_lineage_execution_lookup`. There is no lineage UI. PROV-001 and LINE-001 are IMPLEMENTED for their approved sentences. OBS-001 and SEC-001 stay PARTIAL.

**Specification history.** Slice A, 15 October 2026, was contracts, ADR, and change control only. Slice B added the additive schema `0005_provenance_lineage`. Slice C1 added the runtime lineage writers, and Slice C2 added the strict database enforcement `0006_lineage_enforcement`. Slice D added the canonical run visibility rule and an internal lineage read service, and Slice E exposed it through three typed, read-only endpoints (no BFF production change was needed, and no UI exists). Slice F added the security, retention, query-plan, and observability shield. Slice F1 added `0007_lineage_execution_lookup`. Slice G is the release shield, populated rehearsal, and capability closeout.

Product, security, architecture, data, and API authority stay in the canonical contracts. This specification binds the M004 implementation. It does not override those contracts. [ADR 0004](../adr/0004-run-scoped-relational-lineage.md) records the architecture decision. Change records [0002](../change-control/0002-prov-001-wording.md), [0003](../change-control/0003-line-001-wording.md), and [0004](../change-control/0004-active-workspace-visibility.md) record the wording and tenancy changes.

## Status vocabulary

Every statement below carries one of these meanings. A planned relation, column, or route is not a current one.

| Label             | Meaning                                                  |
| ----------------- | -------------------------------------------------------- |
| IMPLEMENTED TODAY | In the verified M004 runtime and its tests               |
| APPROVED DESIGN   | Approved by human review. Not built. It binds later work |
| OPEN LATER WORK   | Not decided or not owned by M004. No design is approved  |

## Position

M004 is **run-scoped relational lineage in PostgreSQL**. It extends the existing relational model with a small number of additive structures and a server-built, bounded read model.

**Lineage describes what happened. Lineage never grants authority.** It is evidence. It is never an input to the Goal Lock, the policy check, the Action Guard, review eligibility, the dispatcher, or any model call.

M004 is not a generic graph database, a cross-run graph, a global provenance graph, Neo4j, Kafka, Redis, an event bus, a vector database, or a new service. Adding any of them needs an accepted ADR and a demonstrated need. Nothing in M004 provides one.

## Questions the module answers

From persisted evidence, and never from UI state, logs, or audit text:

- Where did evidence originate?
- What was derived from it?
- Through which exact transformations?
- Which findings were observed on which evidence?
- Which evidence ids were cited by a proposal?
- Which model and provider produced that proposal?
- What Goal Lock scoped the run?
- What deterministic guard evaluations occurred?
- Was human review required?
- What did the reviewer decide?
- Which guard decision authorized execution?
- What was executed?
- Was execution verified?
- Which facts are historical or retained, and which were not recorded?

## IMPLEMENTED TODAY (Module 003 baseline)

These relationships already exist and are joined, not copied:

- Original and derived `content_nodes`, immutable once inserted, with nullable ingestion metadata.
- `content_edges` (summary transform) and `content_edge_steps` (ordered transform history), immutable, with a commit-time completeness check.
- `findings`, with a composite foreign key to the node. Findings have no update guard, no timestamp, and no link to an analysis attempt.
- `runs.envelope`, the immutable Goal Lock. Its `source_id` and `source_digest` are JSON fields, not a foreign key.
- `actions`: an immutable proposal and digest, including `evidence_ids` (JSON, not a foreign key), and a mutable `verdict` and `reasons` that each evaluation overwrites.
- `reviews`: one row per action, with `digest`, `expires_at`, `reviewer`, `decision`, and `consumed`. No timestamp columns and no update guard.
- `tickets` and `executions`: one each per action. `executions` carries `digest`, `committed_at`, and `verified_at`. Neither has an update guard.
- `audit_events`: append-only for 30 days. Structural ids live in `detail` JSON.
- Content nodes expire after 24 hours. The operator `retain` command deletes them, and the cascade removes their edges, steps, and findings. Runs, actions, reviews, tickets, and executions have no deletion path.

IMPLEMENTED TODAY does not include any item in the approved design below.

## Scope: run-centric (APPROVED DESIGN)

Every lineage read is scoped by workspace and run. There is no cross-run lineage, no cross-workspace traversal, and no global graph. A node id, action id, or review id supplied by a client is a selector inside an already authorized run. It is never authorization.

A future cross-run or global lineage product requires its own change-control record, ADR, and architecture approval. This module neither starts nor implies it.

## Relational lineage and audit are different things

**Relational lineage** is the durable causal structure: foreign keys, uniques, and immutability.

**Audit events** are chronological operational evidence kept for the audit window.

M004 does not merge them. Audit remains valuable for chronology. It is not the canonical store of structural lineage, and it is not an authorization source.

**No audit backfill.** Audit JSON is not parsed to fabricate structural lineage. A historical structural fact that was never recorded is `not_recorded`. It is not reconstructed from audit, from timestamps, or from `actions.verdict`.

## Guard decision history (IMPLEMENTED TODAY)

The append-only relation `guard_decisions` records the output of each persisted deterministic Action Guard evaluation.

It is:

- append-only, with updates rejected;
- scoped to workspace, run, and action;
- digest-bound to the exact action digest that was evaluated;
- ordered by a non-semantic ordinal;
- timestamped; and
- version-labeled.

It records Action Guard **output**: verdict, stable reason codes, the observed policy revision, the guard version label, and the review it considered when there was one.

**It must never become an Action Guard input.** `guard()`, its input type, and `authorize()` must not read it to decide anything.

**Fail-closed writer.** The writer runs in the same transaction as the state transition it supports. If the required decision lineage cannot persist, the supporting state transition and any business side effect cannot commit.

### Retry and ordering semantics

Identity is the action plus the ordinal. The ordinal is ordered history. It has no semantic meaning.

Today's state machine happens to evaluate one action at most twice. That count is an observation and not an invariant. Future code must not depend on it.

These are **not** frozen and must not be documented as invariants:

- at most one ALLOW per action, ever;
- at most one REVIEW per action, ever;
- exactly two evaluations.

A restart or reclaim must not silently discard duplicate history. A uniqueness violation is a fault that rolls back and fails closed. Allocation uses the existing action row lock and a database backstop, so the history stays contiguous. The exact ordinal rule is fixed in Slice B and tested in Slice C.

### Guard version label

The first label is `action-guard/1`. The canonical constant is `action-guard/1`. It is a version label only. It is not an attestation, a trust score, or a signature.

**Bump rule.** Bump the label whenever a deterministic guard behavior change could alter the verdict or reasons for the same effective inputs. Do not bump it for comments or refactors with identical behavior.

### Guard reasons

Guard reasons are a bounded, listed set of stable reason codes. The module does not yet freeze a minimum count.

Before Slice B defines the database CHECK, it must prove from the current guard implementation and its tests whether a valid decision can ever have an empty reason list:

- If every decision has at least one reason, use a cardinality of 1 to 16.
- If a valid current decision can contain `[]`, the schema must allow 0 to 16.

Action Guard behavior is not modified to satisfy lineage storage.

## Review lineage and timeline (IMPLEMENTED TODAY)

The intended causal structure:

```text
GuardDecision REVIEW
        ↓
Review
        ↓
reviewer decision
        ↓
GuardDecision ALLOW or BLOCK, after revalidation
        ↓
Execution, if ALLOW
```

- The initial REVIEW decision and the post-review revalidation decision both structurally reference the same review row.
- The execution structurally references the exact ALLOW guard decision that authorized it.
- Audit events are not used to infer any of these links.

### Review timestamps

Relational timestamps on `reviews`:

- `requested_at`: recorded at creation.
- `decided_at`: set together with the decision and the reviewer, exactly once.
- `consumed_at`: set exactly once, with consumption.

Rows that exist before the migration keep NULL. A NULL timestamp is `not_recorded`. No timestamp is fabricated, including from audit.

The revalidation instant is the linked decision's own timestamp. It is not stored a second time.

### Intended transitions

| Object       | Rule                                                                                      |
| ------------ | ----------------------------------------------------------------------------------------- |
| `tickets`    | Immutable after insert.                                                                   |
| `executions` | Structural fields immutable. `verified_at` moves NULL to a timestamp once.                |
| `reviews`    | Identity, digest, and `expires_at` immutable.                                             |
| `reviews`    | `decision`, `reviewer`, and `decided_at` are set together, exactly once.                  |
| `reviews`    | `consumed` moves false to true only. `consumed_at` is set exactly once, with consumption. |
| `findings`   | Update rejected. Delete stays governed by content retention and the existing cascade.     |

The strict forms of the review rules are active in `0006_lineage_enforcement` (IMPLEMENTED, Slice C2), after the writers that satisfy them. They apply to new rows and transitions only. A historical review keeps its NULLs, and the current writer can still decide and consume it.

Production review expiry is immutable. A test that needs an expired review must create one through production code or direct insertion. It must not rely on mutating `expires_at`. That test rewrite is implemented.

## Execution authorization link (IMPLEMENTED TODAY)

Executions gain a nullable, legacy-compatible structural link to the exact guard decision that authorized them. The decision must be an ALLOW for the same action and digest.

Historical executions have no such link. Their authorization link is `not_recorded`.

## Proposal evidence integrity (IMPLEMENTED TODAY)

`actions.proposal.evidence_ids` is validated twice:

- in workflow and domain code; and
- at the database boundary.

Each evidence id must resolve to a node in the same workspace and the same run. The existing bound still applies: one to sixteen ids.

Malformed model evidence fails as `invalid_model_evidence` before an executable action is persisted. This is a run failure. It is not a policy BLOCK, and a malformed model output is not converted into one.

This is separate from the Action Guard's time-varying checks of completeness, expiry, and policy authorization. Those stay in the guard.

**Duplicate evidence ids remain tolerated** for compatibility. The immutable proposal is never rewritten or deduplicated. The lineage read model may avoid duplicate relationship objects for presentation, but it returns the exact stored list where it returns the list at all.

### Model finding evidence

An invalid model-finding evidence id uses the same stable `invalid_model_evidence` semantics. It is not quarantined as `worker_failure`.

## Findings relationships

Findings are historical evidence facts. Do not claim finding to proposal causality because both concern the same content.

Use precise relationships:

- `observed_in`: a finding was recorded on a node.
- `findings_on_cited_evidence`, where useful: findings recorded on nodes that a proposal cites. This is structural co-location. It is not proof that the model relied on a finding.

Deterministic findings are not supplied to the model. They influence authority only through the run-level uncertainty flag. Lineage must not present a finer causal link than the stored facts support.

## Proposal producer provenance (IMPLEMENTED TODAY)

Four nullable columns on `actions`, written once when the action is inserted:

| Column                    | Meaning                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------- |
| `producer_provider`       | The provider used for that inference.                                                 |
| `producer_model`          | The **requested** model identifier. Not necessarily a provider-reported served model. |
| `producer_prompt_version` | The prompt contract and version used.                                                 |
| `producer_response_id`    | The provider completion or response correlation id, when supplied.                    |

An empty provider response id is stored as NULL.

The columns are not part of the action digest. They are evidence about the producer and never authority.

**Migration compatibility.** `0005` adds the columns as nullable. After the `0006` enforcement and writer cutover, every new model-produced action must carry `producer_provider`, `producer_model`, and `producer_prompt_version`. `producer_response_id` stays optional. Historical and in-flight rows may remain NULL forever.

`producer_provider IS NULL` is **not** a universal definition of legacy. Rows created between `0005` and the writer cutover, and in-flight rows, can also be NULL. Slice D defines each legacy and anomaly distinction from provable persisted facts, or reports `not_recorded`.

M004 adds no specialist agent role, no multi-agent topology, no reasoning trace, and no record of an agent's thought process. Those belong to M005.

## Free-text boundary (APPROVED DESIGN)

The lineage read model does not duplicate sensitive or free-form content. It excludes:

- content bodies;
- finding explanation prose;
- ticket title and body;
- model reasoning; and
- model summaries.

It carries structural metadata: ids, stable enums, stable reason codes, digests, offsets, versions, timestamps, relationships, and integrity states.

Existing authorized resource endpoints keep their current behavior under the current contracts.

## Visibility (IMPLEMENTED in Slice D for existing reads and in Slice E for the lineage routes)

Approved read rule, recorded in [change record 0004](../change-control/0004-active-workspace-visibility.md):

> active membership AND active workspace AND matching workspace and run

Otherwise the response is a non-enumerating `404 not_found`. A missing run, a foreign workspace, an inactive membership, an inactive workspace, and a missing sub-resource inside an accessible run are indistinguishable.

This applies to run detail, events, content, ticket read, and every lineage read. **Slice D implemented it** for `get_run`, `get_events`, `get_content`, and `get_ticket`, in `vetoq/visibility.py`. `list_runs`, `/me`, and submission already checked workspace activity.

**Canonical helper (IMPLEMENTED).** `visibility.visible_run(connection, run_id, principal)` joins the run, its active workspace, and the principal's active membership, and returns the trusted run row or raises `not_found`. Every later read of run-scoped data in those four routes, and every query of the lineage service, uses that row's `workspace_id` and `id`. A client-supplied workspace id is never used. A ticket is resolved through the run it belongs to, with no independent membership-only path, and a missing ticket, a foreign ticket, an inactive membership, and an inactive workspace are the same 404. A lineage route must not build a second, independent authorization lookup. Client identifiers are selectors, never authorization.

**Mutation routes are not changed.** The clarification covers read routes. `decide_review` and `cancel` keep their current semantics in M004. That is a separate later hardening consideration (OPEN LATER WORK). They are not hardened by this module.

## Retention (APPROVED DESIGN)

M004 does not:

- extend content retention;
- create tombstone content nodes;
- retain a second content body; or
- introduce a run, action, review, ticket, or execution retention policy.

Existing M003 content retention remains authoritative. The broader retention policy for runs, actions, reviews, tickets, executions, and the metadata M004 adds is **unresolved later security and operations work** (OPEN LATER WORK). The new lineage rows carry metadata only and inherit the same absence of a retention clock until that work is decided.

### Truthful content states

The read model reports one of these states for run content. Eligibility for retention and the cause of a deletion are separate facts. **A missing original never means retention deleted it.**

| State                           | Condition                                                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `available`                     | The original exists and has not expired.                                                                                                                |
| `expired_body_pending_deletion` | The original exists, its expiry has passed, and `retain` has not removed it.                                                                            |
| `inconsistent`                  | The original is absent and persisted facts show it could not yet legitimately have been eligible for retention, or other content of the run remains.    |
| `unverifiable`                  | The original is absent and it was eligible for retention, but no durable fact records the cause. Also the state when a check cannot be evaluated.       |
| `removed_by_retention`          | **Reserved. Currently unreachable.** Would require a persisted fact proving `retain` deleted the original. No such fact exists, so it is never emitted. |

`not_recorded` is not a retention state: the node expiry is never NULL.

**Persisted retention facts (Slice D1 inspection).** The original is written with `expires_at` equal to the application clock `now() + 24 hours`, derived nodes copy the original's expiry, and the run row is created by the database clock and cannot be deleted for 24 hours. `retain` runs `DELETE FROM content_nodes WHERE expires_at <= now()` and writes nothing else for content: no audit event, no marker, no tombstone, no counter. A deleted row leaves no trace, and a run-level cascade or an operator delete would leave the same absence. After deletion, **no persisted fact proves that `retain` deleted the original**, only that it was old enough for retention to have deleted it.

**Rules (IMPLEMENTED).** Eligibility is `read_time >= runs.created_at + 24 hours`, where `read_time` is the database clock at the snapshot. There is no grace period. The retention window is the documented 24 hours, and the application-versus-database clock offset is not persisted, so it is not modelled; an invented allowance would be an unapproved rule. Aged eligibility tests INSERT `runs.created_at` already past the window; `immutable_run` is an UPDATE/DELETE trigger and is never disabled.

- Original present, not expired: `available`. Original present, `expires_at <= read_time`: `expired_body_pending_deletion`.
- Original absent and no content remains, before eligibility: `inconsistent`, code `source_missing_before_retention`.
- Original absent and no content remains, at or after eligibility: `unverifiable`, code `source_missing_retention_unverifiable`. Eligibility is stated, deletion cause is not.
- Original absent while other content of the run remains: `inconsistent`, code `source_missing_with_graph_present`. Derived nodes share the original's expiry, so one retention delete removes them together.
- Unusable Goal Lock, or a capped node set: `unverifiable`.

For an absent original the read model synthesizes no node, edge, step, finding, or transform history, and the node, edge and finding counts are the persisted zero. The Goal Lock source id and digest, the proposal evidence ids (reported `unresolved`), and the action, decision, review, execution and ticket facts remain and are presented as stored. The source binding is `unverifiable` in the unverifiable state and `inconsistent` in the inconsistent state.

`unverifiable` is also the result of any individual integrity check that cannot be evaluated. Source-digest verification is unverifiable after content is removed.

Making `removed_by_retention` reachable needs a new durable fact written by the retention operation (for example a per-run retention record). That is a retention-writer and schema change, and it is not authorized in M004.

## Legacy behavior (APPROVED DESIGN)

Historical Module 002 and Module 003 runs are represented truthfully.

- Missing ingestion metadata, transform steps, guard decisions, review timestamps, producer fields, and the execution authorization link are `not_recorded`.
- No structural lineage is backfilled from audit (see above).
- A historical decision may be shown from `actions.verdict`, labeled as the latest verdict only. It is not presented as decision history.

**Slice D rules (IMPLEMENTED).** `not_recorded` (a fact was never stored) and `inconsistent` (recorded facts contradict each other) are decided from provable relations, never from one NULL such as `producer_provider` and never by a blanket legacy flag:

- A recorded producer trio proves a writer from the C1 cutover on. A verdict in the cache with no decision row is then `decisions_missing`. Without the trio it is the `latest_only` stage.
- A guard decision proves a writer that links every execution. An execution with a NULL link and an ALLOW decision for its action is `execution_link_missing`. With no ALLOW decision, the link is `not_recorded`.
- A NULL transform step count is `not_recorded` and steps are never reconstructed from the edge summary. Step rows against a NULL count, or a count that disagrees with the step rows, is `edge_steps_inconsistent`.
- A derived node without a parser pair has `parser_state = not_recorded`. An original has `not_applicable`.
- Review `requested_at`, `decided_at` and `consumed_at` are listed in `not_recorded` when NULL where the review's own state implies them. Recorded timestamps out of order are `review_timeline_order`.

## Failure vocabulary (APPROVED DESIGN)

- `invalid_model_evidence` already exists as a domain failure. M004 extends its use to malformed proposal evidence and malformed finding evidence.
- `lineage_write_failure` is a stable failure code, defined narrowly. Only a failure to persist or validate **required structural lineage** may map to it.

Do not map these to `lineage_write_failure`: tool execution failures, ticket failures, general database failures (statement timeout, query cancellation, lock failure, connection loss, admin shutdown), provider failures, or `invalid_model_evidence`. They keep their existing codes.

The implementation is Slice C. The writers landed in C1 and the narrow database classification landed in C1B.

## Migration sequence (APPROVED DESIGN)

Two revisions, in this order. Neither is created in Slice A, and `SCHEMA_REVISION` is not bumped in Slice A.

| Revision                        | Slice | Purpose                                                                                |
| ------------------------------- | ----- | -------------------------------------------------------------------------------------- |
| `0005_provenance_lineage`       | B     | Additive structure and compatibility (tolerant) guards. Existing writers keep working. |
| `0006_lineage_enforcement`      | C     | Strict invariants, activated only after compatible writers exist.                      |
| `0007_lineage_execution_lookup` | F1    | Additive `executions_workspace_run_idx` on `(workspace_id, run_id)`. Filter path only. |

The strict review rules need writers that set `decided_at`, `consumed_at`, and the decision link, so `0006` shipped only after the C1 writers. Readiness requires `0007_lineage_execution_lookup` (Slice F1). Lineage revisions have no destructive downgrade. `0001` to `0006` are not edited.

**Binding Slice C / `0006` requirements (1 and 2 recorded at Slice B1, 3 at C1B; `0005` is applied and is not edited).**

1. **Execution history survives decision deletion.** `executions.guard_decision_id` uses a compatibility-era `ON DELETE CASCADE` in `0005`. Before lineage writers activate, `0006` must replace it with NO ACTION or RESTRICT semantics, so deleting an individual guard decision can never silently delete execution history. If the normal run or action cascade needs DEFERRABLE behavior or explicit ordering, Slice C proves that. A decision deletion must not be allowed to erase execution history to make the cascade work.
2. **Producer provenance after cutover.** After the Slice C writer cutover, every new model-produced action must carry `producer_provider`, `producer_model`, and `producer_prompt_version`. `producer_response_id` stays optional. `0006` must also prevent a non-NULL `producer_response_id` from existing without the producer trio. Historical and in-flight NULL rows stay valid.

3. **`workspaces.policy_revision` preflight (recorded at C1B).** `guard_decisions.policy_revision_observed` must be trimmed and 1 to 80 characters, but `workspaces.policy_revision` has no such CHECK. A workspace whose value is empty, padded, or longer would make the guard's BLOCK fail to persist and end the run as `lineage_write_failure`. Before `0006` freezes strict lineage behavior, C2 must inspect every existing `workspaces.policy_revision` for compatibility with trimmed and length 1 to 80, and must not silently rewrite a malformed historical value. C2 then decides from the contracts and the actual data whether the source column itself receives a compatible database CHECK. C1B does not change the column and adds no such CHECK.

**Slice C2 result (IMPLEMENTED in `0006_lineage_enforcement`).**

1. **Execution history survives decision deletion.** `executions_guard_decision_fk` is now `ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`. Deleting one linked guard decision is rejected and the execution survives. The run and action cascades still succeed. Deferral is a robustness choice, not a requirement: a probe showed the cascade also succeeds with immediate NO ACTION, because the ordering of PostgreSQL's referential triggers is not something the schema should rely on.
2. **Producer provenance.** The trio is required for every new action by trigger, a `producer_response_id` cannot exist without it (validated CHECK), and the response id stays optional. Historical NULL rows are untouched.
3. **Policy revision.** Preflight over every `workspaces.policy_revision` found no incompatible value in the development database and none in the disposable test database. No contract permits a wider shape, because the guard compares the revision with the fixed policy label. `workspaces_policy_revision_shape` was therefore added, validated, with the same rule as `guard_decisions.policy_revision_observed`. It never classifies as `lineage_write_failure`. Note: the one-argument `btrim` trims space characters only, not tabs or newlines. The check therefore enforces "no leading or trailing space", the same as `guard_decisions.policy_revision_observed`, and not a general whitespace rule. This is recorded, not changed, in Slice D.

Also enforced, for new rows: a review carries `requested_at` and, by commit, a REVIEW decision that references it. Review decision and consumption are one-way transitions, and a new execution requires its link. A decision for an action that has a review carries that review. Nothing was backfilled and no column became `NOT NULL`.

**Slice C1 implementation notes (IMPLEMENTED on `0005`).**

- `GUARD_VERSION = "action-guard/1"` lives in `contracts.py` next to `POLICY`. It is a label only.
- Every persisted `authorize()` evaluation appends one `guard_decisions` row in the same transaction as the transition it supports. The ordinal is `COALESCE(MAX(ordinal),0)+1` for the action under the existing action row lock. A new REVIEW creates the review (with `requested_at = now()`) before its decision. A decision after an approval references that same review. An ALLOW execution stores the exact ALLOW decision id.
- `decide_review` writes `decision`, `reviewer`, and `decided_at = now()` in one UPDATE. Consumption sets `consumed` and `consumed_at` together, only on the path that executes. An approval followed by a revalidation BLOCK is not consumed, which matches existing semantics.
- New model-produced actions store the provider, the requested model, the prompt version, and the response id. A missing or malformed provider, model, or prompt version fails closed as `lineage_write_failure`. An empty, whitespace, or over-200-character response id is stored as NULL, never truncated, and never fails the run. Discarding a non-empty over-200-character id logs one bounded warning with only the run id, the provider, and the stable reason `response_id_too_long`. The raw id is never logged.
- Proposal evidence (1 to 16 canonical ids resolving to nodes of the run) and finding evidence (resolving to a node of the run that was supplied to the model, with the quote present) are validated before anything is persisted. Failure is `invalid_model_evidence` and the run fails.
- `lineage_write_failure` is raised only for a lineage integrity rule rejecting the `guard_decisions` insert, the execution authorization link, or the producer columns, and for an unusable producer trio found by the application. Ticket and other database failures keep `worker_failure`.

**Slice C1B failure-boundary closeout (IMPLEMENTED on `0005`).** C1 mapped every database error on the decision insert to `lineage_write_failure`, and matched the execution link by an error-text substring. C1B replaced both with `vetoq/lineage_failure.py`:

- Identity is the server's structured diagnostics, never message text. A write is classified only for SQLSTATE class 23 on the write's own table with a named lineage constraint, or SQLSTATE `P0001` whose primary message is exactly the machine code of a lineage trigger for that write. The primary message is not translated by `lc_messages`.
- Decision insert (`guard_decisions`): the checks `guard_decision_ordinal`, `_verdict`, `_reasons`, `_digest`, `_policy_revision`, `_version`, and `_review_link`, the uniques `guard_decisions_unique_ordinal` and `_unique_action_decision`, the foreign keys `guard_decisions_action_digest_fk` and `_review_fk`, and the trigger codes `guard_decision_ordinal_invalid` and (`0006`) `guard_decision_review_link_required`.
- Execution link (`executions`): the foreign key `executions_guard_decision_fk` and the trigger codes `invalid_execution_guard_decision` and (`0006`) `execution_guard_decision_required`. Every other execution constraint, such as the ticket foreign key or one execution per action, is not lineage.
- Producer columns (`actions`): the checks `action_producer_triplet`, `_provider_length`, `_model_length`, `_prompt_version_length`, and `_response_id_length`, and (`0006`) the check `action_producer_response_requires_trio` and the trigger code `action_producer_required`. The application validates the trio first, so this is a database backstop.
- Not classified: `OperationalError` (statement timeout, cancellation, lock-not-available, connection loss, admin shutdown), an integrity error on a ticket or any other table or constraint, a NOT NULL violation, evidence or immutability trigger codes, and any error without a PostgreSQL SQLSTATE. These propagate and end the run as `worker_failure`, and the transaction rolls back.
- A later migration that renames or replaces one of these identities must update the classifier. A test confirms every named identity exists in the schema.

## Lineage read service (IMPLEMENTED in Slice D, exposed in Slice E)

The typed read model and its service are exposed by the Slice E endpoints below. There is no UI. Modules: `lineage_model.py` (typed model), `lineage_read.py` (snapshot reader and entry points `build_run_lineage`, `build_action_lineage`, `build_node_lineage`), `lineage_assemble.py` (pure assembly), `lineage_graph.py` (bounded graph analysis). The workflow and the Action Guard do not import them, and a test enforces that.

- **Snapshot.** One `REPEATABLE READ, READ ONLY` transaction (`SET TRANSACTION` is its first statement). The run is resolved by `visible_run` inside that snapshot, then exactly nine run-scoped, indexed queries read nodes, edges, steps, findings, actions, decisions, reviews, executions and tickets, plus the database read time. Twelve statements in all, regardless of run size. No N+1, no recursive SQL, no audit event input. Content bodies are compared inside PostgreSQL (`sha256(convert_to(content,'UTF8')) = digest`, and the octet length) and are never returned.
- **Pure assembler.** Rows go to `assemble(Snapshot, bounds)`, which touches no database. A hand-built snapshot therefore proves the checks for inconsistencies the schema forbids.
- **Entities.** `goal_lock:<run_id>`, `content:<id>`, `finding:<id>`, `proposal:<action_id>`, `guard_decision:<id>`, `review:<id>`, `execution:<id>`, `ticket:<id>`. Metadata only: no content body, ticket title or body, finding explanation, quote, or model text.
- **Relationships and basis.** `structural_fk`, `digest_bound_json` (the evidence ids and envelope inside the action digest), `derived_join` (`findings_on_cited_evidence`, structural co-location, not model reliance), `envelope_binding` (Goal Lock to source), and `not_recorded` (an unlinked execution). `run_scope_aggregate` was not needed and is not implemented.
- **Integrity.** The production `action_digest` is recomputed and compared with the stored digest (`consistent`, `inconsistent`, or `unverifiable` when the Goal Lock or proposal cannot be parsed). Decisions, reviews and executions are checked for digest, review link, contiguous ordinals, the verdict cache, the timeline, scope, and the authorization link. Graph anomalies are `orphan_derived_node`, `edge_cycle` (iterative Tarjan), `unreachable_node`, `content_digest_mismatch`, `content_size_mismatch`, and `bound_exceeded`.
- **Stages.** `proposed`, `review_pending`, `blocked`, `authorized`, `executed`, `verified`, `expired`, `cancelled`, `failed`, and the legacy `latest_only`. `verified` requires an execution with a recorded `verified_at`, never only a run state. A run-terminal state applies to the latest action only. `path.complete` is true only when the stage is `verified`, every path step is `consistent`, and no integrity finding names an entity on the path.
- **Bounds.** Nodes 300, edges 300, steps 1200, findings 2730, actions 8, decisions 16, reviews 8, executions 8, tickets 8, evidence ids 16, traversal depth 3. Each query asks for one row more than its cap, so a clipped set is reported in `bounds.truncated_sets`, never silently. A capped set makes the checks that depend on it `unverifiable`, not falsely inconsistent. Observed counts are the loaded counts. Slice F pinned these caps against every still-supported write path (`write_path_maxima()` in `lineage_model.py`). M002 legacy `inspect()` does not enforce `derived_representations_per_run`; it fans out at most 16 Base64 children per node for derivation depth 2, so the node maximum is `1 + 16 + 256 = 273`. M003 is count-capped at 33. M004 writers add no content nodes. Edges 272, steps 1088, findings `9 × 273 + 30 = 2487`, actions 3 (`runs.proposals` CHECK / `GoalLock.max_proposals`), decisions 12 (`3 × 4` attempts), reviews 3, executions 3, tickets 1 (`tickets.run_id` UNIQUE), evidence ids 16, traversal depth 2. Every focused-identity cap is ≥ its legal maximum, so a valid node or action cannot be hidden as `404` by truncation under current contracts. Findings remain a diagnostic set that may truncate if constructed above the legal maximum. A truncated HTTP read is still `200`.
- **Query inventory.** One run, node, or action lineage read uses twelve statements regardless of run size: `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`, the canonical visible-run lookup, the database read time, and nine capped run-scoped sets. There is no N+1 and no recursive SQL. Every set query predicates `workspace_id` and `run_id` from the trusted run. `content_nodes`, `content_edges` (parent and child), `content_edge_steps` through the edge relation, `findings`, `actions`, `guard_decisions`, `reviews`, `tickets`, membership/workspace visible-run lookup, and `executions` have an index path under `enable_seqscan = off`. Slice F1 added `executions_workspace_run_idx` on `executions (workspace_id, run_id)`. That is an access-path fact, not a scale claim. A tiny table may still seq-scan when sequential scan is allowed.
- **Observability.** One `lineage_read_completed` key=value INFO event on the existing `vetoq.api` logger per successful HTTP lineage read (`lineage_observe.py`). Allowed fields: correlation id, kind, authorized run id, duration, counts, truncation, bounded anomaly codes (at most 16 unique). Forbidden: bodies, ticket text, finding explanations, Goal Lock or proposal free text, producer response ids, SQL, exceptions, workspace names, principal identifiers. A 404 is not logged. Unexpected failures stay with the global exception handler. There is no metrics abstraction; directional counters remain M013/M014 work. OBS-001 stays PARTIAL.
- **Failure and audit independence.** A read changes no run state, authority, execution, audit or lineage row and adds no failure code. The service does not read `audit_events`, and a test proves it.

## Public lineage API (IMPLEMENTED in Slice E)

The authoritative contract is [the API contract](../API_CONTRACT.md). In summary:

- Three GET routes: `/api/v1/runs/{run_id}/lineage`, `.../lineage/nodes/{node_id}?direction=ancestors|descendants|both`, and `.../lineage/actions/{action_id}`. All are authenticated, read-only, `no-store`, and run scoped by the canonical visibility rule. Every refusal is the same non-enumerating `404 not_found`.
- `lineage_routes.py` only calls the Slice D service and serializes. It holds no SQL and no lineage meaning. `lineage_views.py` is the projection layer: it gives the relationships and integrity findings an explicit order and selects the node and action views from the one assembled lineage, using the Slice D traversal helper. Retention, legacy state, integrity, the verified path, relationships and stage are decided only by the assembler.
- Response models are the Slice D Pydantic models plus `NodeLineageView` and `ActionLineageView`. Server bounds are authoritative. A caller supplies only the traversal direction.
- Metadata only. No content body, ticket text, finding explanation, or model text. Audit events are not read, so lineage is served when a run has no audit events.
- `removed_by_retention` is reserved and is never emitted.
- The routes are not imported by the workflow or the Action Guard, and a test enforces that.
- The existing same-origin BFF proxy forwards these GET paths and the `direction` query without change. BFF tests prove the forwarding, the unchanged error bodies, the `no-store` header, and that no client workspace or other header reaches the API.

Slice F is the security, retention, query-plan, and observability shield over this API. It added no product feature, no UI, no graph library, and no migration. Unknown query parameters are ignored by FastAPI and cannot change authorization or bounds. Unsupported methods return FastAPI's normal `405`. A configured but unreachable database remains `500 internal_error` for lineage and every other route; only `database_not_configured` is `503`. That 500-versus-503 split is a known ops hardening item, not a lineage-only special case.

Not part of Slice F1: UI, visualization, a metrics platform, or any index beyond `executions_workspace_run_idx`. Slice G is the populated rehearsal and capability closeout.

## UI and visual scope

There is no UI work in slices A to G. M004 prioritizes backend, database integrity, security, lineage persistence, query correctness, tenancy, recovery, tests, and runtime proof.

The final premium VETOQ visual redesign is deferred. A future visualization may consume the typed lineage API. Lineage data must remain fully usable without animation or specialized graphics. No GSAP, Three.js, graph library, or design dependency is selected here.

## Performance principle

M004 makes no scale claim. Run-local queries are bounded and PostgreSQL-first. M014 owns scale and load evidence.

Future visual sophistication must never materially degrade responsiveness, input latency, accessibility, mobile usability, battery use, bundle size, or the reduced-motion experience.

## Implementation slices

Every slice required its own GREEN A and human review before the next began. There is no UI slice in A to G. All listed slices are complete at GREEN B.

| Slice | Work                                                                                        |
| ----- | ------------------------------------------------------------------------------------------- |
| A     | Contracts, ADR, and change control. Docs only. This slice.                                  |
| B     | `0005` additive lineage schema, compatibility guards, and schema proof.                     |
| C     | C1 and C1B writers and failure boundary. C2 `0006` strict enforcement. C2 done.             |
| D     | Canonical visibility helper and the lineage read service. D implemented.                    |
| E     | Typed run, node, and action lineage APIs. E implemented.                                    |
| F     | Security, retention, query-plan, and observability shield. F implemented.                   |
| F1    | `0007_lineage_execution_lookup` executions run-scoped index. F1 implemented.                |
| G     | Full verification, populated-database rehearsal, docs, and capability closeout. G complete. |

## Capability status

| ID        | GREEN B status | Bound                                                                                      |
| --------- | -------------- | ------------------------------------------------------------------------------------------ |
| PROV-001  | IMPLEMENTED    | Exact approved sentence in change record 0002. No cross-run provenance. No retained graph. |
| LINE-001  | IMPLEMENTED    | Exact approved sentence in change record 0003. Lineage is never an authorization input.    |
| OBS-001   | PARTIAL        | Bounded lineage-read logging is not a metrics platform.                                    |
| SEC-001   | PARTIAL        | Production security program beyond the implemented slice controls.                         |
| UX-001    | PARTIAL        | No UI work is in this module.                                                              |
| A11Y-001  | PARTIAL        | No UI work is in this module. Automated checks are not WCAG certification.                 |
| MULTI-001 | PLANNED        | Not M004.                                                                                  |
| PERF-001  | PLANNED        | M014 owns scale.                                                                           |

The approved sentences do not claim a lineage UI, cross-run lineage, retention deletion proof, certification, or production scale.

## Release criteria for GREEN B

These criteria were required and are met at GREEN B, on the disposable database and then on a populated upgrade rehearsal:

- Both migrations apply from a fresh install and upgrade from a populated M003 database with row counts unchanged and legacy columns NULL.
- Every persisted deterministic guard evaluation has a decision row written atomically with its transition. A write failure leaves no ticket and no side effect.
- The guard and `authorize()` do not read lineage tables as an input.
- Review, execution, and ticket transition rules, the review structural links, and the execution authorization link are enforced and tested.
- Proposal and finding evidence ids that are malformed fail as `invalid_model_evidence` and persist no executable action.
- Every lineage read is workspace and run scoped, non-enumerating, and bounded. Inactive-workspace reads return 404.
- Retention states are exact, and no deleted content graph is fabricated.
- The lineage response contains no content body, finding explanation, ticket text, or model free text.
- `pnpm verify` passes. No scale claim is made.

## Non-goals

Cross-run, cross-workspace, or global lineage. A graph database or any new infrastructure. Tombstone content, a second content body, or any new retention window or policy. Backfill from audit. Multi-agent topology, specialist roles, reasoning traces, or agent thought process. Changes to the Goal Lock, Action Guard decisions, review semantics, or model privileges. Hardening of `decide_review` or `cancel`. Any UI, visualization framework, or design dependency.

## Open later work

- The broader retention policy for runs, actions, reviews, tickets, executions, and M004 metadata.
- Hardening of `decide_review` and `cancel` for an inactive workspace.
- A cross-run or global lineage product, if ever wanted.
- Multi-agent and specialist-agent provenance (M005).
- The premium lineage visualization.
- Scale and load evidence (M014).
