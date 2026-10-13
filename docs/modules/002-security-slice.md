# Module 002 — First real security vertical slice

**Current module specification.** Product, security, architecture, data, and API authority are the contracts in `docs/`. This specification does not override them.

**IMPLEMENTED. AWAITING HUMAN REVIEW AND MANUAL GIT WORKFLOW.**

## Goal and boundaries

An authenticated operator reviews pasted support-email text. A real model proposes no action or one scoped ticket. VETOQ inspects evidence, enforces confirmed authority, allows one legitimate real ticket, rejects an unauthorized proposal, and persists a complete audit. Text is the first slice only; later approved modules expand toward heterogeneous D3 coverage.

## Locked implementation choices

Groq supplies contextual analysis through the provider-neutral interface, initially using `openai/gpt-oss-120b`. Clerk supplies identity; workspace membership remains local and server-authoritative. The reference action is a real PostgreSQL-backed `tickets.create`. Inputs are synthetic or sanitized text. Protected content expires after 24 hours and minimized audit metadata after 30 days through the operator retention command.

## Implementation contract

- Verified identity and workspace membership; all product objects enforce workspace access.
- Support-triage template with user-confirmed scope; immutable Goal Lock and source bindings.
- Inert text with original/derived provenance. Proposed bounds: 4KiB goal, 64KiB source, 128KiB total transformed content, decode depth two.
- Deterministic inspection plus structured contextual model investigation. No model-based final authorization.
- Typed business proposal with exact canonical arguments and evidence references.
- Pure policy and Action Guard; model SDK types cannot enter authorization.
- Closed ticket tool, real persisted target record, guarded private dispatcher.
- Digest-bound human review with expiry; hard prohibitions remain non-overridable.
- Persisted bounded state machine and durable runner; one continuation without scope expansion.
- Transactional local ticket/receipt/audit; idempotent submission and execution.
- Responsive run list/detail/review/ticket views, safe empty/error/unknown states.
- Labeled adversarial evaluation, isolated from operational records/metrics.

## APIs and records

Implemented endpoints are `me`, run creation/list/read/events/content/cancel, exact review decision, and ticket read. There is no public generic tool executor. The initial Alembic migration creates exactly the eleven approved relational tables and database triggers for immutable authority, proposals, protected content, and append-only audit.

## Acceptance gates

A real provider call must produce valid analysis or explicit failure. An authorized model proposal must persist a ticket; read it back. A wrong-workspace proposal to the SAME implemented ticket tool must be blocked before any write. Reject secret retrieval and external exfiltration by deterministic authority. Test changed arguments, replay, expired approval, unknown tool/fields, cancellation, revoked membership, policy failure, database failure, timeout, duplicate execution, and restart.

A live model may resist an attack upstream. Label that honestly; do not fabricate a denied proposal. A final-gate live demonstration requires an actually observed model proposal and persisted veto. Controlled evaluation proposals separately establish deterministic enforcement.

All nine attack families need cases, and benign task utility must be measured. No effect when analysis is incomplete. No duplicate ticket on retries. All required widths, keyboard focus, and accessibility checks pass. No unresolved critical/high security defects. Update handoff and measured results.

The final implementation evidence and exact limitations are in [002-verification.md](002-verification.md). The real allowed flow persisted and verified one ticket. The controlled same-tool wrong-workspace flow persisted `BLOCK` with zero ticket writes. A live adversarial model call resisted the injected target upstream, so it is evidence of model behavior and is not claimed as a live final-gate veto.

## Later scope

PDF/DOCX, HTML/web retrieval, OCR/image text, other source channels, dedicated classifiers, external integrations, and richer orchestration require subsequent approval and evidence. Do not silently present this text slice as D3.
