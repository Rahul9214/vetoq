# Security contracts — Module 002 elaboration

Canonical invariants are [SECURITY_INVARIANTS.md](SECURITY_INVARIANTS.md). This file records how the text slice implements them. It does not grant a weaker authority rule. Later formats and external tools require new approved contracts and evidence.

## Goal Lock

Use a versioned support-triage template. Minimal envelope: schema_version, template, user goal text, verified principal/workspace, source IDs, grants (tool, operation, resource scope, destination, data classes), limits, review mode, expiry, and policy revision. The user confirms displayed scope; the server intersects it with real permissions. AI may help interpretation but cannot mint grants.

User-derived: goal and template/scope choice. System-derived: identity, allowed permissions, limits, time, source bindings, policy version. Grants/snapshot are immutable after confirmation. Counters, findings, revocation, and workflow state change separately. Amending authority creates a new run. Proposed defaults: 30-minute lifetime, one successful ticket, three proposals, one safe continuation, review on material uncertainty. No arbitrary numerical risk ceiling initially.

## Provenance

A content node contains origin kind/identifier, supplier, timestamp, media type, digest, protected content/reference, trust label, processing completeness, and extractor/version. Directed edges record transformation, parameters, lossiness, and parent/child. Evidence spans identify an exact representation and offsets; later formats may include page/DOM/OCR bounds. Preserve originals and bounded decoded children. If offset mapping is approximate, label it.

Observed influence labels are presented_to_model, cited_by_model, and used_in_argument when mapped. Do not assert causal model reasoning. Transforming content never upgrades its authority. Do not store private chain-of-thought.

## Model provider boundary

The provider interface accepts versioned structured inference requests and returns validated structured output plus invocation metadata. The Groq adapter handles the OpenAI-compatible wire format, strict JSON Schema output, timeouts, rate limits, transport failures, invalid output, and evidence-reference validation. Shared domain errors do not expose provider transport types to policy, Goal Lock, or Action Guard. There is no silent fallback.

## Action Guard

Required inputs: verified principal/workspace; active envelope; registered tool/schema; canonical arguments; server-derived resources/destination; content evidence; policy references/current restrictions; counters; action-bound review; execution/idempotency state. The action digest binds run, principal, envelope, tool/version, arguments, destination/resource, and policy revision.

Decision order: validate identity/state/schema → apply hard prohibitions and scope → expiry/budgets/data rules → review requirement → exact review validation → private guarded execution.

- ALLOW: the exact persisted action may execute through the dispatcher.
- REVIEW: persist that exact action until a different authorized reviewer approves or rejects it.
- BLOCK: reject and record reason codes. A reviewer cannot turn a hard prohibition into ALLOW.

Unknown tool/field, invalid approval, unavailable policy, or changed arguments cannot authorize execution. Model recommendations are stored separately from deterministic reasons. Review cannot override a hard prohibition. Approval is digest-bound, expiring, one-time, and subject to current membership and policy at dispatch.

## Execution and audit

The reference tickets.create adapter persists a real record. Same-tool wrong-workspace tests prove non-vacuous enforcement. Unique submission/execution/ticket keys prevent duplicate writes. For a local ticket, final recheck, ticket, receipt, and success event commit atomically. Read back after commit. External side effects later need receipts and reconciliation; do not claim exactly-once external execution.

Events record actor, run, sequence, type, timestamps, references, versions, and safe reasons. Audit is append-only to application roles during retention, not claimed administrator-proof. Proposed retention: protected source/derived content 24 hours; minimized metadata 30 days. Review expiry, revocation, and cancellation are auditable. Never log secrets, tokens, raw payloads, unrestricted provider output, or chain-of-thought.

## API errors

The implemented error contract is [API_CONTRACT.md](API_CONTRACT.md). Expired content is 410. An expired or mismatched review is 409 `review_stale`. There is no generic public execute_tool endpoint.
