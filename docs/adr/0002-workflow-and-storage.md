# ADR 0002 — Explicit state machine and PostgreSQL

Status: accepted and implemented for Module 002. Subordinate to the canonical contracts in [PRODUCT_CONTRACT.md](../PRODUCT_CONTRACT.md).

## Decision

Use PostgreSQL as the initial durable store. Keep the first agent workflow a small explicit persisted state machine with short work leases and bounded retries. A local reference ticket side effect and its receipt/audit share one transaction. Use a separate runner process from the same Python codebase.

## Why

Long inference and review require durable state, but the initial topology does not warrant LangGraph or a queue platform. Local ticket transactions support an honest, reproducible real action without early external integration complexity.

## Consequences

Module 001 introduced no business tables. Module 002 adds the approved eleven-table migration, uniqueness, final rechecks, and recovery. External integrations must reconcile unknown outcomes rather than claim universal exactly-once execution.

Defer object storage until retained binaries exist, LangGraph until branch/interrupt complexity warrants it, and Redis/queues until observed scale requires them. No Kafka, Kubernetes, vector database, event bus, or model training infrastructure now.

PostgreSQL 18 local images use /var/lib/postgresql as the volume mount. Pin a supported patch tag and review security updates explicitly; never use latest. Local loopback/password configuration is not a production deployment profile.
