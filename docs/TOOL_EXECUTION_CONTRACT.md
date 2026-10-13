# Tool execution contract

Every side effect crosses this boundary. Module 002 implements one tool. Capability status lives only in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md).

## Proposal

A proposal names a tool, a tool version, canonical arguments, and one or more persisted evidence identifiers. Unknown fields are rejected. The model does not supply the destination, the policy revision, or the principal.

## Current tool

| Field       | Value                     |
| ----------- | ------------------------- |
| Tool        | `tickets.create`          |
| Version     | 1                         |
| Destination | `local-ticket-store`      |
| Arguments   | workspace id, title, body |
| Side effect | one PostgreSQL ticket     |

The workspace argument must equal the Goal Lock workspace. Title length is 1 to 160 characters. Body length is 1 to 8000 characters. The write budget is one successful ticket.

## Digest and guard

The action digest commits the run, the Goal Lock, and the canonical proposal. The Action Guard reloads current authority and returns only:

- **ALLOW** — dispatch this exact action
- **REVIEW** — wait for a matching approval
- **BLOCK** — do not write

## Review binding

An uncertain proposal is REVIEW until a different active reviewer approves the same digest. The approval expires, is stored once, and is consumed when the write commits. Rejection blocks the run. A mismatched digest, a consumed approval, an inactive reviewer, or an expired approval cannot ALLOW.

## Receipt, verification, and recovery

ALLOW inserts the ticket and the execution receipt in the same transaction, then reads the ticket back. `verified_at` is set only after that read. A later worker that finds the receipt reconciles instead of inserting another ticket.

Retryable provider failures stay in `PROPOSING` under a bounded lease. They are not tool retries. A non-idempotent write is not repeated. Cancellation and revocation are checked before the write. A stale fence cannot commit an action for an older worker.

## Future tools

A new tool needs a versioned schema, a destination, canonical arguments, the same digest, the same guard, and its own receipt and reconciliation rules. An external side effect whose outcome is unknown is not success. Bypassing this boundary means the tool is outside VETOQ's protection.
