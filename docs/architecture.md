# Architecture

Canonical planes and the technology baseline are [ARCHITECTURE_CONTRACT.md](ARCHITECTURE_CONTRACT.md). This file is the Module 002 elaboration.

## Implemented architecture

A pnpm workspace contains a responsive Next.js product UI and same-origin Clerk-authenticated BFF in `apps/web`. A uv-managed FastAPI API and durable worker share typed domain modules in `apps/api`. PostgreSQL stores authority, provenance, findings, actions, receipts, audit events, and real reference tickets. Alembic owns the schema.

## Module 002 architecture

Browser → authenticated API → persisted run → durable runner → inspection → model proposal → deterministic Action Guard → registered adapter → verified target result. Evidence and audit persist in PostgreSQL. The API and runner share one modular Python codebase. They are deployment processes, not separate business microservices.

1. Identity/ingress verifies principal, membership, limits, and content structure.
2. Evidence/analysis preserves sources and transformations and produces bounded findings.
3. Workflow owns deterministic states, counters, interruption, retry, and recovery.
4. Authorization owns Goal Lock, policy, approval integrity, and the final guard.
5. Execution owns a closed tool registry, canonical arguments, and the reference ticket adapter.
6. Persistence/audit owns transactions and immutable historical evidence.

Model access is always behind a provider interface. A first implementation may configure one adapter. Provider SDK types must not enter policy or domain contracts. Models cannot set grants, approve actions, or receive tool/database credentials. Model-produced data stays untrusted.

## Contracts and trust

See security-contracts.md. Identity and confirmed scopes provide authority. External content, derived text, detector output, and agent output provide evidence only. Provenance is not hidden chain-of-thought. Protection applies only where the dispatcher completely mediates side effects.

The first tool is tickets.create in a reference support application. It must persist an actual ticket. Its local transaction can atomically commit the ticket, execution receipt, and audit outcome. External adapters later need their own idempotency and reconciliation contracts; an unknown result is never a success notification.

## Workflow

The implemented states are QUEUED, PROPOSING, AUTHORIZING, AWAITING_REVIEW, VERIFYING, COMPLETED, NO_ACTION, BLOCKED, FAILED, CANCELLED, and EXPIRED. Inspection happens inside the queued claim; there is no persisted INSPECTING or EXECUTING state. ALLOW moves the run to VERIFYING after the ticket write, then COMPLETED after read-back. REVIEW waits in AWAITING_REVIEW until a different reviewer decides. A hard block may permit one bounded continuation without new privileges. Older architecture notes that named EXECUTING or OUTCOME_UNKNOWN describe later external tools, not this slice.

Claim eligible work with `FOR UPDATE SKIP LOCKED`, a short lease, and a fence. Do not hold database locks during inference or human review. Reconcile a committed ticket after restart instead of writing again. Retryable provider failures use bounded attempts and lease backoff. A non-idempotent write is not repeated.

## Schema and API

Module 002 implements workspaces, memberships, runs (including an immutable Goal Lock), content_nodes, content_edges, findings, actions, reviews, executions, audit_events, and tickets. Foreign keys preserve run/workspace ownership; uniqueness protects submission keys, execution per action, ticket per run, and event sequence. Database triggers reject mutation of confirmed authority, proposals, protected content, and audit history.

API: `/api/v1/me`; create/list/read runs; cursor-based run events; authorized content; cancel; exact-action review decision; read ticket. All product APIs require verified identity and workspace authorization. There is no public generic tool execution endpoint. The UI polls; SSE remains deferred.

## Failure principles

Missing authority, unavailable policy, invalid output, or failed required analysis prevents execution. Database failure prevents durable acceptance and side effects. An incomplete scan is not clean. Model failures are operational errors, not attacks. Human approval expires and never overrides hard prohibitions. Cancellation prevents future dispatch but cannot undo an already committed action.

## Deployment and complexity

One web process, API, PostgreSQL, and worker are sufficient for Module 002. The Next.js BFF obtains the Clerk session token server-side; the API verifies issuer keys, signature, time claims, subject, and authorized party. Groq transport uses direct HTTPS behind the provider adapter. No public host or deployment URL is configured.

Defer LangGraph until state/interrupt complexity justifies it, object storage until retained binaries exist, and a dedicated classifier until evaluation shows benefit. Reject Kafka, Kubernetes, vector search, event buses, and microservices for current scope. No graph library or animation runtime is needed for the neutral shell.

## Sequence after the foundation

Module 002: text-only guarded real action. Later approved modules: heterogeneous extraction, robust multimodal evaluation, integration hardening, and submission evidence. Module 002 does not reduce the final D3 ambition. Material changes need owner consultation.
