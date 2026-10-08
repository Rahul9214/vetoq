# Architecture

## Implemented foundation

A pnpm workspace contains a Next.js App Router shell in apps/web. A uv-managed FastAPI application lives in apps/api. Its only endpoints are foundation health checks. PostgreSQL local infrastructure is described by compose.yaml; no business schema, migration, workflow runner, model integration, or product API exists.

## Planned minimum architecture

Browser → authenticated API → persisted run → durable runner → inspection → model proposal → deterministic Action Guard → registered adapter → verified target result. Evidence and audit persist in PostgreSQL. The API and runner share one modular Python codebase. They are deployment processes, not separate business microservices.

1. Identity/ingress verifies principal, membership, limits, and content structure.
2. Evidence/analysis preserves sources and transformations and produces bounded findings.
3. Workflow owns deterministic states, counters, interruption, retry, and recovery.
4. Authorization owns Goal Lock, policy, approval integrity, and the final guard.
5. Execution owns a closed tool registry, canonical arguments, and the reference ticket adapter.
6. Persistence/audit owns transactions and immutable historical evidence.

Model access is always behind a provider interface. A first implementation may configure one adapter. Provider SDK types must not enter policy or domain contracts. Models cannot set grants, approve actions, or receive tool/database credentials. Model-produced data stays untrusted.

## Planned contracts and trust

See security-contracts.md. Identity and confirmed scopes provide authority. External content, derived text, detector output, and agent output provide evidence only. Provenance is not hidden chain-of-thought. Protection applies only where the dispatcher completely mediates side effects.

The first tool is tickets.create in a reference support application. It must persist an actual ticket. Its local transaction can atomically commit the ticket, execution receipt, and audit outcome. External adapters later need their own idempotency and reconciliation contracts; an unknown result is never a success notification.

## Planned workflow

QUEUED → INSPECTING → PROPOSING → AUTHORIZING. ALLOW leads to EXECUTING → VERIFYING → COMPLETED. Review leads to AWAITING_REVIEW and then reauthorization. A block/restriction may permit one bounded continuation without new privileges. NO_ACTION, BLOCKED, FAILED, CANCELLED, and EXPIRED are explicit terminal states. External tools may require OUTCOME_UNKNOWN.

Use a small persisted state machine initially. Claim pending work with short database transactions and leases. Never hold locks while waiting for inference or review. Reconcile committed results after restart instead of executing again. A model transient error permits at most one retry; unknown non-idempotent side effects are not blindly retried.

## Planned schema and API

Module 002 introduces workspaces, memberships, runs (including an immutable Goal Lock), content_nodes, content_edges, findings, actions, reviews, executions, audit_events, and tickets. Foreign keys preserve run/workspace ownership; uniqueness protects submission keys, execution per action, ticket per run, and event sequence. No such tables exist in Module 001.

Planned API: /api/v1/me; create/list/read runs; cursor-based run events; authorized content; cancel; exact-action review decision; read ticket. All product APIs require verified identity and workspace authorization. There is no public generic tool execution endpoint. Poll initially; defer SSE until justified.

## Failure principles

Missing authority, unavailable policy, invalid output, or failed required analysis prevents execution. Database failure prevents durable acceptance and side effects. An incomplete scan is not clean. Model failures are operational errors, not attacks. Human approval expires and never overrides hard prohibitions. Cancellation prevents future dispatch but cannot undo an already committed action.

## Deployment and complexity

One web process, API, PostgreSQL, and later a runner are enough initially. Same-origin identity/routing will be selected before public product deployment. Foundation health endpoints are not an authentication implementation. No model endpoint, identity provider, public host, or deployment URL is currently configured.

Defer LangGraph until state/interrupt complexity justifies it, object storage until retained binaries exist, and a dedicated classifier until evaluation shows benefit. Reject Kafka, Kubernetes, vector search, event buses, and microservices for current scope. No graph library or animation runtime is needed for the neutral shell.

## Sequence after the foundation

Module 002: text-only guarded real action. Later approved modules: heterogeneous extraction, robust multimodal evaluation, integration hardening, and submission evidence. Module 002 does not reduce the final D3 ambition. Material changes need owner consultation.
