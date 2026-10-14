# Agent handoff

**M003 is GREEN B. INGEST-001 is IMPLEMENTED for adapter-governed ingestion of the five declared text formats, with unsupported formats failing closed. Do not start M004 without approval.**

## M003 Slice K — release verification (15 October 2026)

- Browser release tests use one origin, `http://localhost:3000`. `scripts/e2e-browser.mjs` starts a test API on `127.0.0.1:18010` and a worker against `VETOQ_TEST_DATABASE_URL`. It does not start port 3100 and it does not attach to the development server.
- The development database `vetoq` stayed at Alembic `0004_edge_steps` and was not reset. A fresh disposable database migrated base → `0001_security_slice` → `0002_worker_claim` → `0003_secure_ingestion` → `0004_edge_steps` and was then dropped.
- `pnpm verify` passed: Prettier, web lint, strict types, Vitest 57, production build, Ruff, mypy, Pytest 325 in 26.61s with no skips, and Playwright 111 across Chromium, Firefox, and WebKit in 9.5m.
- One live Groq smoke on the disposable database completed an authorized local ticket and its read-back verification. That smoke is provider integration, not the security proof.
- INGEST-001 is IMPLEMENTED with the sentence in change record 0001. MULTI-001 stays PLANNED. SEC-001, UX-001, and A11Y-001 stay PARTIAL. No manual screen-reader audit was performed. Scale, enterprise operations, and multi-agent analysis stay in later modules.

## M003 Slice J — public and auth experience (15 October 2026)

- The public page is an execution narrative: bounded authority, evidence, the proposed action, review, and verification. The hero is light and separate from the lavender closing field.
- The lavender field sits immediately above the footer, with one call to action into sign-in. The footer names only real sections and account routes.
- Sign-in and sign-up keep Clerk inside a VETOQ split shell. Submitted content stays untrusted. The page does not claim certification, multimodal ingestion, or live multi-agent analysis.
- At the close of Slice J, INGEST-001 was still PARTIAL and Slice K had not started. The current status is the Slice K section above.

## M003 I2 — run narrative (14 October 2026)

- The run page reads from the persisted run: goal, Goal Lock, evidence graph, findings, proposal, guard verdict, review, ticket, and verification time. It does not recompute a decision.
- Evidence is a parent-to-child list. `representation_kind` labels Original, Canonical text, Decoded text, or Active content. Null is Legacy evidence. `declared_media_type` null is Not recorded.
- An edge summary stays separate from `transform_steps`. A null step list says the transform history was not recorded. Content opens as inert text.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. UX-001 stays PARTIAL. A11Y-001 stays PARTIAL. Slice J is recorded above.

## M003 I1 — authenticated Workbench (14 October 2026)

- The signed-in Workbench is one workspace: intent, authority, untrusted content, then confirmation. It is not a stack of separate cards. Slice J later replaced the public homepage and auth shell.
- The five pasted formats stay Plain text, JSON, Markdown, HTML, and Email (RFC822). Guidance is specific to the selection. Changing the format does not alter the pasted source. There is no upload, drop zone, or automatic detection.
- Confirmation still sends `confirmed: true`. The copy says the user is confirming the goal, the authority, and untrusted content. It does not call the content safe or sanitized.
- The primary action remains "Start guarded analysis". While the request is in flight the control says "Submitting…". Stable rejection codes stay visible beside a short explanation. The source is not copied into the error.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. UX-001 stays PARTIAL. A11Y-001 stays PARTIAL. I2 is recorded above.

## M003 H2B — live ingestion activation (14 October 2026)

- `POST /api/v1/runs` calls `accept_declared_submission`. The server sets template `support-triage/1`. The client cannot send it. `media_type` is required and is normalized only by the kernel.
- A body that still sends `sanitized`, `source_class`, `trust`, `parser_id`, `parser_version`, or `template` is `422 invalid_input` and creates no run.
- The same idempotency key and the same normalized declaration return the same run. A different declared type with that key is `409 idempotency_conflict`.
- Edge reads add `transform_steps`. A null count is `null`. A recorded count is the ordered `{transform, version}` list. The summary fields stay separate.
- The BFF forwards only `workspace_id`, `goal`, `source`, `media_type`, and `confirmed` for `POST /runs`. The 512 KiB cap, origin check, and correlation id stay. There is no multipart upload.
- The Workbench adds a native format select for the five labels. Confirmation still means the goal and the submission. It does not certify the content.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. At H2B, Slice I had not started.
- `uv run ruff check` passed. `uv run ruff format --check` passed. `uv run mypy` reported no issues in 52 source files. `uv run pytest` reported 325 passed. Web ESLint, strict `tsc`, Prettier on the changed files, and Vitest (34 tests) passed. `next build` passed. Targeted Chromium Playwright later passed in H2B1: 5 authenticated workbench tests, no skips, against `http://localhost:3000`. Root `pnpm verify` was not run.

## M003 H2A — internal ingestion pipeline (14 October 2026)

H2B later mounted the route described here. The notes below are the H2A worker behavior, which remains.

- The worker treats a queued original as staged M003 only when `representation_kind` is `original` and `declared_media_type` is stored. Null metadata stays on the Module 002 path. The worker does not sniff the body.
- Staged canonicalization persists each derived node, its summary edge, and the exact ordered steps in the claim transaction. Restart verifies those deterministic rows and does not insert a second copy. A mismatch fails closed.
- New Base64 edges record `base64` / `1` as one step. The decoded node uses `representation_kind = decoded_text` and parser `bounded-decoder` version `1`. Historical edges stay null.
- Derived representation count and derived UTF-8 bytes apply to adapter children and later Base64 children together. The original is outside that count. Overrun is `parser_limit_exceeded` and does not call the model.
- At H2A the live route still rejected an M003 body. H2B mounted it. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL.
- `uv run ruff check` passed. `uv run ruff format --check` passed. `uv run mypy` reported no issues in 51 files. `uv run pytest` reported 312 passed. Playwright and `pnpm verify` were not run.

## M003 H1 — edge transform-chain schema (14 October 2026)

- Alembic head is `0004_edge_steps`. Readiness expects that revision. `0001`, `0002`, and `0003` were not edited. Downgrade is refused.
- `content_edges.transform_step_count` is nullable. NULL means the chain was not recorded. 1 through 4 means that many ordered `content_edge_steps` rows. Historical edges stay NULL. There is no backfill.
- The edge `transform` and `version` remain the summary. Step rows are the ordered history. They need not match. The worker, the Base64 writer, and the live route do not write steps yet.
- The budget field is `transform_steps_per_edge` = 4. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL.
- Fresh database `vetoq_m003_migrate_test` migrated from base through `0004_edge_steps` and was dropped. `vetoq_test` and development `vetoq` then upgraded additively from `0003_secure_ingestion`. Development was not reset.
- Before the upgrade, `vetoq` had workspaces 22, runs 13, content_nodes 14, content_edges 1, audit_events 69, and no `content_edge_steps` table. `vetoq_test` had workspaces 1228, runs 662, content_nodes 694, content_edges 29, audit_events 2939, and no `content_edge_steps` table.
- After the upgrade both databases are at `0004_edge_steps` with those same five counts. `content_edge_steps` is 0. No edge has a non-null `transform_step_count`.
- `uv run ruff check` passed. `uv run ruff format --check` passed. `uv run mypy` reported no issues in 49 files. `uv run pytest` reported 294 passed. Playwright and `pnpm verify` were not run.

## M003 Slice G — API foundation (14 October 2026)

Historical. H2B replaced the live body described in the first bullet.

- At Slice G the live public body was still `goal`, `source`, `confirmed`, and `sanitized: true`. It did not accept `media_type` and it did not call an adapter.
- `DeclaredSubmission` and `accept_declared_submission` require `media_type`, reject `sanitized` and `source_class`, validate with the registered adapter, and insert one original with truthful `0003` metadata. Parser id and version on that original are null. No derived child or edge is written.
- The run read returns those metadata fields as stored, including null on Module 002 rows, and returns the run's `content_edges`. An empty edge list is empty.
- Slice G did not store the ordered chain. H1 added `0004_edge_steps`. H2A is the worker that writes it for staged runs.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL.

## M003 Slice F1 — pre-accept processability (14 October 2026)

- Pre-accept validation of `html_inert` version `1`, `email_rfc822` version `1`, and `json_structured` version `1` proves the deterministic derived representation count and derived UTF-8 bytes. Exceeding either is `422 input_limit` and creates no run. The original source is outside the 32 derived representations. The budget field is `derived_representations_per_run`.
- Canonicalization still raises `parser_limit_exceeded` if that proof is bypassed. Derived children carry an ordered `transform_steps` chain. Quoted-printable escapes are rejected before decode. Inline `style` and `meta` refresh are active evidence only. A supported empty email leaf is traversed and omitted. Top-level empty text and Markdown stay `empty_input`.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. SEC-001 stays PARTIAL. No migration, no content-node write, and no public format selection.

## M003 Slice F — HTML and RFC822 adapters (14 October 2026)

Status: the last two contracted adapters, awaiting human review. `POST /runs` is still the Module 002 body, including `sanitized: true`.

- `html_inert` version `1` extracts lossy visible text and, when present, lossy active content. It does not execute HTML, fetch URLs, or emit an empty child.
- `email_rfc822` version `1` rejects an unsupported leaf, charset, or transfer encoding for the whole message. `binary` and nested `message/rfc822` are unsupported. Header bytes and MIME part counts are pre-accept limits. Slice F1 moves the deterministic derived-byte and derived-representation budgets into that same pre-accept proof.
- `text_plain` version `1`, `json_structured` version `1`, and `markdown` version `1` are unchanged. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED. No malware scan and no binary attachment support.

## M003 Slice E — JSON and Markdown adapters (14 October 2026)

Status: two more adapters, awaiting human review. `POST /runs` is still the Module 002 body, including `sanitized: true`.

- `json_structured` version `1` validates strict JSON and returns one lossy `canonical_text` child. Depth is open containers. A member is one object pair or one array element, summed across the document.
- `markdown` version `1` preserves the original text and returns no derived node. It does not render HTML.
- `text_plain` version `1` is unchanged. HTML and RFC822 remained unresolved in this slice. INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.

## M003 Slice D — text/plain adapter (14 October 2026)

Status: one adapter, awaiting human review. `POST /runs` is still the Module 002 body, including `sanitized: true`.

- `production_registry()` registers `text_plain` version `1` for `text/plain` only. The other four contract types resolve as internal `adapter_not_implemented`. That code is not a public API error.
- Canonicalization succeeds with zero derived nodes. The original string is not copied into a child.
- Parser version is outside the Goal Lock, `source_digest`, and submission identity. A newer parser does not reprocess an accepted run. Replay is not implemented.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.

## M003 Slice C — ingestion kernel (14 October 2026)

Status: kernel only, awaiting human review. No JSON, HTML, or RFC822 parser is registered. The running submission path is still Module 002.

- Schema remains `0003_secure_ingestion`. Fresh, `vetoq_test`, and development `vetoq` match on content-node columns, checks, the immutability function, and the Alembic revision.
- Budgets, declared-type normalization, the adapter registry, and the future submission identity live in `vetoq.ingestion`. The registry starts empty.
- Parser version is not part of the Goal Lock and not part of that future submission identity.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.

## M003 Slice B — schema (14 October 2026)

Status: persistence only, awaiting human review. No parser, adapter registry, API body change, or UI change is included.

- Alembic head is `0003_secure_ingestion`. Readiness expects that revision.
- `content_nodes` gained nullable `declared_media_type`, `representation_kind`, `parser_id`, `parser_version`, `charset`, and `byte_size`. NULL on existing rows means not recorded.
- INGEST-001 stays PARTIAL. MULTI-001 stays PLANNED.
- A fresh database migrated from base through `0003_secure_ingestion` and was dropped. `vetoq_test` and development `vetoq` then upgraded additively from `0002_worker_claim`. Development row counts stayed workspaces 22, runs 13, content_nodes 14, content_edges 1, audit_events 69, and every existing content node stayed NULL on the new columns.
- Focused Pytest passed 78 tests. Ruff and strict mypy passed. Playwright and `pnpm verify` were not run.

## M003 Slice A — specification (13 October 2026)

Status: specification complete, awaiting human review. No migration, API, worker, UI, or dependency change is included.

- The normative spec is [modules/003-universal-secure-ingestion.md](modules/003-universal-secure-ingestion.md).
- [ADR 0003](adr/0003-declared-format-ingestion.md) freezes declared-format adapters, one Goal Lock source, and PostgreSQL text storage.
- [Change record 0001](change-control/0001-ingest-001-wording.md) holds the future INGEST-001 sentence. The registry row was not edited and stays PARTIAL.
- MULTI-001 stays PLANNED. The supported set is `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`.
- The next implementation step, after review, is Slice B in that specification. The public-site redesign is Slice J.

## Module 002 runtime baseline

**Module 002 implementation is the verified runtime, awaiting any remaining human review and manual Git workflow.**

Verified on **9 October 2026 (Asia/Calcutta)**. Read [the Module 002 verification record](modules/002-verification.md) for the acceptance table, provider observations, dependency rationale, test denominators, and limitations.

## M002 stabilization slice 1 — identity / workspace / test-database boundary (12 October 2026)

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
  - The persisted run `128c8010-…` has principal `user_3KS…` (32 characters). That principal matches the active `reviewer` membership in "Demo support" (`00000000-0000-4000-8000-00000000000a`).
  - The browser's `/me` JSON was not pasted back, so the response body itself is not recorded.
- **Observation for the next slice.** That run remains `QUEUED`, with one audit event (`RUN_ACCEPTED`). No worker was running during validation, so this is not attributed to the identity boundary.

## M002 stabilization slice 2C — review / separation of duties (12 October 2026)

Status: complete and awaiting human review. Two-principal production review semantics are proven through isolated PostgreSQL integration tests using the real production authorization/review/workflow code path. A second live Clerk browser principal was not available for manual E2E validation and remains an auth-E2E hardening item.

- The originating principal cannot approve the exact action (`403 self_review_prohibited`, audit `SELF_REVIEW_PROHIBITED`, review undecided and unconsumed). A different active reviewer approves that digest. The worker returns through `AUTHORIZING`, Action Guard emits `ACTION_ALLOW`, and the same transaction writes one ticket, one receipt, and consumes the review. Read-back reaches `COMPLETED`.
- Negative proofs on `vetoq_test` write zero tickets: self-review, outsider and non-reviewer, inactive reviewer, expired review, consumed-approval replay, digest mismatch, argument mutation, Goal Lock scope mismatch despite approval, reviewer membership revoked after approval, originator membership revoked before execution, and cancellation after approval.
- Review eligibility is a backend field. The run page shows approve and reject only when that field is true, and it shows the exact action, evidence summary, and expiry. A verified-ticket link requires `verified_at`.
- Development run `0110239d-7409-4f08-a289-33134a5d4303` had already passed its Goal Lock expiry, so one worker tick closed it as `EXPIRED` with no review and no write. That is retained history, not a product gap.
- Focused verification on 12 October 2026: Ruff and strict mypy passed. `tests/test_action_guard.py` and `tests/test_database_integration.py` on `vetoq_test`: 37 passed. Run-view Vitest: 5 passed. The development database was not used for integration setup.

## M002 stabilization slice 3 — worker / recovery / concurrency (12 October 2026)

Status: complete and awaiting human review. Goal Lock, Action Guard, and review semantics are unchanged.

- One run failure is quarantined with a stable reason (`source_integrity_failure`, `provider_invalid_output`, `worker_failure`, or the provider code) and the worker continues with later eligible runs.
- Claim selection uses `FOR UPDATE SKIP LOCKED`. The run row is the claim lock. Workspace and membership rows are locked only inside `authorize()`, so inference and human review do not hold database locks.
- A stale fence cannot insert an action after a newer worker reclaims the lease. Two workers claim one run once. Two independent runs overlap inside inference.
- Retryable provider failures keep the run in `PROPOSING` with a bounded lease backoff (`2 ** attempts` seconds, cap 8) and then fail closed. No second provider is introduced.
- `run_worker` finishes the in-flight tick, then stops accepting work on Ctrl+C/SIGTERM or a stop signal. Logs carry `run_id` and reason codes, not source text or secrets.
- Alembic `0002_worker_claim` adds `runs_claimable` and `reviews_unresolved_expiry`. At the close of slice 3, `vetoq_test` was at that revision and the development database was still at `0001_security_slice` until `pnpm db:migrate`. Slice 4 confirmed both databases are at `0002_worker_claim`. Readiness expects that revision.
- Focused verification: Ruff, strict mypy, and 68 passed across `test_action_guard.py`, `test_database_integration.py`, `test_health.py`, `test_provider.py`, and `test_schema.py`.

## M002 stabilization slice 4 — repository hygiene and frontend foundation (12 October 2026)

Status: complete and awaiting human review. Approved security semantics were not changed.

- Development and test databases are both at `0002_worker_claim`.
- Stage labels come from persisted run state. A proposal is `PROPOSED` or the Action Guard verdict, not `PENDING`, after model completion. Goal Lock is `SEALED`. Source and findings are `RECORDED` or `NONE`, not a verification claim. A ticket is `VERIFIED` only when `verified_at` is set.
- Run polling retries with bounded backoff, stops on terminal states, polls `AWAITING_REVIEW` every 15 seconds, and requests events after the last sequence.
- Canonical color tokens live in `globals.css`. `vetoq.css` aliases them. Page-level `overflow-x: hidden` was removed. Clerk’s hosted card uses the paper and plum tokens.
- The Groq client stays on `httpx2` 2.13.1. Starlette 1.7.0, which FastAPI 0.142.2 requires, imports `httpx2` for `TestClient` and emits `StarletteDeprecationWarning` when only canonical `httpx` is installed. Pytest treats warnings as errors, so that import cannot load. `httpx2` also uses `truststore` for the operating-system certificate store; canonical `httpx` 0.28.1 would switch the Groq client to the certifi bundle. The provider only uses `Client`, timeouts, `post`, and `HTTPError`/`TimeoutException`.
- Installed Clerk 7.9.11 deprecates `createRouteMatcher` for the next major release, in favor of auth checks inside each protected page, layout, and route. Moving `protect()` out of `proxy.ts` would change the established BFF boundary, so the matcher stays for a dedicated Clerk upgrade. `proxy.ts` was not removed.
- `class-variance-authority` 0.7.1 types the status-badge tones. No Radix or default shadcn components were added; the current screens do not need overlays, menus, dialogs, tooltips, or tabs.
- Membership SQL stays at each call site. The statements differ in joined columns, role filters, and row locks, so one helper would risk changing isolation or lock order.
- `baseUrl` was removed from the web tsconfig. `@/*` stays relative to that file.

## M002 stabilization slice 5 — production contracts (12 October 2026)

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
