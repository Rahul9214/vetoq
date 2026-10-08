# VETOQ agent operating contract

VETOQ — **Trust the Goal. Verify the Action.**

## Read before working

Read README.md, docs/handoff.md, the active specification in docs/modules/, docs/product.md, docs/architecture.md, applicable docs/adr/, and docs/threat-model.md and docs/security-contracts.md. Read the relevant source and tests before changing behavior. This repository, not conversation memory, is the durable source of truth. Resolve documentation/code discrepancies explicitly.

## Scope and ownership

Only Module 001 (repository foundation) is authorized. Module 002 and subsequent modules require separate human approval. Do not implement detectors, Goal Lock runtime behavior, Action Guard, model calls, tickets, business tables, attack simulations, dashboards, or multimodal ingestion in Module 001. Material architecture/scope changes require consultation before implementation. Routine implementation choices inside approved scope do not require repeated permission.

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
- No LangGraph, model SDKs, OCR, PDF/DOCX tools, Redis, vector stores, Motion, or object storage in Module 001.

## UX requirements

Maintain obsidian/graphite surfaces, restrained emerald/jade and amber/copper semantics, legibility, and visible focus. No dominant blue, generic AI dashboard, or fake metrics. Validate 320, 360, 390, 430, 768, 1024, 1280, 1440, and 1920 px. Accessibility and responsiveness are release criteria, not polish. Use semantic HTML, keyboard access, reduced-motion support, adequate contrast, and non-color status labels.

## Validation and completion

Use the root pnpm verify command and the setup instructions in README.md. Run frontend lint, strict types, tests, production build; backend Ruff lint/format checks, strict mypy, Pytest; and browser accessibility/viewport checks when the UI changes. Fix genuine failures; never weaken checks merely to pass. Record blocked checks honestly. Inspect the entire working change, including untracked files, before reporting completion. Do not claim a service ran when only its configuration was checked.

Update docs/handoff.md with implemented scope, exact verification commands/results, limitations, next authorized task, and outstanding decisions. Keep implemented/planned/target/deferred explicit. Completion reports include acceptance status, files created/modified/removed, dependencies and reasons, tests/results, responsive/accessibility observations, risks, read-only branch/status/diff stat, and suggested commit groups. Never begin the next module implicitly.

## Locked product constraints

The official categories and F1/F2/F3/D1/D2/D3 definitions are recorded in docs/product.md from the owner's verified organizer PDF. F3 means at least seven detected categories; VETOQ targets all nine. D3 requires highly heterogeneous multimodal inputs and demonstrably high reliability. Text-only Module 002 is an initial slice, not reduced final scope. Claims require reproducible evidence.

Official deadline: 11 October 2026, 11:59 PM IST. Internal freeze: 11 October 2026, 8:00 PM IST. Do not replace the freeze with an earlier assumption.
