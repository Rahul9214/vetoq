# Engineering context

Repository operating notes. Product, security, and architecture rules live in the contracts listed first in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md). If two of those higher contracts contradict each other, stop and report the contradiction.

## Layout

| Path           | Role                                                                 |
| -------------- | -------------------------------------------------------------------- |
| `apps/web`     | Next.js UI, Clerk session, same-origin BFF, unit tests               |
| `apps/api`     | FastAPI, worker, domain modules, Alembic, Pytest                     |
| `scripts`      | Development and verification helpers                                 |
| `docs`         | Canonical contracts, ADRs, module specifications, historical records |
| `compose.yaml` | Local PostgreSQL only                                                |

JavaScript uses pnpm. Python uses uv. Python is 3.12. Do not add a provider SDK, LangGraph, Redis, a vector store, or object storage to Module 002.

## Commands

From the repository root:

| Command                | Effect                                                               |
| ---------------------- | -------------------------------------------------------------------- |
| `pnpm dev:web`         | Web on `localhost:3000`. Do not bind the web process to `127.0.0.1`  |
| `pnpm dev:api`         | API on `127.0.0.1:18000`                                             |
| `pnpm dev:worker`      | Long-running worker                                                  |
| `pnpm worker:once`     | One worker step                                                      |
| `pnpm db:migrate`      | Alembic against the database in the environment                      |
| `pnpm admin:provision` | Workspace and membership for one Clerk subject                       |
| `pnpm retention:run`   | Delete expired content and audit rows older than 30 days             |
| `pnpm verify:web`      | ESLint, strict types, Vitest, production build                       |
| `pnpm verify:api`      | Ruff, strict mypy, Pytest                                            |
| `pnpm verify`          | Full repository gate, including browsers. Not the default inner loop |

## Environments

Root `.env` holds API, database, and Groq settings. `apps/web/.env.local` holds the Clerk keys and `VETOQ_API_URL`. Examples contain placeholders only.

`VETOQ_DATABASE_URL` is the development database `vetoq`. `VETOQ_TEST_DATABASE_URL` must be a different database whose name ends in `_test`. Integration tests and the Groq smoke refuse to run otherwise. They cancel active runs in the test database. They must not be pointed at development data.

Both databases are expected at Alembic revision `0007_lineage_execution_lookup`. Default Alembic uses the development URL. Do not migrate the test database by changing the shared `.env` and forgetting to restore it.

## Current module

M003, universal secure ingestion, is complete at GREEN B. Its specification is [modules/003-universal-secure-ingestion.md](modules/003-universal-secure-ingestion.md). Schema readiness is `0007_lineage_execution_lookup`. The live `POST /runs` path is declared-format ingestion for `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`. `media_type` is required. `sanitized` is rejected. Historical Module 002 rows stay on the legacy worker path. PDF, Office, images, audio, archives, URLs, MCP, arbitrary binary, file upload, and malware scanning are unsupported. I1 is the authenticated Workbench. I2 is the authenticated run narrative over persisted evidence and transform steps. Slice J is the public execution narrative and the Clerk sign-in shell. The lavender field is the pre-footer close, not the hero. Slice K closed Module 003: INGEST-001 is IMPLEMENTED for the five declared formats, with unsupported formats failing closed. MULTI-001 stays PLANNED. SEC-001, UX-001, and A11Y-001 stay PARTIAL. M004 (provenance and execution lineage) is complete at GREEN B. Its specification is [modules/004-provenance-lineage.md](modules/004-provenance-lineage.md) and [ADR 0004](adr/0004-run-scoped-relational-lineage.md). Schema readiness is `0007_lineage_execution_lookup`. There is no lineage UI. PROV-001 and LINE-001 are IMPLEMENTED for their approved sentences. OBS-001 and SEC-001 stay PARTIAL. Do not start M005 from this note. Browser release tests use `scripts/e2e-browser.mjs`, which serves `http://localhost:3000` through a test API on `127.0.0.1:18010` and `VETOQ_TEST_DATABASE_URL`.

## Module 002 runtime

Text-only security slice. Identity is Clerk plus local membership. The model is Groq `openai/gpt-oss-120b` behind a provider-neutral adapter. The only real tool is `tickets.create` version 1 into PostgreSQL. Decision outcomes are ALLOW, REVIEW, and BLOCK. The worker leases, fences, and fails closed per run.

## Known debt

- `vetoq.css` is still a large custom stylesheet and still has charcoal panels.
- Clerk `createRouteMatcher` is deprecated in the installed SDK and remains until a dedicated upgrade.
- Membership SQL is repeated where the statements differ in locks and filters.
- `httpx2` stays because Starlette 1.7.0's test client requires it.
- The `runs` check constraint still names `INSPECTING`. The workflow does not write that state. The extra allowed value is retained as backward-compatible schema debt; `0001` and `0002` were not rewritten and no new migration was added.
- A second live Clerk reviewer was not used for the review proof.
- No production host, metrics pipeline, or measured SLO exists.

## Git

Git and GitHub are human controlled. Agents do not stage, commit, push, pull, switch, reset, clean, stash, merge, or rebase. Read-only status and diff are allowed. Prefer `GIT_OPTIONAL_LOCKS=0`.
