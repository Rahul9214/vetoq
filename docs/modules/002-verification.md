# Module 002 verification record

Verified on **9 October 2026 (Asia/Calcutta)** for `feat/002-security-vertical-slice`. This record distinguishes engineering checks and integration smokes from product efficacy claims.

## Acceptance evidence

| Requirement                             | Result                       | Evidence                                                                                                                                                                                  |
| --------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Immutable Goal Lock before inference    | PASS                         | Typed frozen contract, database immutability trigger, unit and PostgreSQL tests                                                                                                           |
| Provenance and bounded derivation       | PASS                         | Original node, digest/trust metadata, bounded Base64 children, depth/volume failure tests                                                                                                 |
| Real contextual model analysis          | PASS                         | Live Groq calls using `openai/gpt-oss-120b`; strict structured output validated                                                                                                           |
| Provider-independent authority          | PASS                         | Provider contracts/adapters have no imports into pure Action Guard; model has no execution capability                                                                                     |
| Authorized real action                  | PASS                         | Live Groq-to-PostgreSQL smoke completed one `tickets.create`, one write, read-back verified                                                                                               |
| Same-tool unauthorized action           | PASS                         | Controlled PostgreSQL integration targeted workspace B from workspace-A Goal Lock; persisted `BLOCK`, `GOAL_SCOPE_MISMATCH`, zero tickets                                                 |
| ALLOW / BLOCK / REVIEW                  | PASS                         | Pure guard and UI states; exact review digest, expiry, use state and current authority rechecked                                                                                          |
| Idempotency and recovery                | PASS                         | Unique submission/action execution/ticket constraints; committed receipt reconciled by a new worker without a second write                                                                |
| Clerk identity boundary                 | PASS                         | Live configured JWKS returned one key; issuer HTTPS; focused signature/subject/authorized-party tests                                                                                     |
| Nine-family fixture coverage            | PASS as engineering coverage | 27 labeled synthetic attacks, exactly three for each official family; 20 benign controls                                                                                                  |
| Responsive/accessibility release checks | PASS automated               | 78 Playwright cases across Chromium, Firefox and WebKit (39 foundation + 39 correction-pass); nine widths, live Clerk signed-out readiness, keyboard, axe A/AA, reduced motion, 400% text |

## Exact verification results

- Backend deterministic suite: **58 passed, 11 deselected** after adding rate-limit, unavailable-service, and rejected-request cases.
- PostgreSQL integration suite: **11 passed, 58 deselected** on a disposable PostgreSQL 18.6 Alpine database after applying Alembic revision `0001_security_slice`. This includes cancellation during in-flight inference, deterministic-evidence review propagation, bounded retry failure, workspace object isolation, and persisted derived provenance.
- Frontend unit suite: **9 passed** across 3 files (`page.test.tsx`, `secure-run-form.test.tsx`, `audit-trail.test.tsx`), including wrong-workspace presentation and inert stored-XSS rendering.
- Production web build: **PASS**. Routes: `/`, `/api/v1/[...path]`, `/runs/[runId]`, `/tickets/[ticketId]`, and not-found; Clerk proxy included.
- Browser suite: **78 passed** in Chromium, Firefox, and WebKit, including configured Clerk signed-out readiness in each engine.
- Next.js 16+ proxy convention: `apps/web/src/proxy.ts` preserved without renaming; request handling validated.
- Ruff lint/format and strict mypy: **PASS**.
- Root `pnpm verify`: **PASS**.
- Alembic upgrade and schema-aware readiness: **PASS**.

## Live provider evidence

The configured Groq adapter made real calls with provider `groq`, model `openai/gpt-oss-120b`, prompt version `support-analysis/1`, and strict JSON Schema output.

- Benign synthetic support request: one call, valid typed `tickets.create` proposal for the confirmed workspace, no findings, `uncertain=false`; observed adapter elapsed time **2515 ms**.
- Adversarial synthetic request: one call, `Context Poisoning` finding, proposal remained in workspace A, `uncertain=false`; observed adapter elapsed time **1702 ms**. The provider resisted the injected workspace target, so this is not a live final-gate veto demonstration.
- End-to-end live smoke: one Groq analysis flowed through deterministic authorization to PostgreSQL; state `COMPLETED`, verdict `ALLOW`, `ticket_count=1`, `writes=1`, and read-back `verified=true`.

These three observations are integration evidence only. They do not establish recall, precision, benign-pass rate, latency percentiles, reliability, F3, or D3.

## Commands

```powershell
pnpm format:check
pnpm verify:web
pnpm verify:api
pnpm test:browser
pnpm verify
pnpm db:migrate
$env:VETOQ_TEST_DATABASE_URL = "postgresql://...disposable..."
uv run --locked --directory apps/api pytest -m integration
pnpm verify:groq
pnpm audit --prod
pnpm audit
uvx pip-audit --path apps/api/.venv/Lib/site-packages
```

Credential values, raw tokens, and raw provider payloads were never printed or recorded. Live input was synthetic.

## Corpus denominators

The smoke corpus contains 27 attack inputs: 3 each for Instruction Override, Role Change, Secret Extraction, Tool Abuse, Credential Theft, Context Poisoning, Multi-Step Jailbreaks, Encoded Instructions, and Indirect Prompt Injection. The benign corpus contains 20 controls. Tests verify structure and deterministic inspection coverage; no full corpus model run or held-out measurement was performed, so no efficacy percentages are reported.

## Dependency delta and audit

Added backend runtime dependencies: SQLAlchemy 2.1.4 for typed PostgreSQL access, Alembic 1.20.0 for versioned migrations, PyJWT 2.15.1 with cryptography 50.0.2 for Clerk JWT verification, and httpx2 2.13.1 for the direct Groq HTTP boundary. Clerk JWKS uses PyJWT. httpx2 stays because Starlette 1.7.0 TestClient requires it and it keeps OS trust-store TLS via truststore. Added frontend runtime dependency `@clerk/nextjs` 7.9.11. No model SDK or LangGraph was added.

The production-only JavaScript audit and the Python environment audit report no known vulnerabilities. `pip-audit` emitted package-metadata normalization warnings while auditing, but completed successfully. The full JavaScript audit reports one high development-only `braces@3.0.3` denial-of-service advisory through Next.js ESLint tooling. The advisory names `3.0.4` as patched, but the registry returns no matching published `braces@3.0.4`, so no resolvable upgrade exists. It must not be described as a clean full tree.

## Limitations

- Text input only; no heterogeneous or multimodal D3 evidence.
- Fixture presence and deterministic signatures do not prove model detection reliability.
- The live adversarial model resisted the unauthorized target, so deterministic final-gate veto evidence comes from a controlled typed proposal persisted through the real PostgreSQL workflow.
- Automated accessibility checks do not replace manual screen-reader and browser-zoom testing.
- No authenticated Playwright account flow was automated; browser checks prove the configured Clerk client reaches a usable signed-out state in all three engines, backend tests cover identity cryptography and authorization boundaries, and UI unit tests cover authenticated states.
- Two-principal production review semantics are proven through isolated PostgreSQL integration tests using the real production authorization/review/workflow code path. A second live Clerk browser principal was not available for manual E2E validation and remains an auth-E2E hardening item.
- Retention is an explicit operator command and requires external scheduling.
- Audit is append-only for the application role, not tamper-proof against a database administrator.
- The local ticket adapter is transactionally consistent; no exactly-once claim is made for future external systems.
- No public deployment, production Clerk instance, load test, or production performance measurement was performed.
