# VETOQ agent operating contract

VETOQ — **Trust the Goal. Verify the Action.**

## Read before working

Obey the source-of-truth order in [docs/PRODUCT_CONTRACT.md](docs/PRODUCT_CONTRACT.md):

1. `docs/PRODUCT_CONTRACT.md`
2. `docs/SECURITY_INVARIANTS.md`
3. `docs/ARCHITECTURE_CONTRACT.md`
4. `docs/DATA_CONTRACT.md`
5. `docs/API_CONTRACT.md`
6. `docs/AGENT_CONTRACT.md`
7. `docs/TOOL_EXECUTION_CONTRACT.md`
8. `docs/UI_UX_CONTRACT.md`
9. Accepted ADRs
10. The current module specification
11. `docs/ENGINEERING_CONTEXT.md`
12. The verified implementation and its tests

If two higher-priority contracts materially contradict each other, stop and report the contradiction. Do not choose silently.

Then read README.md and docs/handoff.md. Older product, architecture, security, design, threat, and evaluation notes remain as module context and must not override the contracts. Read the relevant source and tests before changing behavior. This repository, not conversation memory, is the durable source of truth. Resolve documentation/code discrepancies explicitly.

## Scope and ownership

Module 001 is complete. Module 002 is complete: the text-only security vertical slice recorded in `docs/modules/002-security-slice.md`. Module 003 (universal secure ingestion) is complete at GREEN B as of 15 October 2026 and is the stable baseline; its specification is `docs/modules/003-universal-secure-ingestion.md`. Module 004 (provenance graph and execution lineage) is complete at GREEN B; its specification is `docs/modules/004-provenance-lineage.md`. Schema readiness is `0007_lineage_execution_lookup`. There is no lineage UI. Module 005 and later modules are not authorized and require separate human approval. Do not expand a module into dashboards, external ticket integrations, multimodal input, or other later scope. Material architecture/scope changes require consultation before implementation. Routine implementation choices inside approved scope do not require repeated permission.

Git and GitHub are HUMAN CONTROLLED. Never initialize repositories, create/switch branches, stage, commit, push, pull, merge, rebase, reset, stash, alter remotes, create issues/PRs, or otherwise mutate Git state. Read-only status/diff/log/branch inspection is permitted; prefer GIT_OPTIONAL_LOCKS=0. Report suggested Conventional Commit groups only. Never automate the owner's lifecycle.

## Engineering and security

- AI OUTPUT IS EVIDENCE, NOT AUTHORITY. Future privileged execution must pass deterministic authorization.
- Keep Goal Lock, policy, and Action Guard provider-independent. Model adapters supply evidence/proposals, never authority.
- Use cohesive typed modules, explicit contracts, structured safe errors, input limits, secure configuration, and fail-closed security behavior.
- No fabricated runtime findings, scores, traces, tool results, latency, dashboards, or business/evaluation metrics. Test/evaluation fixtures must be labeled and excluded from operational metrics.
- Never place credentials or private reasoning in code, logs, fixtures, screenshots, or documentation. Environment examples contain placeholders only.
- Retain provenance across transformations. Source labels and model explanations are not permission grants.
- Do not introduce unused dependencies, speculative abstractions, empty directories, dead code, or product placeholders that imply functioning security.
- Use pnpm for JavaScript and uv for Python. Pin direct dependencies and commit reproducible lockfiles through the human workflow. No floating latest specifications.
- No LangGraph, provider SDK, OCR, PDF/DOCX tools, Redis, vector store, Motion, or object storage in Module 002.
- No graph database, Kafka, Redis, event bus, vector store, or new service in Module 004. Lineage is run-scoped relational data in PostgreSQL. It describes what happened and never grants authority.

## UX requirements

Follow [docs/UI_UX_CONTRACT.md](docs/UI_UX_CONTRACT.md). The brand is paper, ivory, stone, champagne, ink, graphite, lavender, plum, copper, coral, amber, and rose. Semantic ALLOW, REVIEW, and BLOCK colors are not the brand. No dominant dark, blue, or green theme, and no fake operational status. Validate 320, 360, 390, 430, 768, 1024, 1280, 1440, and 1920 px. Accessibility and responsiveness are release criteria, not polish. Use semantic HTML, keyboard access, reduced-motion support, adequate contrast, and non-color status labels.

## Validation and completion

Use the root pnpm verify command and the setup instructions in README.md. Run frontend lint, strict types, tests, production build; backend Ruff lint/format checks, strict mypy, Pytest; and browser accessibility/viewport checks when the UI changes. Fix genuine failures; never weaken checks merely to pass. Record blocked checks honestly. Inspect the entire working change, including untracked files, before reporting completion. Do not claim a service ran when only its configuration was checked.

Update docs/handoff.md with implemented scope, exact verification commands/results, limitations, next authorized task, and outstanding decisions. Keep implemented/planned/target/deferred explicit. Completion reports include acceptance status, files created/modified/removed, dependencies and reasons, tests/results, responsive/accessibility observations, risks, read-only branch/status/diff stat, and suggested commit groups. Never begin the next module implicitly.

## Locked product constraints

The official categories and F1/F2/F3/D1/D2/D3 definitions are recorded in docs/product.md from the owner's verified organizer PDF. F3 means at least seven detected categories; VETOQ targets all nine. D3 requires highly heterogeneous multimodal inputs and demonstrably high reliability. Text-only Module 002 is an initial slice, not reduced final scope. Claims require reproducible evidence.

The hackathon deadline of 11 October 2026, 11:59 PM IST and the internal freeze of 8:00 PM IST are historical event dates. They are not the current engineering schedule.
