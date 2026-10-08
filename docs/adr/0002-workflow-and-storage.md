# ADR 0002 — Explicit state machine and PostgreSQL

Status: accepted in pre-implementation architecture review. Workflow and business storage are deferred to Module 002.

## Decision

Use PostgreSQL as the initial durable store. Keep the first agent workflow a small explicit persisted state machine with short work leases and bounded retries. A local reference ticket side effect and its receipt/audit can share one transaction. Use a separate runner process from the same Python codebase when the workflow arrives.

## Why

Long inference and review require durable state, but the initial topology does not warrant LangGraph or a queue platform. Local ticket transactions support an honest, reproducible real action without early external integration complexity.

## Consequences

No business tables or speculative migration in Module 001. Its PostgreSQL use is configuration and a read-only readiness probe. Later execution uses uniqueness, rechecks, and recovery; external integrations must reconcile unknown outcomes rather than claim universal exactly-once execution.

Defer object storage until retained binaries exist, LangGraph until branch/interrupt complexity warrants it, and Redis/queues until observed scale requires them. No Kafka, Kubernetes, vector database, event bus, or model training infrastructure now.

PostgreSQL 18 local images use /var/lib/postgresql as the volume mount. Pin a supported patch tag and review security updates explicitly; never use latest. Local loopback/password configuration is not a production deployment profile.
