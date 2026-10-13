# Architecture contract

The logical planes below are the stable architecture. The running system is a modular monolith. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md).

## Planes

### Control plane

Identity, workspace membership, Goal Lock acceptance, policy revision, review decisions, cancellation, and operator administration. Module 002 implements this as Clerk token verification, PostgreSQL membership, the confirmed support-triage envelope, and the review and cancel routes. It does not implement an enterprise policy studio or organization administration.

### Intelligence plane

Typed analysis of untrusted evidence. Module 002 has one provider-neutral adapter and one configured model. The plane may recommend and explain. It cannot grant authority, execute, or approve review. Future specialists are defined in [AGENT_CONTRACT.md](AGENT_CONTRACT.md) and are not implemented.

### Enforcement plane

The deterministic Action Guard, the closed tool boundary, idempotency, fencing, and the private dispatcher. This plane is the only path to a side effect. There is no public generic execute endpoint.

### Evidence plane

Provenance nodes and edges, findings, action digests, review records, execution receipts, read-back, and the sequenced audit log. Module 002 stores this in PostgreSQL. A cross-run lineage product and a tamper-proof external archive are not implemented.

## Deployment shape

One Next.js web process, one FastAPI process, one worker process, and PostgreSQL are sufficient for Module 002. The API and worker share one Python codebase. They are processes, not microservices.

The current repository does not include microservices, Kafka, Kubernetes, Redis, Temporal, a vector database, or an event bus. Splitting a plane into its own service requires a demonstrated operational need and an accepted ADR.

## Technology baseline

| Area        | Baseline                                                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------------------------------- |
| Web         | Next.js 16+, React, strict TypeScript, Tailwind CSS v4, customized component primitives, CVA where it types real variants |
| API         | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic                                                                     |
| Database    | PostgreSQL                                                                                                                |
| Identity    | Clerk, verified on the server                                                                                             |
| Model       | Provider-neutral adapter. The configured implementation is Groq `openai/gpt-oss-120b`                                     |
| Tool        | `tickets.create` version 1, destination `local-ticket-store`, backed by PostgreSQL                                        |
| HTTP client | `httpx2`, because the pinned Starlette test client requires it and it uses the OS trust store                             |

LangGraph, provider SDKs, object storage, OCR, and a dedicated classifier are not part of this baseline.

## Workflow states

The worker persists `QUEUED`, `PROPOSING`, `AUTHORIZING`, `AWAITING_REVIEW`, `VERIFYING`, `COMPLETED`, `NO_ACTION`, `BLOCKED`, `FAILED`, `CANCELLED`, and `EXPIRED`.

Inspection happens inside the queued claim. The database check constraint still names `INSPECTING`. Current workflow code does not write that state. There is no persisted `EXECUTING` state. ALLOW writes the ticket, moves to `VERIFYING`, and reaches `COMPLETED` only after read-back. REVIEW waits in `AWAITING_REVIEW`.

Claim selection uses `FOR UPDATE SKIP LOCKED`, a lease, and a fence. Database locks are not held during inference or human review.
