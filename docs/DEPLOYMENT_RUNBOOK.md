# Deployment runbook

Module 002 runs locally. This is not a cloud or Kubernetes deployment. DEPLOY-001 is PLANNED.

## Local services

Required for a signed-in run:

- PostgreSQL from Compose, loopback only, persistent volume
- API at `127.0.0.1:18000`
- Worker process from the same codebase
- Web at `localhost:3000`
- Clerk development instance
- Groq credential for live analysis

The web process must use `--hostname localhost`. Binding it to `127.0.0.1` makes Clerk's middleware rewrite look external, and Next.js proxies the request to itself.

## Database order

1. Start PostgreSQL with `pnpm db:up`.
2. Apply migrations with `pnpm db:migrate` so the target database reaches `0002_worker_claim`.
3. Create `vetoq_test` separately when integration tests are required, migrate that database explicitly, then point `VETOQ_TEST_DATABASE_URL` at it.
4. Provision a workspace membership for the Clerk subject. Do not invent a second reviewer unless a human asks for one.

Development and test databases stay distinct. Production, when it exists, is a third database. Tests never fall back to development.

## Configuration checks

The API refuses product traffic when the database URL is missing. Readiness is 503 until PostgreSQL answers and the schema revision matches. Production configuration, already enforced by settings when `environment` is production, requires an explicit host list, a non-placeholder database password, and `sslmode=verify-full`. Those checks do not deploy TLS or a host.

Clerk keys stay in untracked env files. The Groq key stays server-side. The model never receives it as a tool credential.

## Startup and shutdown

Start API, worker, and web in separate terminals. `pnpm worker:once` is a single step, not the long-running process. SIGINT or SIGTERM asks the worker to finish the in-flight tick and stop claiming. A committed ticket is reconciled on the next claim. It is not written twice.

`pnpm retention:run` is manual. It deletes expired content nodes and audit events older than 30 days.

## Rollback and recovery

- Schema rollback is not automatic. `0002_worker_claim` refuses downgrade. Restore a backup or add a forward migration.
- Application rollback must keep the code compatible with the applied revision.
- Local Compose data lives in a named volume. Do not delete the volume to fix a configuration mistake.
- A failed run is quarantined with a reason. It is not retried forever.
- There is no multi-region backup, no managed failover, and no production incident channel.

## Secrets

Do not commit `.env` or `.env.local`. Do not print database URLs or keys in logs, docs, or tests. Placeholders belong in `.env.example` only.
