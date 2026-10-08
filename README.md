# VETOQ

**Trust the Goal. Verify the Action.**

An execution-security product being built for **ET AI Hackathon: Agentic Edition, presented by Accenture** — Problem Statement 2: **Agentic Cybersecurity — Prompt Injection Firewall**.

VETOQ's thesis is to verify both suspicious inputs and whether an agent's proposed action remains inside the user's authorization. **AI output is evidence, not authority.** Privileged execution will be owned by deterministic policy and an Action Guard.

## Current status

**Module 001: repository foundation.** The implemented runtime is a neutral responsive application shell and a health-only FastAPI service. PostgreSQL local configuration and engineering checks are provided.

**Not implemented:** prompt-injection detection, Goal Lock runtime, Action Guard, model calls, tools/tickets, business tables, multimodal ingestion, authentication integration, dashboards, or product evaluation. This build does not provide prompt-injection protection. No public deployment or achieved F3/D3 level is claimed.

The intended coverage remains all nine official attack families and heterogeneous multimodal inputs. F3 requires at least seven detected categories; D3 requires heterogeneous multimodal input with demonstrably high reliability. Claims require reproducible evidence. Module 002's text slice is a starting point, not a reduced final goal.

## Prerequisites

- Node.js **22.20 or newer within 22.x**; verified runtime details are in docs/handoff.md.
- pnpm **11.15.1** (pinned in packageManager).
- uv; verified with **0.11.26**.
- Python **3.12.x**; uv can select/install a compatible interpreter.
- Docker with Compose v2 and a running Linux-container engine for local PostgreSQL.
- Network access for the initial dependency and test-browser downloads.

Use maintained official installers to provision missing tools. Setup never requires Git automation. No model account or API key is required for Module 001.

## Local setup

Run from the repository root in PowerShell (the package commands also work on other platforms):

```powershell
pnpm install --frozen-lockfile
uv sync --locked --directory apps/api
pnpm browsers:install
Copy-Item .env.example .env
```

Edit the untracked .env and replace the local password in BOTH POSTGRES_PASSWORD and VETOQ_DATABASE_URL. Use URL encoding when needed in a database URL. The example values are placeholders, not credentials. Never commit .env.

```powershell
pnpm db:config
pnpm db:up
docker compose ps
pnpm dev:web
```

In a second terminal:

```powershell
pnpm dev:api
```

Open **http://127.0.0.1:3000**. API liveness is **http://127.0.0.1:8000/health/live**; readiness is **http://127.0.0.1:8000/health/ready**. Development servers bind to loopback.

If ports are occupied, set POSTGRES_PORT=55432 and change the database URL to match in your untracked .env. For a different API port, run:

```powershell
uv run --locked --directory apps/api uvicorn vetoq.main:create_app --factory --app-dir src --host 127.0.0.1 --port 18000
```

Do not stop unrelated services to free these ports.

The shell does not require PostgreSQL. The API can start in development without a database URL, but readiness then returns 503 with database_not_configured. A configured unavailable database returns 503 with database_unavailable. Readiness returns 200 only after SELECT 1 succeeds; no schema or business tables are created.

Use pnpm db:down to stop local infrastructure while preserving its volume. Do not delete the volume to fix a configuration problem. Docker's database initialization settings apply to a new data directory; changing the example password does not rotate an existing database's credentials.

## Verification

```powershell
pnpm verify
```

This checks repository formatting; frontend lint, strict types, unit tests, and production build; Python lint/format, strict typing, and tests; then browser validation against the production shell. It exits on failure and does not silently skip browser checks.

The required foundation checks pass in the verified environment. A supplemental full dependency audit still reports one high **development-only** advisory with no published patch; the production-only audit is clean. See [the verification record](docs/modules/001-verification.md) before accepting dependency risk.

Individual commands:

| Command                                                   | Check                                                                      |
| --------------------------------------------------------- | -------------------------------------------------------------------------- |
| pnpm format:check                                         | Prettier on supported source/document/config files                         |
| pnpm verify:web                                           | ESLint, TypeScript, Vitest, Next.js production build                       |
| pnpm verify:api                                           | Ruff lint/format, strict mypy, Pytest                                      |
| pnpm test:browser                                         | Chromium, Firefox, WebKit shell/accessibility/viewport checks; build first |
| pnpm db:config                                            | Compose validation using the labeled example configuration                 |
| docker compose exec postgres pg_isready -U vetoq -d vetoq | Actual database readiness after startup                                    |

pnpm format and uv run --locked --directory apps/api ruff format . deliberately rewrite formatting; verification commands only check it. Dependency caches, browsers, .venv, build output, and reports are ignored.

Browser binaries default to .cache/ms-playwright; override PLAYWRIGHT_BROWSERS_PATH if necessary. The API helper uses .cache/uv unless UV_CACHE_DIR is set. For uv setup on a restricted host, set a writable UV_CACHE_DIR before uv sync.

Automated accessibility checks do not prove complete WCAG conformance. Actual check outcomes and environmental limitations belong in [handoff](docs/handoff.md), not promotional badges.

## Configuration and deployment boundary

Settings load VETOQ_* variables from the environment or the root .env, with environment variables taking precedence. Trusted hosts must be an explicit JSON list without wildcards. Credentials are represented as secrets and not included in health errors.

Production mode requires an explicit host list, a PostgreSQL URL with a non-placeholder password, and sslmode=verify-full. Configure the trusted CA through the PostgreSQL client mechanism as appropriate. These checks validate configuration; they do not install TLS, identity, network controls, or deploy the product. No wildcard CORS, public business API, or password-auth system is introduced.

The Compose profile is **local development only**: PostgreSQL is exposed on loopback and uses a persistent named volume. Production identity/hosting and full security operations remain future approved work.

## Architecture direction

Next.js/React/strict TypeScript/Tailwind → FastAPI/Pydantic → PostgreSQL. A later durable runner shares the backend codebase. Model access stays behind a provider interface. Deterministic policy and Action Guard remain independent of providers.

SQLAlchemy/Alembic arrive with actual Module 002 persistence. LangGraph, object storage, classifiers, and format parsers remain deferred until justified. There is no Kafka, Kubernetes, Redis, vector store, or microservice platform.

## Repository map

- apps/web — neutral shell, frontend tooling, shell unit/browser checks.
- apps/api — health API, validated settings, Python tooling and tests.
- scripts — Windows-compatible verification/development helpers.
- docs — durable product, architecture, security, design, evaluation, ADR, and module contracts.
- compose.yaml — local PostgreSQL configuration, no business initialization scripts.

## Continue safely

Start with [AGENTS.md](AGENTS.md), [handoff](docs/handoff.md), and the active [Module 001 specification](docs/modules/001-foundation.md). [Module 002](docs/modules/002-security-slice.md) is planned and requires separate approval.

Key references: [product](docs/product.md), [architecture](docs/architecture.md), [threat model](docs/threat-model.md), [security contracts](docs/security-contracts.md), [evaluation methodology](docs/evaluation.md), and [design system](docs/design-system.md).

Git/GitHub are human controlled. Coding agents never stage, commit, push, create/switch branches, or operate the repository lifecycle. They report suggested commit groups.

**Official deadline:** 11 October 2026, 11:59 PM IST. **Internal freeze:** 11 October 2026, 8:00 PM IST.
