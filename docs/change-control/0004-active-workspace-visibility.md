# Change record 0004 — Active-workspace read visibility

Status: approved as a tenancy clarification. No code changes in Slice A. **Implemented in M004 Slice D** for `get_run`, `get_events`, `get_content`, and `get_ticket`, through `vetoq/visibility.py`. The internal lineage service uses the same helper. **Slice E** exposed three GET lineage routes that use that same helper. `decide_review` and `cancel` remain outside this record.

Human approval: GREEN A on 15 October 2026, for M004 Slice A, following the M004 P0 and P0A reviews (decisions H10 and R7). The accompanying architecture decision is [ADR 0004](../adr/0004-run-scoped-relational-lineage.md).

## Required contents

| Item              | Record                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rationale         | The current routes disagree. `/me`, `list_runs`, run submission, and the Action Guard check that the workspace is active. `get_run`, `get_events`, `get_content`, and `get_ticket` check only the principal's membership. A run of an inactive workspace is therefore hidden from the list but readable by id. No contract or test makes that intended. M004 lineage must not become a second, more permissive access path.                    |
| Affected contract | [SECURITY_INVARIANTS.md](../SECURITY_INVARIANTS.md), Tenancy. [API_CONTRACT.md](../API_CONTRACT.md), status semantics for `404 not_found`.                                                                                                                                                                                                                                                                                                     |
| Security impact   | Narrows reads only. A read now also requires an active workspace. It does not widen any read, change a mutation, or weaken tenant isolation. The 404 stays non-enumerating, so an inactive workspace, an inactive membership, a foreign workspace, and a missing object look the same. Mutation semantics are unchanged (see below).                                                                                                           |
| Migration impact  | None. This is a query change. No schema, audit, or in-flight run is affected. Existing clients of an inactive workspace lose read access by id, which matches the list behavior.                                                                                                                                                                                                                                                               |
| Alternatives      | Doing nothing, which leaves lineage able to expose an inactive workspace more than the run list. Gating only lineage, rejected because run detail and lineage would then disagree. Also changing `decide_review` and `cancel`, rejected for M004 because it changes review semantics and needs its own change control.                                                                                                                         |
| Test impact       | The implementing slices must show, on the disposable database, a 404 for run detail, events, content, ticket read, and every lineage route when the workspace is inactive; a 200 for an active workspace with an active membership; an identical 404 for an inactive membership, a foreign workspace, a foreign run, and a guessed sub-resource id; unchanged `list_runs`; and that lineage routes use the single canonical visibility helper. |
| Human approval    | GREEN A, 15 October 2026.                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ADR               | [ADR 0004](../adr/0004-run-scoped-relational-lineage.md). This record clarifies Tenancy. It does not change authority, Goal Lock, Action Guard rules, or review semantics.                                                                                                                                                                                                                                                                     |

## Approved read visibility rule

A principal may read a run, or anything scoped to that run, only when all of these hold:

- the principal has an active membership in the run's workspace;
- that workspace is active; and
- the workspace and run match the requested resource.

Otherwise the response is `404 not_found`, non-enumerating.

This applies, when implemented, to run detail, events, content, ticket read, and every lineage read.

## Canonical helper

The implementation uses one canonical server-side run visibility helper. A lineage route must not build a second independent authorization lookup. The visible run supplies the trusted `workspace_id` and `run_id` for every later query. Client identifiers are selectors and never authorization.

## Not changed: mutation routes

`decide_review` and `cancel` are **not** changed by M004. They keep their current checks. This record does not claim those paths are hardened for an inactive workspace.

They are recorded as a separate later hardening consideration, which needs its own change record because it touches review semantics.

## What Slice A changed

Nothing in code. The Tenancy clarification and its status are recorded in the contracts and the Module 004 specification.

## What Slice D changed

The four read routes now call one helper that requires an active membership and an active workspace, and every later query in those routes is qualified by the trusted run's workspace and run id. A ticket is read through its run, with no membership-only path. Tests cover a 200 for an active member, and an identical 404 for a foreign principal, an inactive membership, an inactive workspace, a missing object, and a node of another run. `list_runs`, `/me`, `decide_review`, and `cancel` are unchanged.

## What Slice E changed

The three GET lineage routes use the same helper and the same non-enumerating 404. They add no mutation, no client-controlled workspace authority, and no change to `decide_review` or `cancel`.
