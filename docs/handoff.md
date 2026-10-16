# Agent handoff

**M003 is GREEN B. M004 is GREEN B.** INGEST-001, PROV-001, and LINE-001 are IMPLEMENTED for their approved sentences. Schema readiness is `0007_lineage_execution_lookup`. There is no lineage UI. OBS-001, SEC-001, UX-001, and A11Y-001 stay PARTIAL. Do not start M005.

## M004 Slice G — final release shield and GREEN B closeout (16 October 2026)

**Scope.** Verification, populated rehearsal, contract reconciliation, and capability closeout. No product feature, no lineage UI, no M005, no new infrastructure, no Action Guard or authority change, no Git mutation.

**IMPLEMENTED TODAY.** Accumulated M004 (slices A–F1) plus this closeout. Fresh `base→0007` rehearsal, populated `0004→0005→0006→0007` rehearsal with historical NULL states preserved, schema parity of fresh / upgraded / `vetoq_test` / development, real FastAPI+PostgreSQL lineage proofs, live Groq producer provenance, Clerk-authenticated browser E2E including BFF submission, and canonical `pnpm verify`. PROV-001 and LINE-001 are IMPLEMENTED for the exact change-control 0002/0003 sentences.

**Verification (16 October 2026, Windows).** `pnpm verify` from repository root: Prettier clean; ESLint `--max-warnings 0`; `next typegen && tsc --noEmit`; Vitest 66 passed (8 files, 19.08 s); Next.js 16.4.0 production build succeeded; `uv run --locked` Ruff check clean, Ruff format 78 files, mypy strict clean on 70 source files, Pytest 775 passed / 0 skipped in 220.94 s; Playwright 111 passed / 0 skipped in 17.7 m on Chromium, Firefox, and WebKit. Focused backend before that run: Pytest 775 passed in 136.17 s. Live Groq smoke: COMPLETED / ALLOW / verified / producer trio `groq` + `openai/gpt-oss-120b` + `support-analysis/1` / response id present and normalized / execution linked / lineage path complete. Browser E2E required an operator membership for the configured Clerk test user on `vetoq_test` (development `vetoq` was not reset). No new runtime dependency. OBS-001 and SEC-001 stay PARTIAL. A11Y-001 stays PARTIAL: automated axe A/AA on existing public/auth/workbench flows, not WCAG certification.

**Still NOT implemented.** Lineage UI, metrics platform, `removed_by_retention` as a reachable state, cross-run lineage, mutation active-workspace hardening beyond approved reads, M005 specialists, production scale evidence, GA.

**Next authorized task.** Human acceptance of M004 GREEN B. Do not start M005 from this note.

## M004 Slice F1 — executions run-lookup index (16 October 2026)

**Scope.** One additive index for the lineage reader's existing executions query. No semantic change, no UI, no BFF, no Action Guard change, no other index, no Git change.

**Query reconfirmed.** `lineage_read._EXECUTIONS` is:

```sql
SELECT id,workspace_id,run_id,action_id,ticket_id,digest,committed_at,verified_at,
       guard_decision_id
FROM executions WHERE workspace_id=:workspace AND run_id=:run
ORDER BY committed_at,id LIMIT :limit
```

Slice F EXPLAIN with `enable_seqscan = off` had no `(workspace_id, run_id)` index path. Unique `action_id` / `ticket_id` cannot serve that filter. The approved two-column index is sufficient for the filter. `committed_at` and `id` were not added: they are the sort, not the tenant/run predicate.

**IMPLEMENTED TODAY.** `apps/api/migrations/versions/0007_lineage_execution_lookup.py` (down revision `0006_lineage_enforcement`, the only head). Index `executions_workspace_run_idx` on `executions (workspace_id, run_id)`. Downgrade raises `RuntimeError`. No backfill, no constraint, no trigger, no row rewrite. `SCHEMA_REVISION` and readiness are `0007_lineage_execution_lookup`.

**Verification (16 October 2026, Windows).** Fresh scratch `base→0007` one head. Populated `0006→0007` row counts unchanged. Disposable `vetoq_test` and development `vetoq` upgraded additively; business table counts identical; existing executions indexes retained; `executions_workspace_run_idx` added. Schema parity of fresh, upgraded, `vetoq_test`, and development passed. From `d:\vetoq\apps\api`, `uv run --locked`: `ruff check` clean, `ruff format --check` 78 files formatted, `mypy` strict clean on 70 source files, `pytest -rs` 775 passed, 0 skipped, 129.77 s. No web production change. Playwright and `pnpm verify` were not run.

**Still NOT implemented.** Lineage UI, metrics platform, Slice G closeout, cross-run lineage, `removed_by_retention`. PROV-001, LINE-001, and OBS-001 stay PARTIAL.

**Next authorized task.** Human review of Slice F1, then a GREEN A for Slice G. Do not start Slice G from this note.

## M004 Slice F — security, retention, query-plan, and observability shield (15 October 2026)

**Scope.** A shield over the completed M004 persistence, read, and API system. No product feature, UI, graph library, Action Guard change, retention marker, or migration. Schema stays `0006_lineage_enforcement`. Lineage remains evidence of what happened and is never authority.

**IMPLEMENTED TODAY.**

- Authority independence: `action_guard.py` and `workflow.py` import none of the lineage read/API/observe modules. `GuardInput` has no lineage fields. Workflow writes `guard_decisions` as output (one INSERT plus ordinal allocation) and never reads the lineage service to grant ALLOW, REVIEW, or execution. A lineage HTTP read changes no run, action, review, execution, ticket, audit, or failure field.
- Same-tool Goal Lock: workspace A / `tickets.create` / destination A is ALLOW, persisted, ticketed, executed, and verified. The same principal and tool aimed at workspace B is BLOCK / `GOAL_SCOPE_MISMATCH`, with zero tickets and zero executions in B. Lineage reports both outcomes and changes neither.
- Tenancy: unauthenticated is 401; inactive membership, inactive workspace, foreign workspace, foreign run, missing run, missing/malformed/foreign node or action ids, and a valid id belonging to another visible run are all `404 not_found`. Unknown query parameters (`workspace_id`, `depth`, `limit`, `unlimited`, `include_body`, `include_audit`) are ignored by FastAPI and cannot change authorization, bounds, or bodies. Direction is the only node traversal selector. OpenAPI generated from `app.openapi()` exposes only `run_id`, `node_id`, `action_id`, and `direction`. POST/PUT/PATCH/DELETE return FastAPI 405 with `no-store`.
- Cap proof, Case A. Still-supported write-path maxima: nodes 273 (`1 + 16 + 256` M002 Base64 fan-out; M003 is 33; M004 adds none), edges 272, steps 1088, findings 2487, actions 3, decisions 12, reviews 3, executions 3, tickets 1, evidence ids 16, traversal depth 2. Server caps are 300 / 300 / 1200 / 2730 / 8 / 16 / 8 / 8 / 8 / 16 / 3. Every focused-identity cap is ≥ the legal maximum, so a valid node or action cannot be hidden as 404 by truncation. No focused-lookup redesign. Formulae live in `lineage_model.write_path_maxima()`.
- Cross-run lookup: every set query predicates trusted `workspace_id` and `run_id`. Focus helpers do no SQL. No global-id-then-compare-run shape.
- Query inventory: twelve statements per run, node, or action read (`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`, visible run, read time, nine capped sets). No N+1, no recursive SQL, no `FOR UPDATE`. Index path exists under `enable_seqscan = off` for visible-run lookup, `content_nodes`, `content_edges`, `content_edge_steps`, `findings`, `actions`, `guard_decisions`, `reviews`, and `tickets`. Slice F found that `executions` had no `(workspace_id, run_id)` index. Slice F1 added `executions_workspace_run_idx`.
- Retention: D1 states re-proven. Aged eligibility tests INSERT `runs.created_at` already past the window. `immutable_run` stays enabled (`tgenabled = O`). `removed_by_retention` is never emitted. Real `vetoq retain` after eligibility is `unverifiable`.
- Observability: `lineage_observe.py` emits one `lineage_read_completed` key=value INFO event on the existing `vetoq.api` logger per successful HTTP lineage read. Fields: correlation id, kind, authorized run id, duration_ms, counts, truncated, truncated_sets, anomaly_count, anomaly_codes (at most 16 unique). A 404 is not logged. Unexpected failures stay with the global exception handler. No metrics abstraction exists; none was invented. OBS-001 stays PARTIAL.
- Public errors: the Exception handler envelope is `internal_error` with no SQL, host, constraint, traceback, secret, or source body. TestClient in this stack re-raises unhandled exceptions; the envelope is proven by invoking the handler directly. Configured-but-unreachable database stays `500` for lineage and every other route; unconfigured is `503`. That split is a known ops hardening item, not a lineage-only special case.
- Diagnostic assembly of the legal M002 fan-out (273 nodes, 272 edges, 1088 steps, metadata only): about 11 ms and 331 987 bytes in this environment. Not an SLA. Not a production maximum. M014 owns load evidence.
- BFF production code unchanged. One additional Vitest proves extra query parameters are forwarded without a body or workspace header; backend authority still ignores them.

**Judgment calls.** (1) Case A: retain focused 404 because no still-supported writer can exceed the node or action cap. (2) Do not special-case lineage 500-versus-503. (3) The executions index waited for human approval and is Slice F1. (4) Do not invent a metrics backend. (5) Do not log 404 selectors. (6) INSERT-aged `created_at` is the supported D1 construction; the trigger is UPDATE/DELETE only.

**Verification (15 October 2026, Windows, disposable `vetoq_test`).** From `d:\vetoq\apps\api`, `uv run --locked`: `ruff check` clean, `ruff format --check` 77 files formatted, `mypy` strict clean on 70 source files, `pytest -rs` 773 passed, 0 skipped, 125.07 s. Focused shield `tests/test_lineage_shield.py`: 23 passed. M004 regression group (API, read, assemble, enforcement, failure-boundary, writers, schema, visibility): 425 passed. Web: focused Vitest on the BFF route test 21 passed, ESLint `--max-warnings 0`, `next typegen && tsc --noEmit`, Prettier on the edited test. No production web code changed, so the production build and Playwright were not run. `pnpm verify` was not run. Slice G owns the repository release shield.

**Still NOT implemented (at Slice F).** Lineage UI or visualization, a metrics platform, populated-database rehearsal and capability closeout (Slice G), cross-run lineage, `removed_by_retention`. The executions index is Slice F1. PROV-001, LINE-001, and OBS-001 stay PARTIAL.

**Next authorized task.** None for F. It passed human review except the executions index, which is Slice F1.

## M004 Slice E — typed public lineage APIs and BFF passthrough (15 October 2026)

**Scope.** Three authenticated, typed, read-only lineage endpoints over the Slice D service, with API tests and BFF compatibility tests. No migration, UI, writer change, Action Guard change, retention change, dependency, or Git change. Schema stays `0006_lineage_enforcement`.

**IMPLEMENTED TODAY.**

- `GET /api/v1/runs/{run_id}/lineage` returns `RunLineage`. `GET .../lineage/nodes/{node_id}?direction=ancestors|descendants|both` returns `NodeLineageView`. `GET .../lineage/actions/{action_id}` returns `ActionLineageView`. The contract is in [API_CONTRACT.md](API_CONTRACT.md).
- `vetoq/lineage_routes.py` (new, its own router included by `main.py`) calls `build_run_lineage` and serializes. It has no SQL and no lineage meaning. `vetoq/lineage_views.py` (new) holds the two focused view models and the pure projections, plus `canonical()`, which orders relationships and integrity findings explicitly. `vetoq/lineage_read.py` gained two pure helpers, `focus_node` and `focus_action`, extracted from `build_node_lineage` and `build_action_lineage` so there is one traversal and one lookup. `routes.fail` is now typed `NoReturn`.
- Visibility is the Slice D rule, applied inside the service. Every refusal is the same `404 not_found`. A caller supplies only `direction`. The server bounds are fixed in `lineage_routes.SERVER_BOUNDS`.
- BFF: no production change. The generic `[...path]` proxy already forwards the three paths and the `direction` query with the server-side token and a fresh `X-Request-ID`, and sets its own `no-store`. Eight new Vitest tests prove it.

**Judgment calls.** (1) The path ids are persisted ids without the entity prefix. The BFF segment rule rejects `:`, so a prefixed id is `400 invalid_path` there and `404` at the API. (2) The action view excludes other actions even when they cite the same evidence. (3) The node view's `integrity` is the findings that name an entity in the view plus every run-level finding, so a focused view never hides a run-level anomaly. (4) A configured but unreachable database is `500 internal_error`, as for every existing route. Only `database_not_configured` is `503`. This was not changed. (5) The application still serves no OpenAPI document. The generated schema is tested instead. (6) Legacy states that no current writer can produce are reached by altering the rows of a real read snapshot, so the real route and visibility rule stay in the loop. (7) Serialized-size and query-plan evidence were left to Slice F.

**Verification (15 October 2026, Windows, disposable `vetoq_test`).** `uv run --locked ruff check`, `ruff format --check`, `mypy` (68 source files), and `pytest -rs`: 750 passed, 0 skipped, 182 s. New file `tests/test_lineage_api.py` has 28 tests. Web: focused Vitest on the BFF route test (20 passed, 8 new), ESLint (`--max-warnings 0`), `next typegen && tsc --noEmit`, and Prettier on the edited test. No production web code changed, so the production build and Playwright were not run. `pnpm verify` was not run.

**Still NOT implemented (at Slice E).** Lineage UI or visualization, observability and query-plan evidence (later Slice F), populated-database rehearsal and release evidence (Slice G), cross-run lineage, `removed_by_retention`. PROV-001 and LINE-001 stay PARTIAL.

**Next authorized task.** None for E. It passed human review.

## M004 Slice D1 â€” retention truthfulness closeout (15 October 2026)

**Scope.** One read-model correctness fix and its tests and docs. No route, BFF, UI, migration, retention writer, Action Guard, or lineage writer change.

**Finding.** Slice D emitted `removed_by_retention` from an age plus five-minute heuristic. After deletion no persisted fact proves that `retain` deleted the content. `retain` runs only `DELETE FROM content_nodes WHERE expires_at<=now()`. It writes no audit event, marker, tombstone, or counter. Elapsed time proves eligibility, not cause.

**IMPLEMENTED TODAY.** The five-minute allowance is removed, and no other grace period replaces it. Eligibility is `read_time >= runs.created_at + 24 hours`. States: source present and unexpired is `available`. Present and expired is `expired_body_pending_deletion`. Absent before eligibility is `inconsistent` (`source_missing_before_retention`). Absent at or after eligibility is `unverifiable` (`source_missing_retention_unverifiable`). Absent while other content remains is `inconsistent` (`source_missing_with_graph_present`). `source_node_absent` and `retention_inconsistent` were replaced by these codes. `removed_by_retention` stays in the model enum as a documented, **currently unreachable** reserved state and is never emitted. Making it reachable needs a new durable fact written by retention, which is a writer and schema change and is not authorized in M004. An absent source has no synthesized nodes, edges, steps, findings, or transform history. Goal Lock source facts, evidence ids (`unresolved`), and action, decision, review, execution and ticket facts are presented as stored.

**Tests.** Assembler tests cover each state, the exact boundary (exactly 24 hours and 24 hours plus one minute are unverifiable, and 24 hours minus one minute is inconsistent), no grace period, and that `removed_by_retention` is never emitted for any age. Real-database tests cover present, present-and-expired, and a run of the real `vetoq retain` command: before eligibility it ends `inconsistent`, and after eligibility it ends `unverifiable`, with every statement `retain` executed being a `DELETE`. The disposable database cannot wait 24 hours. Slice F rewrote the aged-run fixture to INSERT `runs.created_at` already aged; `immutable_run` is an UPDATE/DELETE trigger and is never disabled. The D1 DISABLE TRIGGER construction is superseded.

**Still NOT implemented.** Lineage routes, BFF, UI, retention proof, Slices E to G. PROV-001 and LINE-001 stay PARTIAL.

**Next authorized task.** None for D1. It passed human review.

## M004 Slice D â€” canonical run visibility and lineage read service (15 October 2026)

**Scope.** Canonical active-workspace visibility for the existing run reads, plus an internal, run-scoped, bounded lineage read service. No public lineage route, BFF change, UI, migration, dependency, writer change, or Action Guard change.

**IMPLEMENTED TODAY.**

- `vetoq/visibility.py`: `visible_run(connection, run_id, principal)` requires an active membership, an active workspace, and a matching run, else a non-enumerating `404 not_found`. It is used by `get_run`, `get_events`, `get_content`, and `get_ticket`. Every later query in those routes uses the trusted run's `workspace_id` and `id`. A ticket is read through its run. `decide_review`, `cancel`, `list_runs`, and `/me` are unchanged. Behavior change: a run of an inactive workspace is no longer readable by id.
- `vetoq/lineage_model.py`, `lineage_read.py`, `lineage_assemble.py`, `lineage_graph.py`: the internal service (`build_run_lineage`, `build_action_lineage`, `build_node_lineage`). One `REPEATABLE READ, READ ONLY` snapshot, twelve statements regardless of run size (transaction mode, run visibility, read time, nine capped run-scoped sets), a pure assembler, an iterative Tarjan cycle check and bounded BFS. No audit input, no content body, ticket text, finding explanation, or model text in the output. Details are in [modules/004-provenance-lineage.md](modules/004-provenance-lineage.md).
- Caps: nodes 300, edges 300, steps 1200, findings 2730, actions 8, decisions 16, reviews 8, executions 8, tickets 8, evidence ids 16, traversal depth 3. A capped set is reported in `bounds.truncated_sets` and makes dependent checks `unverifiable`.
- Retention (corrected in D1): an absent original is `inconsistent` if `read_time < runs.created_at + 24 hours` (or other content remains), and `unverifiable` otherwise. `removed_by_retention` is a reserved, currently unreachable state, because `retain` writes no durable fact. See the Slice D1 section.
- Legacy versus anomaly: decided from provable relations (a recorded producer trio, an ALLOW decision, a NULL step count), never from one NULL. A fact never stored is `not_recorded`.
- The `policy_revision` one-argument `btrim` note (spaces only) is recorded in the module specification.

**Judgment calls.** (1) The Slice D five-minute retention allowance was withdrawn in D1. (2) `not_recorded` is not a retention state, because the node expiry is never NULL. (3) `run_scope_aggregate` was not needed as a relationship basis and is not implemented. (4) Observed counts are the loaded (capped) counts, so a truncated set shows its cap. (5) A real run cannot reach several anomalies because the schema forbids them, so those checks are proven on hand-built snapshots against the pure assembler. (6) The current pipeline records parser identity and transform steps even when the source row is a legacy M002 row, so real legacy-NULL derived rows are covered by assembler tests only.

**Tests.** New `tests/test_lineage_assemble.py` (pure, 49 tests), `tests/test_lineage_read.py` (real PostgreSQL, 24 tests), and `tests/test_run_visibility.py` (7 route tests). They cover visibility, tenant isolation, inactive membership and workspace, bounds, retention, legacy, integrity, the snapshot and read-only guarantees, audit independence, the fixed query count, the same-tool Goal Lock regression, and the static authority boundary (the workflow and Action Guard do not import the read side, and no lineage route exists).

**Verification (from `d:\vetoq\apps\api`, `uv run --locked`, against the disposable `vetoq_test`).** `ruff check` clean, `ruff format --check` 72 files formatted, `mypy` strict clean on 65 files, `pytest` 716 passed, 0 skipped, 156s. The new suites alone: 80 passed. No Playwright or root `pnpm verify` ran, and no UI or browser claim is made.

**Still NOT implemented (at Slice D).** Lineage routes, BFF passthrough, UI, cross-run lineage, observability (Slice F). Slice E later added the routes (see above).

**Next authorized task.** None for Slice D. It passed human review.

## M004 Slice C2 â€” `0006_lineage_enforcement` (15 October 2026)

**Scope.** Strict database rules for new rows only, matching what the C1 writers already do. No runtime redesign, no `0005` edit, no lineage read or API, no BFF, no UI, no new dependency or infrastructure.

**IMPLEMENTED TODAY.** `apps/api/migrations/versions/0006_lineage_enforcement.py` (down revision `0005_provenance_lineage`, the only head). `SCHEMA_REVISION` and readiness require `0006_lineage_enforcement`. Downgrade raises `RuntimeError`. No backfill, no global `NOT NULL`, no historical rewrite.

- `workspaces_policy_revision_shape` CHECK (trimmed, 1 to 80), validated. Preflight: 22 of 22 development and 0 offending test values.
- Reviews: `requested_at` required by insert trigger. A deferred constraint trigger requires a REVIEW decision referencing the review by commit. `protect_review` freezes identity, digest, expiry, and `requested_at`. The decision (decision, reviewer, `decided_at`) is one all-or-nothing transition. Consumption is one transition that needs `consumed_at` and an `approve` decision. A legacy review can still be decided and consumed. Legacy states (decision without `decided_at`, consumed without `consumed_at`) survive and cannot be rewritten.
- Executions: the link is required for new rows and still exact. `executions_guard_decision_fk` is `ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`. Direct decision deletion is rejected (the execution survives). Run and action cascades succeed. Retention is unchanged.
- Actions: the producer trio is required by insert trigger. `action_producer_response_requires_trio` is a validated CHECK. The response id stays optional. Producer fields stay immutable and outside the action digest.
- Guard decisions: a decision for an action that has a review must carry that review. Straight ALLOW and BLOCK carry none. History stays output-only (the static authority-boundary test is retained).
- Classifier (`lineage_failure.py`): new trigger codes only for required structural lineage writes: `guard_decision_review_link_required`, `execution_guard_decision_required`, `action_producer_required`, and the check `action_producer_response_requires_trio`. No string matching. The policy-revision CHECK and the review request-time rule are not `lineage_write_failure`.

**Judgment calls.** (1) The link FK is `DEFERRABLE INITIALLY DEFERRED`. A probe showed immediate NO ACTION also survives the cascade, so deferral is a robustness choice, not a need. (2) `btrim` removes spaces only, the same rule as `guard_decisions.policy_revision_observed`, so a trailing newline is accepted by both. (3) `vetoq_test` held 7 synthetic response-id-without-trio fixtures from the Slice B tolerance tests, which would make the validated CHECK fail. On the owner's decision, the disposable `vetoq_test` database was dropped and recreated at `0006` from base. The development database `vetoq` was never dropped or reset: it was preflighted clean and upgraded additively.

**Tests.** New `tests/test_lineage_enforcement.py` covers policy shape, review creation, decision and consumption transitions, execution strictness and NO ACTION semantics, direct-delete rejection, run and action cascade success, retention, producer rules and the digest boundary, the decision review link, classifier identities, and a populated 0005 to 0006 upgrade with in-flight fixtures A to G (values and row counts unchanged, legacy rows still usable, new writes strict). The Slice B tolerance tests in `test_lineage_schema.py` were adapted to the strict schema, the head and parity tests moved to 0006, and the C1 writer and C1B failure-boundary suites pass unchanged in behavior.

**Verification (from `d:\vetoq`).** `uv run --locked --directory apps/api` with `ruff check`, `ruff format --check`, `mypy`, and `pytest` against the recreated `vetoq_test`: Ruff clean, 64 files formatted, mypy strict clean on 57 files, Pytest 636 passed, 0 skipped, 77.7s. The four-way schema parity test (fresh, upgraded, `vetoq_test`, `vetoq`) passes. Development `vetoq` row counts for all 13 tables were identical before and after. No Playwright or root `pnpm verify` ran, and no UI or browser claim is made.

**Still NOT implemented.** Lineage read service and APIs, active-workspace visibility, BFF changes, UI, cross-run lineage, Slice D to G. PROV-001 and LINE-001 stay PARTIAL.

**Next authorized task.** Human review of C2, then a GREEN A for Slice D.

## M004 Slice C1B â€” lineage failure-boundary closeout (15 October 2026)

**Scope.** Only the C1A blocker and its directly related tests and docs. No migration, `SCHEMA_REVISION`, Action Guard, review-route, lineage-read, visibility, BFF, or UI change. Schema is still `0005_provenance_lineage`, and `0005` was not edited.

**The blocker.** C1 mapped every `DBAPIError` on the `guard_decisions` insert to `lineage_write_failure`, so a statement timeout, lock failure, or lost connection was mislabeled as a lineage failure. It also classified the execution link by `"guard_decision" in str(error.orig)`.

**IMPLEMENTED TODAY.**

- **Classifier.** New `apps/api/src/vetoq/lineage_failure.py`. `is_lineage_integrity_failure(error, write)` uses psycopg's SQLSTATE and diagnostics, never message text. A failure is a lineage failure only for SQLSTATE class 23 on the write's own table with a named lineage constraint, or SQLSTATE `P0001` whose primary message is exactly the machine code of a lineage trigger for that write.
- **Three writes.** `DECISION_WRITE` (`guard_decisions` constraints plus `guard_decision_ordinal_invalid`), `EXECUTION_LINK` (`executions_guard_decision_fk` plus `invalid_execution_guard_decision`), and `PRODUCER_WRITE` (the five `action_producer_*` checks, a backstop behind the application validator).
- **Everything else keeps its code.** `OperationalError` (statement timeout, cancellation, lock-not-available, connection loss, admin shutdown), a ticket or any other execution integrity error, NOT NULL violations, evidence and immutability trigger codes, and errors with no SQLSTATE propagate and end the run as `worker_failure` with the transaction rolled back. `invalid_model_evidence` and the application-validated producer trio keep their codes.
- **Response id.** Unchanged behavior (empty, whitespace, or over-200-character becomes NULL, never truncated, never fails the run). New: discarding a non-empty over-200-character id logs one warning with only the run id, the provider, and `response_id_too_long`. The raw id is never logged. Whitespace-only and absent ids log nothing.
- **Docs.** `DATA_CONTRACT` (tables, `0005` immutability facts, failure vocabulary, partly-implemented heading), `API_CONTRACT` (`invalid_model_evidence` and `lineage_write_failure` run failure codes), `PRODUCT_CONTRACT` (M004 slice status), and the module specification (classification identities and the C2 preflight). PROV-001 and LINE-001 stay PARTIAL. No lineage API exists.

**Binding C2 preflight (recorded, not implemented).** Before `0006` freezes strict lineage behavior, inspect every existing `workspaces.policy_revision` for compatibility with trimmed and length 1 to 80 (the `guard_decisions.policy_revision_observed` rule). Do not silently rewrite a malformed historical value. C2 then decides from the contracts and the actual data whether the source column receives a compatible CHECK. C1B changed nothing about that column.

**Tests.** New `tests/test_lineage_failure_boundary.py` (36 tests): real PostgreSQL integrity failures for each decision constraint and the ordinal trigger, the execution link trigger and foreign key, and the producer checks, each classified as exactly its own write. Real statement timeout (57014), lock-not-available (55P03), and administrator termination are never lineage failures. A real ticket CHECK failure, a non-link execution foreign key failure, and an unrelated trigger code are not lineage failures. Message text never classifies. Every named identity is asserted to exist in the live schema. Workflow tests prove a real decision violation (check and foreign key, with and without a review), a real invalid execution link, and a producer backstop failure end as `lineage_write_failure` with nothing surviving, and that statement timeouts on the decision and execution inserts, a ticket integrity failure, and a non-link execution failure end as `worker_failure` with nothing surviving. Response-id log safety is tested with `caplog`. Three C1 tests that used a non-integrity `SELECT 1/0` as a stand-in were replaced by these real-error tests.

**Verification (from `d:\vetoq`).** `uv run --locked --directory apps/api` with `ruff check`, `ruff format --check`, `mypy`, and `pytest` against `vetoq_test`: all clean, mypy strict on 56 files, Pytest 579 passed, 0 skipped, 60.7s. No Playwright or root `pnpm verify` ran. The development database was not touched.

**Open items.** `DISABLE TRIGGER` appears in one test, inside a transaction that always rolls back, only to reach the real diagnostics of the execution-link foreign key. Control characters in a provider response id are not specially handled, and that behavior was not investigated in C1B. C2 still owns strict enforcement, the cascade replacement, and the `policy_revision` preflight.

**Next authorized task.** Human review of C1B, then a GREEN A for C2.

## M004 Slice C1 â€” lineage writers on 0005 (15 October 2026)

**IMPLEMENTED TODAY (supersedes the "NOT implemented" list in Slice B below, except where stated).** Schema is still `0005_provenance_lineage`. `SCHEMA_REVISION` was not changed, `0005` was not edited, and there is no `0006`.

- **Guard version.** `GUARD_VERSION = "action-guard/1"` in `contracts.py`. A label, not authority.
- **Guard decisions.** Every persisted `authorize()` evaluation inserts one `guard_decisions` row in the same transaction (`record_guard_decision`): exact action digest, exact workspace policy revision passed to the guard, the guard version, and the next ordinal for the action. Nothing reads `guard_decisions` to decide anything.
- **Review lineage.** A new REVIEW creates the review (`requested_at = now()`) and then its decision. The decision after an approval references the same review. `decide_review` writes decision, reviewer, and `decided_at = now()` together. Consumption sets `consumed` and `consumed_at` together, only on the executing path. An approval followed by a revalidation BLOCK is not consumed (existing semantics).
- **Execution link.** New executions store the id of the exact ALLOW decision. New runtime executions never have a NULL link.
- **Producer provenance.** New model-produced actions store provider, requested model, prompt version, and response id (empty, whitespace, or over-200-character id becomes NULL). The digest does not include them. The Groq adapter maps a null response id to an empty string instead of `"None"`.
- **Evidence pre-validation.** Proposal and finding evidence is validated before any model result is persisted. Failure is `invalid_model_evidence` and the run fails. The accidental `StopIteration` path for findings is gone.
- **`lineage_write_failure`.** Raised for a rejected lineage integrity rule on the decision insert, the execution link, or the producer columns, or an unusable producer trio. Ticket and other database failures stay `worker_failure`. C1 mapped too broadly. C1B (above) narrowed it.

**Still NOT implemented.** `0006`, strict database enforcement of the new-writer rules (C2), lineage reads and APIs, active-workspace visibility, BFF, and UI. PROV-001 and LINE-001 stay PARTIAL. `executions.guard_decision_id` still has the `0005` cascade (see the binding C2 requirements in the module specification).

**Tests.** The Slice B runtime-compat tests that asserted NULL lineage columns were removed because C1 intentionally changes that behavior. `tests/test_lineage_writers.py` covers decisions, review linkage, timestamps, consumption, execution links, producer provenance, evidence pre-validation, rollback, retry, stale ownership, the same-tool Goal Lock proof, and a static authority-boundary check.

**Verification (from `d:\vetoq`).** `uv run --locked --directory apps/api` with `ruff check`, `ruff format --check`, `mypy`, and `pytest` against `vetoq_test`: all clean, Pytest 547 passed, 0 skipped, 58.5s. No Playwright or root `pnpm verify` ran. The development database was not touched.

**Open items.** C2 must also decide how to treat `vetoq_test` and historical rows. Slice D retention and legacy distinctions stand.

**Next authorized task.** Human review of C1, then a GREEN A for C2.

## M004 Slice B â€” additive lineage schema and database integrity (15 October 2026)

**IMPLEMENTED TODAY.** Migration `apps/api/migrations/versions/0005_provenance_lineage.py` (down revision `0004_edge_steps`, the only Alembic head). `SCHEMA_REVISION` and readiness now require `0005_provenance_lineage`. Downgrade raises `RuntimeError`. `0001` to `0004` were not edited. There is no `0006`.

- **`guard_decisions`.** Append-only output evidence. Bound of 1 to 16 reasons per decision, proven from the guard code (every return path carries at least one reason; at most 11 conditions plus the approval path give 15 distinct codes). The proof is structural (AST) and exhaustive (all condition combinations) in `tests/test_lineage_schema.py`. Composite keys and a digest-bound foreign key to `actions`, a nullable review link, an ordinal that must be contiguous per action, and an update-rejecting trigger. Repeated verdicts per action are allowed.
- **Nullable additive columns.** `actions.producer_*` (all-null or the provider, model, and prompt version together; `protect_action` freezes them after insert), `reviews.requested_at/decided_at/consumed_at` (tolerant checks only, tolerant immutability for identity fields), and `executions.guard_decision_id` (composite foreign key, insert validation requires an ALLOW decision with the same digest). Historical rows stay NULL. There is no backfill.
- **Database integrity.** Action evidence validation at insert (array of 1 to 16 canonical UUIDs that resolve to nodes of the same workspace and run; the DB bound is asserted equal to `BUDGETS.proposal_evidence_ids`), execution immutability (only `verified_at` may move once from NULL), `immutable_ticket`, `immutable_finding`, and a deferred constraint that every derived node has a parent edge. Three lookup indexes.

**NOT implemented.** No runtime writes `guard_decisions`, producer columns, review timestamps, or `executions.guard_decision_id`. No lineage writer, read service, API, BFF, or UI exists. Action Guard, `authorize()`, the review routes, and the active-workspace visibility behavior are unchanged. PROV-001 and LINE-001 stay PARTIAL. Migration `0006_lineage_enforcement` (strict review rules) does not exist.

**Fixture corrections (invalid under the new invariants, not weakened checks).** The expired-review test ages `expires_at` with the freeze trigger disabled inside one transaction. The mismatched-child pipeline fixture now inserts the derived child with its edge and step.

**Verification (from `d:\vetoq`).** `uv run --locked --directory apps/api ruff check .`, `ruff format --check .`, `mypy`, and `pytest` with `VETOQ_TEST_DATABASE_URL` pointing at `vetoq_test`: Ruff clean, 59 files formatted, mypy strict clean on 53 files, Pytest 502 passed, 0 skipped, 57.6s. A fresh disposable database migrated base to `0005`, a populated 0004 rehearsal upgraded with row counts and existing columns unchanged and new columns NULL, `vetoq_test` and the development `vetoq` were upgraded additively (`vetoq` was not reset), and a four-way schema parity test (fresh, upgraded, `vetoq_test`, `vetoq`) passes. Scratch databases were dropped. `vetoq_test` holds labeled synthetic test fixtures, including historical derived nodes with no parent edge. They are not rewritten. No Playwright or root `pnpm verify` ran, so no UI or browser claim is made.

**Open items.** Slice D defines the retention eligibility predicate and legacy-versus-anomaly distinctions. The reason-count bound item from Slice A is resolved (1 to 16). The other Slice A open items stand.

**Slice B1 closeout.** The expired-review test no longer disables `immutable_review`. It runs the authorizing tick with the workflow clock (`vetoq.workflow.now`) set 15 minutes behind, so the production INSERT creates a review whose window already closed, then exercises `review_stale` and the worker expiry. A dedicated test proves `UPDATE reviews SET expires_at=...` fails through the enabled production trigger. No production code or migration changed. Two binding Slice C / `0006` requirements are recorded in [modules/004-provenance-lineage.md](modules/004-provenance-lineage.md): execution history must survive guard-decision deletion (replace the `0005` cascade), and `producer_response_id` requires the producer trio after cutover.

**Next authorized task.** Human review of Slice B and B1, then a GREEN A for Slice C.

## M004 Slice A â€” provenance and lineage contracts (15 October 2026)

Docs-only slice. No production code, migration, database, API, UI, dependency, or Git change. Implemented scope is none: nothing from M004 exists at runtime.

**IMPLEMENTED TODAY.** Unchanged from M003 GREEN B. At the end of Slice A, Alembic head and `SCHEMA_REVISION` were `0004_edge_steps` (superseded by Slice B above).

**APPROVED DESIGN (recorded, not implemented).** [modules/004-provenance-lineage.md](modules/004-provenance-lineage.md), [ADR 0004](adr/0004-run-scoped-relational-lineage.md), and change records [0002](change-control/0002-prov-001-wording.md) (PROV-001), [0003](change-control/0003-line-001-wording.md) (LINE-001), and [0004](change-control/0004-active-workspace-visibility.md) (active-workspace read visibility). The decisions are run-scoped relational lineage in PostgreSQL, append-only `guard_decisions` as output evidence, review and execution structural links, evidence-id validation as `invalid_model_evidence`, producer provenance columns, no audit backfill, no retention extension, canonical visibility, and the two-migration plan `0005_provenance_lineage` then `0006_lineage_enforcement`.

**Capability status.** PROV-001 and LINE-001 stay PARTIAL. The registry sentences were not changed. Replacement sentences are approved for GREEN B only.

**Contract edits.** `AGENTS.md` scope statement corrected (M001, M002, M003 complete; M004 gated by slice; no M005). Run-scoped clarifications and approved-design sections were added to `PRODUCT_CONTRACT.md`, `SECURITY_INVARIANTS.md`, `ARCHITECTURE_CONTRACT.md`, `DATA_CONTRACT.md`, `API_CONTRACT.md`, `ENGINEERING_CONTEXT.md`, and `CHANGE_CONTROL.md`.

**Verification.** Docs formatting check only (`pnpm exec prettier --check` on the touched files). No database test, Playwright run, backend suite, or root `pnpm verify` was run in this slice, so no runtime claim is made.

**Open items.**

- RESOLVED in Slice B: a guard decision cannot have zero reasons; the bound is 1 to 16.
- Slice D defines the retention eligibility predicate and the legacy-versus-anomaly distinctions from provable facts. A NULL `producer_provider` is not a universal legacy marker.
- `decide_review` and `cancel` visibility for an inactive workspace is a separate later hardening consideration needing its own change record.
- A broader retention policy for runs, actions, reviews, tickets, and executions is unresolved later security and operations work.
- `README.md` still describes an earlier module state. It was outside the Slice A delta and was not changed.
- The UI and any visual treatment of lineage are deferred. Performance claims for scale belong to M014.

**Next authorized task.** Human review of Slice A. Slice B (`0005_provenance_lineage`) needs its own GREEN A.

## M003 Slice K â€” release verification (15 October 2026)

- Browser release tests use one origin, `http://localhost:3000`. `scripts/e2e-browser.mjs` starts a test API on `127.0.0.1:18010` and a worker against `VETOQ_TEST_DATABASE_URL`. It does not start port 3100 and it does not attach to the development server.
- The development database `vetoq` stayed at Alembic `0004_edge_steps` and was not reset. A fresh disposable database migrated base â†’ `0001_security_slice` â†’ `0002_worker_claim` â†’ `0003_secure_ingestion` â†’ `0004_edge_steps` and was then dropped.
- `pnpm verify` passed: Prettier, web lint, strict types, Vitest 57, production build, Ruff, mypy, Pytest 325 in 26.61s with no skips, and Playwright 111 across Chromium, Firefox, and WebKit in 9.5m.
- One live Groq smoke on the disposable database completed an authorized local ticket and its read-back verification. That smoke is provider integration, not the security proof.
- INGEST-001 is IMPLEMENTED with the sentence in change record 0001. MULTI-001 stays PLANNED. SEC-001, UX-001, and A11Y-001 stay PARTIAL. No manual screen-reader audit was performed. Scale, enterprise operations, and multi-agent analysis stay in later modules.

## M003 Slice J â€” public and auth experience (15 October 2026)

- The public page is an execution narrative: bounded authority, evidence, the proposed action, review, and verification. The hero is light and separate from the lavender closing field.
- The lavender field sits immediately above the footer, with one call to action into sign-in. The footer names only real sections and account routes.
- Sign-in and sign-up keep Clerk inside a VETOQ split shell. Submitted content stays untrusted. The page does not claim certification, multimodal ingestion, or live multi-agent analysis.
- At the close of Slice J, INGEST-001 was still PARTIAL and Slice K had not started. The current status is the Slice K section above.

## M003 I2 â€” run narrative (14 October 2026)

- The run page reads from the persisted run: goal, Goal Lock, evidence graph, findings, proposal, guard verdict, review, ticket, and verification time. It does not recompute a decision.
- Evidence is a parent-to-child list. `representation_kind` labels Original, Canonical text, Decoded text, or Active content. Null is Legacy evidence. `declared_media_type` null is Not recorded.
- An edge summary stays separate from `transform_steps`. A null step list says the transform history was not recorded. Content opens as inert text.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. UX-001 stays PARTIAL. A11Y-001 stays PARTIAL. Slice J is recorded above.

## M003 I1 â€” authenticated Workbench (14 October 2026)

- The signed-in Workbench is one workspace: intent, authority, untrusted content, then confirmation. It is not a stack of separate cards. Slice J later replaced the public homepage and auth shell.
- The five pasted formats stay Plain text, JSON, Markdown, HTML, and Email (RFC822). Guidance is specific to the selection. Changing the format does not alter the pasted source. There is no upload, drop zone, or automatic detection.
- Confirmation still sends `confirmed: true`. The copy says the user is confirming the goal, the authority, and untrusted content. It does not call the content safe or sanitized.
- The primary action remains "Start guarded analysis". While the request is in flight the control says "Submittingâ€¦". Stable rejection codes stay visible beside a short explanation. The source is not copied into the error.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. UX-001 stays PARTIAL. A11Y-001 stays PARTIAL. I2 is recorded above.

## M003 H2B â€” live ingestion activation (14 October 2026)

- `POST /api/v1/runs` calls `accept_declared_submission`. The server sets template `support-triage/1`. The client cannot send it. `media_type` is required and is normalized only by the kernel.
- A body that still sends `sanitized`, `source_class`, `trust`, `parser_id`, `parser_version`, or `template` is `422 invalid_input` and creates no run.
- The same idempotency key and the same normalized declaration return the same run. A different declared type with that key is `409 idempotency_conflict`.
- Edge reads add `transform_steps`. A null count is `null`. A recorded count is the ordered `{transform, version}` list. The summary fields stay separate.
- The BFF forwards only `workspace_id`, `goal`, `source`, `media_type`, and `confirmed` for `POST /runs`. The 512 KiB cap, origin check, and correlation id stay. There is no multipart upload.
- The Workbench adds a native format select for the five labels. Confirmation still means the goal and the submission. It does not certify the content.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. At H2B, Slice I had not started.
- `uv run ruff check` passed. `uv run ruff format --check` passed. `uv run mypy` reported no issues in 52 source files. `uv run pytest` reported 325 passed. Web ESLint, strict `tsc`, Prettier on the changed files, and Vitest (34 tests) passed. `next build` passed. Targeted Chromium Playwright later passed in H2B1: 5 authenticated workbench tests, no skips, against `http://localhost:3000`. Root `pnpm verify` was not run.

## M003 H2A â€” internal ingestion pipeline (14 October 2026)

H2B later mounted the route described here. The notes below are the H2A worker behavior, which remains.

- The worker treats a queued original as staged M003 only when `representation_kind` is `original` and `declared_media_type` is stored. Null metadata stays on the Module 002 path. The worker does not sniff the body.
- Staged canonicalization persists each derived node, its summary edge, and the exact ordered steps in the claim transaction. Restart verifies those deterministic rows and does not insert a second copy. A mismatch fails closed.
- New Base64 edges record `base64` / `1` as one step. The decoded node uses `representation_kind = decoded_text` and parser `bounded-decoder` version `1`. Historical edges stay null.
- Derived representation count and derived UTF-8 bytes apply to adapter children and later Base64 children together. The original is outside that count. Overrun is `parser_limit_exceeded` and does not call the model.
- At H2A the live route still rejected an M003 body. H2B mounted it. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL.
- `uv run ruff check` passed. `uv run ruff format --check` passed. `uv run mypy` reported no issues in 51 files. `uv run pytest` reported 312 passed. Playwright and `pnpm verify` were not run.

## M003 H1 â€” edge transform-chain schema (14 October 2026)

- Alembic head is `0004_edge_steps`. Readiness expects that revision. `0001`, `0002`, and `0003` were not edited. Downgrade is refused.
- `content_edges.transform_step_count` is nullable. NULL means the chain was not recorded. 1 through 4 means that many ordered `content_edge_steps` rows. Historical edges stay NULL. There is no backfill.
- The edge `transform` and `version` remain the summary. Step rows are the ordered history. They need not match. The worker, the Base64 writer, and the live route do not write steps yet.
- The budget field is `transform_steps_per_edge` = 4. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL.
- Fresh database `vetoq_m003_migrate_test` migrated from base through `0004_edge_steps` and was dropped. `vetoq_test` and development `vetoq` then upgraded additively from `0003_secure_ingestion`. Development was not reset.
- Before the upgrade, `vetoq` had workspaces 22, runs 13, content_nodes 14, content_edges 1, audit_events 69, and no `content_edge_steps` table. `vetoq_test` had workspaces 1228, runs 662, content_nodes 694, content_edges 29, audit_events 2939, and no `content_edge_steps` table.
- After the upgrade both databases are at `0004_edge_steps` with those same five counts. `content_edge_steps` is 0. No edge has a non-null `transform_step_count`.
- `uv run ruff check` passed. `uv run ruff format --check` passed. `uv run mypy` reported no issues in 49 files. `uv run pytest` reported 294 passed. Playwright and `pnpm verify` were not run.

## M003 Slice G â€” API foundation (14 October 2026)

Historical. H2B replaced the live body described in the first bullet.

- At Slice G the live public body was still `goal`, `source`, `confirmed`, and `sanitized: true`. It did not accept `media_type` and it did not call an adapter.
- `DeclaredSubmission` and `accept_declared_submission` require `media_type`, reject `sanitized` and `source_class`, validate with the registered adapter, and insert one original with truthful `0003` metadata. Parser id and version on that original are null. No derived child or edge is written.
- The run read returns those metadata fields as stored, including null on Module 002 rows, and returns the run's `content_edges`. An empty edge list is empty.
- Slice G did not store the ordered chain. H1 added `0004_edge_steps`. H2A is the worker that writes it for staged runs.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL.

## M003 Slice F1 â€” pre-accept processability (14 October 2026)

- Pre-accept validation of `html_inert` version `1`, `email_rfc822` version `1`, and `json_structured` version `1` proves the deterministic derived representation count and derived UTF-8 bytes. Exceeding either is `422 input_limit` and creates no run. The original source is outside the 32 derived representations. The budget field is `derived_representations_per_run`.
- Canonicalization still raises `parser_limit_exceeded` if that proof is bypassed. Derived children carry an ordered `transform_steps` chain. Quoted-printable escapes are rejected before decode. Inline `style` and `meta` refresh are active evidence only. A supported empty email leaf is traversed and omitted. Top-level empty text and Markdown stay `empty_input`.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. No migration, no content-node write, and no public format selection.

## M003 Slice F â€” HTML and RFC822 adapters (14 October 2026)

Status: the last two contracted adapters, awaiting human review. `POST /runs` is still the Module 002 body, including `sanitized: true`.

- `html_inert` version `1` extracts lossy visible text and, when present, lossy active content. It does not execute HTML, fetch URLs, or emit an empty child.
- `email_rfc822` version `1` rejects an unsupported leaf, charset, or transfer encoding for the whole message. `binary` and nested `message/rfc822` are unsupported. Header bytes and MIME part counts are pre-accept limits. Slice F1 moves the deterministic derived-byte and derived-representation budgets into that same pre-accept proof.
- `text_plain` version `1`, `json_structured` version `1`, and `markdown` version `1` are unchanged. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. No malware scan and no binary attachment support.

## M003 Slice E â€” JSON and Markdown adapters (14 October 2026)

Status: two more adapters, awaiting human review. `POST /runs` is still the Module 002 body, including `sanitized: true`.

- `json_structured` version `1` validates strict JSON and returns one lossy `canonical_text` child. Depth is open containers. A member is one object pair or one array element, summed across the document.
- `markdown` version `1` preserves the original text and returns no derived node. It does not render HTML.
- `text_plain` version `1` is unchanged. HTML and RFC822 remained unresolved in this slice. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.

## M003 Slice D â€” text/plain adapter (14 October 2026)

Status: one adapter, awaiting human review. `POST /runs` is still the Module 002 body, including `sanitized: true`.

- `production_registry()` registers `text_plain` version `1` for `text/plain` only. The other four contract types resolve as internal `adapter_not_implemented`. That code is not a public API error.
- Canonicalization succeeds with zero derived nodes. The original string is not copied into a child.
- Parser version is outside the Goal Lock, `source_digest`, and submission identity. A newer parser does not reprocess an accepted run. Replay is not implemented.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.

## M003 Slice C â€” ingestion kernel (14 October 2026)

Status: kernel only, awaiting human review. No JSON, HTML, or RFC822 parser is registered. The running submission path is still Module 002.

- Schema remains `0003_secure_ingestion`. Fresh, `vetoq_test`, and development `vetoq` match on content-node columns, checks, the immutability function, and the Alembic revision.
- Budgets, declared-type normalization, the adapter registry, and the future submission identity live in `vetoq.ingestion`. The registry starts empty.
- Parser version is not part of the Goal Lock and not part of that future submission identity.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.

## M003 Slice B â€” schema (14 October 2026)

Status: persistence only, awaiting human review. No parser, adapter registry, API body change, or UI change is included.

- Alembic head is `0003_secure_ingestion`. Readiness expects that revision.
- `content_nodes` gained nullable `declared_media_type`, `representation_kind`, `parser_id`, `parser_version`, `charset`, and `byte_size`. NULL on existing rows means not recorded.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.
- A fresh database migrated from base through `0003_secure_ingestion` and was dropped. `vetoq_test` and development `vetoq` then upgraded additively from `0002_worker_claim`. Development row counts stayed workspaces 22, runs 13, content_nodes 14, content_edges 1, audit_events 69, and every existing content node stayed NULL on the new columns.
- Focused Pytest passed 78 tests. Ruff and strict mypy passed. Playwright and `pnpm verify` were not run.

## M003 Slice A â€” specification (13 October 2026)

Status: specification complete, awaiting human review. No migration, API, worker, UI, or dependency change is included.

- The normative spec is [modules/003-universal-secure-ingestion.md](modules/003-universal-secure-ingestion.md).
- [ADR 0003](adr/0003-declared-format-ingestion.md) freezes declared-format adapters, one Goal Lock source, and PostgreSQL text storage.
- [Change record 0001](change-control/0001-ingest-001-wording.md) holds the future INGEST-001 sentence. The registry row was not edited and stays PARTIAL.
- MULTI-001 stays PLANNED. The supported set is `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`.
- The next implementation step, after review, is Slice B in that specification. The public-site redesign is Slice J.

## Module 002 runtime baseline

**Module 002 implementation is the verified runtime, awaiting any remaining human review and manual Git workflow.**

Verified on **9 October 2026 (Asia/Calcutta)**. Read [the Module 002 verification record](modules/002-verification.md) for the acceptance table, provider observations, dependency rationale, test denominators, and limitations.

## M002 stabilization slice 1 â€” identity / workspace / test-database boundary (12 October 2026)

Status: complete and awaiting human review. Slice 2 has not started.

- **Root cause of `request_failed_500`.** The web server was started with `--hostname 127.0.0.1`. Next.js presents middleware request URLs as `localhost`, and Clerk turns each pass-through into an absolute rewrite to that URL. Because the server's own origin was `127.0.0.1`, Next.js treated the rewrite as external and proxied the request back to itself; the matcher applied again, and the loop never ended.
  - Evidence: one signed-out `/api/v1/me` request produced 257 self-connections into the server's port and timed out with 0 bytes. This reproduced in both dev and production-build mode.
  - With `--hostname localhost`, the same code returned JSON 401 in 0.08 s (dev) and 0.17 s (production).
  - The web scripts and Playwright now use `localhost`. The server stays loopback-only because it binds `::1`.
- **BFF and Clerk.** `proxy.ts` matches `/api/:path*` and never calls `protect()` for it. The BFF uses `auth()` and returns these JSON errors:
  - 401 `authentication_required`
  - 503 `identity_unavailable` or `api_not_configured`
  - 503 `api_unavailable` and 504 `api_timeout`
  - 502 `invalid_upstream_response`
  - 400, 403, 405 and 413 for invalid requests
  - Every error carries a correlation ID, which is forwarded to FastAPI as `X-Request-ID`. Logs are redacted.
- **Backend.**
  - The unverified rule that accepted the Clerk issuer as `azp` was removed.
  - Missing Clerk configuration and an unreachable JWKS endpoint return 503 instead of 401.
  - Framework 404 and 405 responses use the JSON error contract.
  - `hide_parameters=True` keeps SQL parameter values out of logs.
  - `/me` reports `access: active | not_provisioned`.
  - The first-page run-list query no longer fails with `AmbiguousParameter`.
- **Test database.** `VETOQ_TEST_DATABASE_URL` must name a database ending in `_test`. The server-reported `current_database()` must match it, and it must differ from `VETOQ_DATABASE_URL`. Otherwise integration setup and `verify:groq` refuse to run. Local value: `vetoq_test` on the Compose PostgreSQL. The development database was not reset or cleaned.
- **Verification.**
  - Vitest: 24 tests across 5 files.
  - ESLint, strict TypeScript, Prettier and the Next.js production build pass.
  - Ruff and strict mypy pass. Pytest: 92 passed against `vetoq_test`.
  - Development database counts (22 workspaces, 11 runs, 55 audit events) were unchanged across all test runs.
  - The guard refused setup when pointed at the development database.
  - The multi-browser Playwright suite was not run in this slice.
- **Runtime evidence.**
  - Signed out: `/api/v1/me` returns JSON 401.
  - Signed in through the BFF: `/me` 200, run list 200, `POST /runs` 202, all without errors.
  - The persisted run `128c8010-â€¦` has principal `user_3KSâ€¦` (32 characters). That principal matches the active `reviewer` membership in "Demo support" (`00000000-0000-4000-8000-00000000000a`).
  - The browser's `/me` JSON was not pasted back, so the response body itself is not recorded.
- **Observation for the next slice.** That run remains `QUEUED`, with one audit event (`RUN_ACCEPTED`). No worker was running during validation, so this is not attributed to the identity boundary.

## M002 stabilization slice 2C â€” review / separation of duties (12 October 2026)

Status: complete and awaiting human review. Two-principal production review semantics are proven through isolated PostgreSQL integration tests using the real production authorization/review/workflow code path. A second live Clerk browser principal was not available for manual E2E validation and remains an auth-E2E hardening item.

- The originating principal cannot approve the exact action (`403 self_review_prohibited`, audit `SELF_REVIEW_PROHIBITED`, review undecided and unconsumed). A different active reviewer approves that digest. The worker returns through `AUTHORIZING`, Action Guard emits `ACTION_ALLOW`, and the same transaction writes one ticket, one receipt, and consumes the review. Read-back reaches `COMPLETED`.
- Negative proofs on `vetoq_test` write zero tickets: self-review, outsider and non-reviewer, inactive reviewer, expired review, consumed-approval replay, digest mismatch, argument mutation, Goal Lock scope mismatch despite approval, reviewer membership revoked after approval, originator membership revoked before execution, and cancellation after approval.
- Review eligibility is a backend field. The run page shows approve and reject only when that field is true, and it shows the exact action, evidence summary, and expiry. A verified-ticket link requires `verified_at`.
- Development run `0110239d-7409-4f08-a289-33134a5d4303` had already passed its Goal Lock expiry, so one worker tick closed it as `EXPIRED` with no review and no write. That is retained history, not a product gap.
- Focused verification on 12 October 2026: Ruff and strict mypy passed. `tests/test_action_guard.py` and `tests/test_database_integration.py` on `vetoq_test`: 37 passed. Run-view Vitest: 5 passed. The development database was not used for integration setup.

## M002 stabilization slice 3 â€” worker / recovery / concurrency (12 October 2026)

Status: complete and awaiting human review. Goal Lock, Action Guard, and review semantics are unchanged.

- One run failure is quarantined with a stable reason (`source_integrity_failure`, `provider_invalid_output`, `worker_failure`, or the provider code) and the worker continues with later eligible runs.
- Claim selection uses `FOR UPDATE SKIP LOCKED`. The run row is the claim lock. Workspace and membership rows are locked only inside `authorize()`, so inference and human review do not hold database locks.
- A stale fence cannot insert an action after a newer worker reclaims the lease. Two workers claim one run once. Two independent runs overlap inside inference.
- Retryable provider failures keep the run in `PROPOSING` with a bounded lease backoff (`2 ** attempts` seconds, cap 8) and then fail closed. No second provider is introduced.
- `run_worker` finishes the in-flight tick, then stops accepting work on Ctrl+C/SIGTERM or a stop signal. Logs carry `run_id` and reason codes, not source text or secrets.
- Alembic `0002_worker_claim` adds `runs_claimable` and `reviews_unresolved_expiry`. At the close of slice 3, `vetoq_test` was at that revision and the development database was still at `0001_security_slice` until `pnpm db:migrate`. Slice 4 confirmed both databases are at `0002_worker_claim`. Readiness expects that revision.
- Focused verification: Ruff, strict mypy, and 68 passed across `test_action_guard.py`, `test_database_integration.py`, `test_health.py`, `test_provider.py`, and `test_schema.py`.

## M002 stabilization slice 4 â€” repository hygiene and frontend foundation (12 October 2026)

Status: complete and awaiting human review. Approved security semantics were not changed.

- Development and test databases are both at `0002_worker_claim`.
- Stage labels come from persisted run state. A proposal is `PROPOSED` or the Action Guard verdict, not `PENDING`, after model completion. Goal Lock is `SEALED`. Source and findings are `RECORDED` or `NONE`, not a verification claim. A ticket is `VERIFIED` only when `verified_at` is set.
- Run polling retries with bounded backoff, stops on terminal states, polls `AWAITING_REVIEW` every 15 seconds, and requests events after the last sequence.
- Canonical color tokens live in `globals.css`. `vetoq.css` aliases them. Page-level `overflow-x: hidden` was removed. Clerkâ€™s hosted card uses the paper and plum tokens.
- The Groq client stays on `httpx2` 2.13.1. Starlette 1.7.0, which FastAPI 0.142.2 requires, imports `httpx2` for `TestClient` and emits `StarletteDeprecationWarning` when only canonical `httpx` is installed. Pytest treats warnings as errors, so that import cannot load. `httpx2` also uses `truststore` for the operating-system certificate store; canonical `httpx` 0.28.1 would switch the Groq client to the certifi bundle. The provider only uses `Client`, timeouts, `post`, and `HTTPError`/`TimeoutException`.
- Installed Clerk 7.9.11 deprecates `createRouteMatcher` for the next major release, in favor of auth checks inside each protected page, layout, and route. Moving `protect()` out of `proxy.ts` would change the established BFF boundary, so the matcher stays for a dedicated Clerk upgrade. `proxy.ts` was not removed.
- `class-variance-authority` 0.7.1 types the status-badge tones. No Radix or default shadcn components were added; the current screens do not need overlays, menus, dialogs, tooltips, or tabs.
- Membership SQL stays at each call site. The statements differ in joined columns, role filters, and row locks, so one helper would risk changing isolation or lock order.
- `baseUrl` was removed from the web tsconfig. `@/*` stays relative to that file.

## M002 stabilization slice 5 â€” production contracts (12 October 2026)

Status: complete and awaiting human review. No product behavior was changed.

- Canonical contracts now govern identity, authority, architecture, data, API, agents, tool execution, and UI direction.
- The capability registry in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) is the only status list. Planned specialists, connectors, Shadow Guard, Policy Replay, the evaluation lab, and production deployment stay PLANNED.
- Older product, architecture, security, design, threat, and evaluation documents point at those contracts. The hackathon prompt-injection-firewall wording is historical context, not the product category.

## Current implemented scope

The first real end-to-end text security slice is implemented: Clerk-authenticated operator and local membership; confirmed immutable Goal Lock; original and bounded derived provenance; deterministic inspection; real Groq `openai/gpt-oss-120b` analysis behind a provider-neutral interface; typed proposal; deterministic ALLOW/BLOCK/REVIEW guard; exact digest review; leased persisted workflow; real PostgreSQL ticket, receipt, audit, and read-back; and responsive P0 product UI.

The same `tickets.create` tool has real PostgreSQL evidence for both paths. The allowed path commits exactly one ticket and verifies it. The controlled wrong-workspace path persists `BLOCK` with `GOAL_SCOPE_MISMATCH` and commits zero tickets even when the principal belongs to both workspaces.

## Current verification

Final Module 002 release gate, 12 October 2026. `pnpm verify` exited 0.

- Prettier check passed. ESLint reported zero warnings. Strict TypeScript passed. Vitest: **27 passed across 6 files**. Next.js 16.4.0 production build passed.
- Backend: Ruff check passed, Ruff format reported 30 files already formatted, strict mypy reported no issues in **27 source files**, Pytest **116 passed** in 14.45s on PostgreSQL. Integration setup used `vetoq_test` only.
- Playwright: **78 passed** on Chromium, Firefox, and WebKit. Widths 320, 360, 390, 430, 768, 1024, 1280, 1440, and 1920. Axe WCAG A/AA passed. Reduced motion and 400% root text at 320px passed.
- Development database `vetoq` and test database `vetoq_test` are both at `0002_worker_claim`. A fresh disposable database migrated from zero to that head and was dropped. The development database was not reset.
- Cancel of a non-terminal run persists `CANCELLED`. Cancel of an already terminal run leaves that row unchanged and returns its persisted state.
- An idle worker connected to `vetoq_test`, found no claimable run, and stopped when asked. It was not left running. It was not pointed at `vetoq`.

## Current operations

Use `pnpm db:migrate`, provision the Clerk subject with `pnpm admin:provision -- ...`, then run `pnpm dev:web`, `pnpm dev:api`, and `pnpm dev:worker` in separate terminals. `pnpm worker:once` processes one step. Schedule `pnpm retention:run` to delete expired 24-hour content and audit metadata older than 30 days. Product readiness requires PostgreSQL and exact schema revision.

## Current limitations and next action

Module 002 is text-only. It does not establish F3 or D3, statistical detector reliability, external tool protection, or public deployment readiness. The 27 attack and 20 benign fixtures are labeled engineering regressions, not operational metrics. Automated accessibility passed; manual screen-reader and true browser-zoom validation remain. Authenticated Playwright sign-in was not automated; the configured signed-out Clerk state is tested in all three engines, identity cryptography and workspace authorization have focused backend tests, and authenticated UI states have component tests.

M003 Slice A is the authorized specification and is awaiting review. Do not begin Slice B, multimodal input, external integrations, evaluation expansion, or deployment from this handoff. The hackathon deadline of 11 October 2026, 11:59 PM IST and the internal freeze of 8:00 PM IST are historical event dates.

## Prior Module 001 handoff record

Verified on **8 October 2026 (Asia/Calcutta)**. The following is the historical Module 001 record and is superseded where Module 002 now implements the planned capability. Read [the Module 001 verification record](modules/001-verification.md) for its original evidence.

## Read in this order

1. [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) and the rest of the hierarchy recorded there.
2. AGENTS.md, README.md, and this handoff.
3. The active module specification, [modules/003-universal-secure-ingestion.md](modules/003-universal-secure-ingestion.md). The Module 002 specification remains the runtime baseline.
4. Applicable ADRs, then the older product, architecture, threat, security, evaluation, and design notes.
5. Relevant source, tests, and the verification record.

If two higher-priority contracts contradict each other, stop and report the contradiction.

## Implemented

Neutral Next.js shell with explicit foundation-only disclosure; health-only FastAPI factory; validated environment settings; real read-only PostgreSQL readiness probe; local PostgreSQL Compose; pinned pnpm/uv locks; documentation; root verification and foundation tests. No business schema, migration, model integration, detector, policy, Goal Lock runtime, Action Guard, ticket, dashboard, or evaluation capability exists.

## Actual verification

- pnpm verify: exit 0. Frontend lint/types/build and 2 unit tests pass; backend Ruff/strict mypy and 25 tests pass; all 36 browser checks pass.
- Browser coverage: Chromium, Firefox, WebKit; nine widths from 320 to 1920; keyboard skip link; axe A/AA checks; reduced-motion and 200% text enlargement.
- Real Uvicorn HTTP smoke: liveness 200, PostgreSQL-backed readiness 200, product endpoint 404.
- PostgreSQL 18.6-alpine3.24 started healthy in a disposable Compose project. Public-schema table count: 0. Test container/network/volume and temporary credentials were removed.
- Frozen pnpm install, locked uv sync, peer checks, Compose validation, Python dependency consistency: pass.
- Production-only JavaScript audit: no known vulnerabilities.
- Full JavaScript audit: **FAIL, one high development-only braces@3.0.3 advisory**. Do not suppress or call the entire dependency tree clean. See verification record.

## Environment and caveats

Verified Windows runtimes: Node 22.20.0, pnpm 11.15.1, Python 3.12.13, uv 0.11.26; Docker engine 29.6.1. Local existing unrelated services occupy ports 5432 and 8000. Verification used database 55432 and API 18000. README documents alternate-port commands. Existing service configuration and data were not changed.

Docker Desktop was started to enable the test. The Docker engine remains available; no VETOQ application or database test server was left running. Dependency/browser/build caches remain ignored. No .env was created for the owner.

Manual screen-reader and actual 400% browser-zoom checks remain unperformed. No claim of full WCAG conformance, measured product security reliability, achieved F3/D3, Linux/macOS validation, or public deployment.

ESLint 9.39.5 is deprecated but retained to satisfy the current Next.js lint-plugin peer ranges; ESLint 10 produced peer incompatibilities and was removed. jsdom 26.1.0 fits the installed Node runtime; its transitive whatwg-encoding package emits a deprecation warning. Neither warning is suppressed.

## Git and ownership

Owner branch: chore/001-repository-foundation. Starting owner commit: d453cc6. All implementation files remain untracked for human staging. No pre-existing tracked source files were modified or removed. Plain git diff --stat is empty because new files are untracked; the verification record inventories them.

Read-only Git commands used --no-optional-locks and a command-local safe.directory override for the sandbox account ownership mismatch. No persistent Git setting, index, branch, commit, or remote was changed.

## Next action

Human review of Module 001, including the unresolved development-dependency advisory, followed by the manual Git workflow. Suggested commit grouping is in the verification record. Do not begin Module 002 without separate approval.

Before Module 002: resolve model provider/access/budget, hosting/identity, reference-ticket scope, permitted input-data handling, and exact heterogeneous input mapping for later modules. Preserve the owner-verified F/D definitions, all-nine-family goal, provider-independent authority, official deadline of 11 October 2026 11:59 PM IST, and internal freeze at 8:00 PM IST that day. No model/prompt/policy version exists yet.
