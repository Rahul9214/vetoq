# Agent handoff

**Module 002 implementation complete; awaiting human review and manual Git workflow. No later module is authorized.**

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

Human review and manual Git workflow are next. Do not begin multimodal ingestion, external integrations, evaluation expansion, deployment, or another module without approval. The hackathon deadline of 11 October 2026, 11:59 PM IST and the internal freeze of 8:00 PM IST are historical event dates.

## Prior Module 001 handoff record

Verified on **8 October 2026 (Asia/Calcutta)**. The following is the historical Module 001 record and is superseded where Module 002 now implements the planned capability. Read [the Module 001 verification record](modules/001-verification.md) for its original evidence.

## Read in this order

1. [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) and the rest of the hierarchy recorded there.
2. AGENTS.md, README.md, and this handoff.
3. The active module specification.
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
