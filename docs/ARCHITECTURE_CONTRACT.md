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

### Ingestion boundary

[ADR 0003](adr/0003-declared-format-ingestion.md) and [the Module 003 specification](modules/003-universal-secure-ingestion.md) add a declared-format adapter boundary in front of this plane. The ingestion kernel defines that boundary. All five contracted adapters are registered. `POST /runs` validates with the adapter for the declared type, then the worker canonicalizes that staged original. A legacy original, whose ingestion metadata is null, remains one pasted string plus bounded Base64 derivation.

The client declares one allowlisted type. That declaration selects the adapter. The adapter does not switch on a sniff. Supported live declarations are `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`. Anything else is refused before a run exists. Before acceptance, adapter validation is pure and bounded: no network, no database write, and no model call. That pass proves deterministic processability, including derived representation count and derived text bytes. The live accept path runs that pass and then inserts one original. Unsupported embedded MIME content is refused in that pass and is not stored. Derived text stays `untrusted` and is not a second Goal Lock source. The normalized declared type is part of submission identity, not of the Goal Lock. PostgreSQL `text` stores accepted representations. Object storage is not part of this boundary. The versioned budgets live in one table in the module specification. `0003_secure_ingestion` stores nullable content metadata only. It does not add a parser. `0004_edge_steps` stores the ordered transform chain for an edge. The worker writes that chain for a new staged derivation and for a new Base64 edge. Slice I provenance presentation is not this boundary.

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

LangGraph, provider SDKs, object storage, OCR, and a dedicated classifier are not part of this baseline. M003 text adapters, when implemented, use the Python standard library. They do not add a PDF, Office, image, audio, archive, fetch, or malware-scanning library.

## Workflow states

The worker persists `QUEUED`, `PROPOSING`, `AUTHORIZING`, `AWAITING_REVIEW`, `VERIFYING`, `COMPLETED`, `NO_ACTION`, `BLOCKED`, `FAILED`, `CANCELLED`, and `EXPIRED`.

Inspection happens inside the queued claim. The database check constraint still names `INSPECTING`. Current workflow code does not write that state. There is no persisted `EXECUTING` state. ALLOW writes the ticket, moves to `VERIFYING`, and reaches `COMPLETED` only after read-back. REVIEW waits in `AWAITING_REVIEW`.

Claim selection uses `FOR UPDATE SKIP LOCKED`, a lease, and a fence. Database locks are not held during inference or human review.
