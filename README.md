# VETOQ

**Trust the Goal. Verify the Action.**

**Agent Execution Security Platform.** VETOQ governs what autonomous and semi-autonomous agents are allowed to do, not merely what they are allowed to read or generate. **AI output is evidence, not authority.**

The historical ET AI Hackathon context is recorded in [product.md](docs/product.md). It does not define VETOQ as a prompt-injection firewall. The canonical product, security, and architecture rules are in [PRODUCT_CONTRACT.md](docs/PRODUCT_CONTRACT.md).

## Current status

**Module 002: first security vertical slice.** The runtime accepts a confirmed support-triage goal and synthetic/sanitized untrusted email text, preserves provenance, combines deterministic inspection with real Groq analysis, and sends an exact typed proposal through a provider-independent Action Guard. One authorized `tickets.create` persists and verifies a real PostgreSQL ticket; the same tool targeting another workspace is blocked before any write.

Clerk supplies identity while PostgreSQL membership remains server-authoritative. The UI exposes run submission/history, provenance/findings, action status, exact review, and verified ticket outcome using actual API state. Multimodal ingestion, external tools, dashboards, public deployment, and statistically meaningful product evaluation are not implemented. No achieved F3/D3 level is claimed.

The intended coverage remains all nine official attack families and heterogeneous multimodal inputs. F3 requires at least seven detected categories; D3 requires heterogeneous multimodal input with demonstrably high reliability. Claims require reproducible evidence. Module 002's text slice is a starting point, not a reduced final goal.

## Prerequisites

- Node.js **22.20 or newer within 22.x**; verified runtime details are in docs/handoff.md.
- pnpm **11.15.1** (pinned in packageManager).
- uv; verified with **0.11.26**.
- Python **3.12.x**; uv can select/install a compatible interpreter.
- Docker with Compose v2 and a running Linux-container engine for local PostgreSQL.
- Network access for the initial dependency and test-browser downloads.

Use maintained official installers to provision missing tools. Setup never requires Git automation. Module 002 requires Groq and Clerk development credentials stored only in ignored local environment files.

## Local setup

Run from the repository root in PowerShell (the package commands also work on other platforms):

```powershell
pnpm install --frozen-lockfile
uv sync --locked --directory apps/api
pnpm browsers:install
Copy-Item .env.example .env
Copy-Item .env.example apps/web/.env.local
```

Edit root `.env` and replace every placeholder. Keep only `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, and optional `VETOQ_API_URL` in `apps/web/.env.local`. Configure the same Clerk publishable key in root `.env` for API token verification. Never commit either file.

```powershell
pnpm db:config
pnpm db:up
pnpm db:migrate
docker compose ps
pnpm admin:provision -- --workspace-id 00000000-0000-4000-8000-00000000000a --workspace-name "Demo support" --principal user_from_clerk --role reviewer
pnpm dev:web
```

In a second terminal:

```powershell
pnpm dev:api
pnpm dev:worker
```

Open **http://localhost:3000**. API liveness is **http://127.0.0.1:18000/health/live**; readiness is **http://127.0.0.1:18000/health/ready**. Development servers bind to loopback.

The web server deliberately binds to `localhost`, not `127.0.0.1`. Next.js presents middleware request URLs as `localhost`; when the server's own origin is `127.0.0.1`, Clerk's pass-through rewrite looks external and Next.js proxies the request to itself repeatedly until it hangs.

If ports are occupied, set POSTGRES_PORT=55432 and change the database URL to match in your untracked .env. For a different API port, run:

```powershell
$env:VETOQ_API_PORT = "18000"
pnpm dev:api
```

Set `VETOQ_API_URL=http://127.0.0.1:18000` in `apps/web/.env.local` before starting or restarting the web server. A signed-in product request fails closed with `database_not_configured` until `VETOQ_DATABASE_URL` is present, PostgreSQL is reachable, and the migration has been applied. Provision only the exact Clerk subject shown by the no-membership state; the development command does not grant access automatically:

```powershell
pnpm admin:provision -- --workspace-id 00000000-0000-4000-8000-00000000000a --workspace-name "Demo support" --principal user_from_clerk --role reviewer
```

Do not stop unrelated services to free these ports.

The API can start in development without a database URL, but readiness returns 503. Readiness returns 200 only when PostgreSQL is reachable and the exact Alembic revision is applied. Product endpoints require a verified Clerk token and active local membership.

Use pnpm db:down to stop local infrastructure while preserving its volume. Do not delete the volume to fix a configuration problem. Docker's database initialization settings apply to a new data directory; changing the example password does not rotate an existing database's credentials.

## Verification

```powershell
pnpm verify
```

This checks repository formatting; frontend lint, strict types, unit tests, and production build; Python lint/format, strict typing, and tests; then browser validation against the production shell. It exits on failure and does not silently skip browser checks.

The required Module 002 checks pass in the verified environment. See [the Module 002 verification record](docs/modules/002-verification.md) for exact results, live-provider evidence, audit status, and limitations.

Individual commands:

| Command                                                   | Check                                                                            |
| --------------------------------------------------------- | -------------------------------------------------------------------------------- |
| pnpm format:check                                         | Prettier on supported source/document/config files                               |
| pnpm verify:web                                           | ESLint, TypeScript, Vitest, Next.js production build                             |
| pnpm verify:api                                           | Ruff lint/format, strict mypy, Pytest                                            |
| pnpm test:browser                                         | Chromium, Firefox, WebKit shell/accessibility/viewport checks; build first       |
| pnpm verify:groq                                          | Real synthetic-only Groq-to-PostgreSQL smoke; requires `VETOQ_TEST_DATABASE_URL` |
| pnpm db:config                                            | Compose validation using the labeled example configuration                       |
| docker compose exec postgres pg_isready -U vetoq -d vetoq | Actual database readiness after startup                                          |

Database integration tests and `pnpm verify:groq` run only when `VETOQ_TEST_DATABASE_URL` is set. They refuse to start unless the database name ends in `_test`, the server reports that same name, and it differs from `VETOQ_DATABASE_URL`. They never fall back to the development database. Create and migrate the disposable database once:

```powershell
docker compose exec postgres createdb -U vetoq vetoq_test
$env:VETOQ_DATABASE_URL = "postgresql://vetoq:<local-password>@127.0.0.1:55432/vetoq_test"; pnpm db:migrate; Remove-Item Env:VETOQ_DATABASE_URL
$env:VETOQ_TEST_DATABASE_URL = "postgresql://vetoq:<local-password>@127.0.0.1:55432/vetoq_test"
```

pnpm format and uv run --locked --directory apps/api ruff format . deliberately rewrite formatting; verification commands only check it. Dependency caches, browsers, .venv, build output, and reports are ignored.

Browser binaries default to .cache/ms-playwright; override PLAYWRIGHT_BROWSERS_PATH if necessary. The API helper uses .cache/uv unless UV_CACHE_DIR is set. For uv setup on a restricted host, set a writable UV_CACHE_DIR before uv sync.

Automated accessibility checks do not prove complete WCAG conformance. Actual check outcomes and environmental limitations belong in [handoff](docs/handoff.md), not promotional badges.

## Configuration and deployment boundary

Settings load VETOQ_* variables from the environment or the root .env, with environment variables taking precedence. Trusted hosts must be an explicit JSON list without wildcards. Credentials are represented as secrets and not included in health errors.

Production mode requires an explicit host list, a PostgreSQL URL with a non-placeholder password, and sslmode=verify-full. Configure the trusted CA through the PostgreSQL client mechanism as appropriate. These checks validate configuration; they do not install TLS, identity, network controls, or deploy the product. No wildcard CORS, public business API, or password-auth system is introduced.

The Compose profile is **local development only**: PostgreSQL is exposed on loopback and uses a persistent named volume. Production identity/hosting and full security operations remain future approved work.

## Architecture direction

Next.js/React/strict TypeScript/Tailwind → same-origin Clerk BFF → FastAPI/Pydantic → PostgreSQL. A durable worker shares the backend codebase. Model access stays behind a provider interface. Deterministic policy and Action Guard remain independent of Groq.

SQLAlchemy/Alembic own Module 002 persistence. LangGraph, object storage, classifiers, and format parsers remain deferred until justified. There is no Kafka, Kubernetes, Redis, vector store, or microservice platform.

## Repository map

- apps/web — authenticated product UI, same-origin BFF, unit and browser checks.
- apps/api — health/product API, durable worker, security domain, migration, tests and fixtures.
- scripts — Windows-compatible verification/development helpers.
- docs — durable product, architecture, security, design, evaluation, ADR, and module contracts.
- compose.yaml — local PostgreSQL configuration, no business initialization scripts.

## Continue safely

Start with [AGENTS.md](AGENTS.md), [the product contract](docs/PRODUCT_CONTRACT.md), [handoff](docs/handoff.md), and the active [Module 002 specification](docs/modules/002-security-slice.md). Later modules require separate approval. Engineering commands and environment boundaries are in [ENGINEERING_CONTEXT.md](docs/ENGINEERING_CONTEXT.md).

Git/GitHub are human controlled. Coding agents never stage, commit, push, create/switch branches, or operate the repository lifecycle. They report suggested commit groups.

The hackathon deadline of 11 October 2026, 11:59 PM IST and the internal freeze of 8:00 PM IST are historical. See [the product contract](docs/PRODUCT_CONTRACT.md).
