# Security invariants

These rules govern every current and future module. The authority invariant is not replaceable by weaker wording. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md). A material change to this file follows [CHANGE_CONTROL.md](CHANGE_CONTROL.md).

## Authority

Authority is externally granted, explicitly scoped and continuously verifiable.

Agents may autonomously exercise delegated authority, but cannot create, expand or waive it.

Model judgments may inform security decisions but cannot independently enlarge execution authority.

Consequences:

- Model output cannot create authority.
- Workspace membership does not equal Goal Lock authority.
- Human review cannot expand Goal Lock authority.
- A hard prohibition cannot be reviewed into ALLOW.

## Identity

- A product request requires an authenticated principal.
- The API verifies the identity token. The browser does not authorize.
- An active workspace membership is required for workspace data.
- An email address, display name, or client-supplied header is not authority.
- The authorized party claim must not be treated as the issuer.

## Goal Lock

- The envelope is immutable after the run is accepted. Amending authority creates a new run.
- The envelope scopes principal, workspace, tool, tool version, destination, policy revision, expiry, and the write budget.
- The action digest binds the run, envelope, and canonical proposal.
- Expiry is enforced before execution. A database trigger rejects changes to the envelope, principal, workspace, expiry, and submission identity.

## Provenance

- A consequential proposal must reference persisted evidence.
- Derived content keeps a parent edge. Transformation does not upgrade trust.
- Unknown, incomplete, or unmapped evidence never enlarges authority.
- Module 002 stores original pasted text and bounded derived text as `untrusted`. It does not store private chain-of-thought.

## Action Guard

- The guard is deterministic and provider-independent.
- It is the final enforcement boundary before a write.
- Unknown, invalid, expired, mutated, or incomplete state is never ALLOW.
- Current membership, workspace, policy revision, cancellation, and expiry are loaded before execution.
- The implemented hard reasons include identity or membership failure, revocation or cancellation, invalid state, a tool outside the grant, workspace mismatch, stale policy, expiry, exhausted limits, incomplete evidence, digest mismatch, and an existing execution.

## Review

- The decision is bound to one exact action.
- The approval expires.
- The approval is single-use.
- The caller must present the action digest.
- The originator cannot approve. Separation of duties requires a different active reviewer.
- Reviewer membership and role are revalidated at decision time and again before the write.
- Hard prohibitions are not overridable.
- Module 002 proves this with the production review and guard code on the disposable test database. A second live browser principal was not part of that proof.

## Execution

- Submission and execution are idempotent for the local ticket path.
- The ticket, receipt, and success event commit together. The ticket is read back before the run is completed.
- A committed local ticket is reconciled after restart instead of written again.
- A stale worker fence cannot insert an action after a newer claim.
- Cancellation and revocation are checked before the write. Cancellation does not undo a committed ticket.
- One bounded continuation may follow a hard scope or tool mismatch. It does not add privileges.

## Tenancy

- A principal reads and mutates only workspaces where membership is active.
- Missing membership and missing objects both surface as not found where the route is non-enumerating.
- Self-review is the deliberate exception: the originator receives a forbidden response after the prohibition is audited.

## AI providers

- The model returns typed evidence and an optional typed proposal.
- The model cannot execute a tool or hold execution credentials.
- There is no provider fallback that enlarges authority.
- Malformed, incomplete, or unreferenced model output fails closed.

## Secrets

- The model does not receive database credentials, Clerk secrets, or tool credentials.
- Logs carry correlation identifiers, run identifiers, and stable reason codes. They do not carry tokens, source text, SQL parameter values, or provider secrets.
