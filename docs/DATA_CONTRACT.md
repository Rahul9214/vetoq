# Data contract

This document describes the Module 002 schema that is applied today. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md).

## Applied revisions

| Revision              | Contents                                                 |
| --------------------- | -------------------------------------------------------- |
| `0001_security_slice` | Eleven tables, ownership keys, and immutability triggers |
| `0002_worker_claim`   | `runs_claimable` and `reviews_unresolved_expiry`         |

Readiness requires `0002_worker_claim`. Do not rewrite an applied migration. The next schema change is a new revision. `0002_worker_claim` has no destructive downgrade.

## Tables

| Table           | Ownership                                                    |
| --------------- | ------------------------------------------------------------ |
| `workspaces`    | Tenant boundary. `active` and `policy_revision`              |
| `memberships`   | Principal role `operator` or `reviewer` in one workspace     |
| `runs`          | One Goal Lock (`envelope`), state, budgets, lease, and fence |
| `content_nodes` | Untrusted original or derived text for one run               |
| `content_edges` | Parent-to-child transformation, version, and lossiness       |
| `findings`      | Deterministic or model evidence span on one node             |
| `actions`       | One persisted proposal, digest, and optional verdict         |
| `reviews`       | One review row per action                                    |
| `tickets`       | At most one local ticket per run and per action              |
| `executions`    | At most one receipt per action, with optional `verified_at`  |
| `audit_events`  | Append-only sequence per run                                 |

Foreign keys keep content, findings, actions, reviews, tickets, and executions inside the run and workspace. A run references the membership that accepted it.

## Immutable fields

Database triggers reject changes to the Goal Lock envelope, principal, workspace, expiry, submission key, and submission digest. They reject changes to action proposal, digest, run, and workspace. Content node updates are rejected. Audit events cannot be updated, and they cannot be deleted before the retention window. These triggers are application-level durability. They are not a control against a database administrator.

The `runs.state` check constraint still lists `INSPECTING`. The workflow does not persist that value. Do not treat the constraint name as evidence that an inspection state exists.

## Goal Lock and digests

`runs.envelope` is the confirmed `GoalLock`: version, template `support-triage/1`, principal, workspace, source id and digest, goal text, `tickets.create` version 1, destination `local-ticket-store`, expiry, policy revision `support-triage/1`, and the write, proposal, and continuation budgets.

The action digest is SHA-256 over canonical JSON of version, run id, envelope, and proposal. The submission digest identifies the accepted input for idempotency.

## Idempotency, review, and audit

- One submission key per workspace and principal. The same key and digest returns the original run. A different digest conflicts.
- One execution per action and one ticket per run.
- A review is consumed in the same transaction that writes the ticket. A consumed or expired approval cannot authorize another write.
- Audit sequence is assigned per run as one greater than the current maximum. Clients read events with `sequence > after`.

## Provenance graph

Nodes store origin, supplier, digest, content, `trust = untrusted`, completeness, and expiry. Edges store the transform. Module 002 is a per-run text graph, not the later cross-run lineage product.

## Retention

The retention command deletes content nodes whose expiry has passed and audit events older than 30 days. The run-delete trigger also refuses deletion of a run newer than 24 hours. This is an operator command, not a background service.

## Migration policy

Never edit `0001_security_slice` or `0002_worker_claim` to clean history. Add a forward revision. Do not point Alembic at the development database when the intent is the test database.
