# Data contract

This document describes the schema that is applied today. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md). Parser support has not started.

## Applied revisions

| Revision                | Contents                                                 |
| ----------------------- | -------------------------------------------------------- |
| `0001_security_slice`   | Eleven tables, ownership keys, and immutability triggers |
| `0002_worker_claim`     | `runs_claimable` and `reviews_unresolved_expiry`         |
| `0003_secure_ingestion` | Nullable content-node ingestion metadata                 |
| `0004_edge_steps`       | Ordered transform steps for one content edge             |

Readiness requires `0004_edge_steps`. Do not rewrite an applied migration. The next schema change is a new revision. `0002_worker_claim`, `0003_secure_ingestion`, and `0004_edge_steps` have no destructive downgrade.

## Tables

| Table                | Ownership                                                                      |
| -------------------- | ------------------------------------------------------------------------------ |
| `workspaces`         | Tenant boundary. `active` and `policy_revision`                                |
| `memberships`        | Principal role `operator` or `reviewer` in one workspace                       |
| `runs`               | One Goal Lock (`envelope`), state, budgets, lease, and fence                   |
| `content_nodes`      | Untrusted original or derived text for one run                                 |
| `content_edges`      | Parent-to-child summary transform, version, lossiness, and optional step count |
| `content_edge_steps` | Ordered transform and version for one recorded edge                            |
| `findings`           | Deterministic or model evidence span on one node                               |
| `actions`            | One persisted proposal, digest, and optional verdict                           |
| `reviews`            | One review row per action                                                      |
| `tickets`            | At most one local ticket per run and per action                                |
| `executions`         | At most one receipt per action, with optional `verified_at`                    |
| `audit_events`       | Append-only sequence per run                                                   |

Foreign keys keep content, findings, actions, reviews, tickets, and executions inside the run and workspace. A run references the membership that accepted it.

## Immutable fields

Database triggers reject changes to the Goal Lock envelope, principal, workspace, expiry, submission key, and submission digest. They reject changes to action proposal, digest, run, and workspace. Content node updates are rejected. Content edge updates are rejected. Transform-step updates are rejected. Audit events cannot be updated, and they cannot be deleted before the retention window. These triggers are application-level durability. They are not a control against a database administrator.

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

## Ingestion metadata

Normative ingestion rules are [the Module 003 specification](modules/003-universal-secure-ingestion.md). `0003_secure_ingestion` adds nullable `declared_media_type`, `representation_kind`, `parser_id`, `parser_version`, `charset`, and `byte_size` on `content_nodes`. NULL means the fact was not recorded. Historical rows are not backfilled. `validated_media_type` and `channel` are not columns. Non-null values are constrained to the allowlists in that migration. A derived representation kind requires a parser id and version together. The existing content trigger still rejects every update, so this metadata is immutable once written. The live `POST /runs` insert writes those columns on the original. A historical Module 002 row stays null and is not rewritten. The worker writes derived nodes, edges, and steps after it claims a staged original. A null `transform_step_count` is read as no step list.

`content` remains `text NOT NULL`. `trust` remains `untrusted`. `content_edges.transform` and `version` are the summary of the whole parent-to-child derivation. They are not defined as the last step. `transform_step_count` NULL means the ordered chain was not recorded. A value from 1 through 4 means exactly that many `content_edge_steps` rows, with contiguous indexes from 1. Historical edges stay NULL. They are not backfilled from the summary. The worker inserts the count and the actual steps for a new recorded derivation. It does not invent a step from the summary. A new Base64 edge records one `base64` / `1` step. A decoded node records `decoded_text` with parser `bounded-decoder` version `1`. Parser id and parser version stay on the child node and are independent of the step list. Reading a null count yields no step list. It does not yield an empty list and it does not infer steps from the summary. The Goal Lock envelope keeps one `source_id` and one `source_digest`. `source_digest` is SHA-256 of the UTF-8 encoding of the validated source string, not of the HTTP JSON bytes, and not of a derived representation. The normalized declared media type is not an envelope field and it is not authority. Parser version is not part of `source_digest` or the submission digest. An accepted run is not reprocessed when a parser version changes. No `bytea`, object store, or filesystem payload is added. Retention of nodes and audit events is unchanged. Deleting a node deletes its edges and those edges' steps. Steps have no retention timestamp. The one ingestion budget source includes `transform_steps_per_edge` = 4. The database checks repeat that bound.
