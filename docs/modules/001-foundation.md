# Module 001 — Repository foundation

**Authorization:** approved by the human owner. Module 002 is not authorized.

## Objective

Establish reproducible tooling, durable engineering documentation, neutral responsive Next.js shell, validated FastAPI factory with foundation health checks, and local PostgreSQL configuration.

## Included

Repository governance and handoff; product, architecture, threat, security-contract, evaluation, design, and module documentation; ADRs; pinned pnpm/uv manifests and locks; frontend ESLint/TypeScript/Vitest/Testing Library; Python Ruff/mypy/Pytest; root verification commands; real browser checks for shell reflow, focus, and automated accessibility.

Playwright/axe are used now solely to validate mandatory foundation UI acceptance. No product E2E flow or security fixture is introduced.

## Explicit exclusions

No prompt-injection detector, Goal Lock runtime, Action Guard, model call or SDK, ticket execution, findings, attack simulation, business tables, migration, LangGraph, multimodal parser, dashboard, evaluation result, identity-provider implementation, or public deployment.

## Acceptance

| ID    | Required outcome                                                                                                                 |
| ----- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1–6   | Operating rules, product boundaries, architecture, threat model, documented future contracts, and Modules 001/002 specifications |
| 7–8   | Required JavaScript/Python dependencies pinned and locked                                                                        |
| 9–12  | Shell and API run, settings validate, local PostgreSQL setup is documented and reproducible                                      |
| 13–16 | Frontend lint, strict typing, tests, production build pass                                                                       |
| 17–19 | Python lint/format, strict typing, foundation tests pass                                                                         |
| 20–23 | No product functionality, fabricated runtime data, exposed secrets, or misleading documentation                                  |
| 24    | Another agent can continue through repository documents alone                                                                    |

The human exclusively controls Git. A Git diff omits untracked new files; review all new files explicitly. Inspect complete changes and remove unused/dead/debug artifacts. Fix real check failures. Report blocked execution honestly rather than marking it passed.

## Verification

Root pnpm verify runs formatting, frontend lint/types/unit/build, backend lint/format/types/tests, and production-shell browser tests. PostgreSQL Compose configuration and actual database startup are separate checks because they require Docker. See README.md for commands and docs/handoff.md for actual observations.
