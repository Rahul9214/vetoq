# Threat model

Canonical controls are [SECURITY_INVARIANTS.md](SECURITY_INVARIANTS.md). This file is the threat narrative for the text slice. Module 002 implements these controls: verified Clerk identity, server-authoritative membership, immutable Goal Lock, untrusted provenance, bounded decoding, strict model output, deterministic Action Guard, digest-bound review, private dispatch, transactional tickets/receipts/audit, and read-back verification. These controls apply only to the mediated local ticket tool and do not establish multimodal, external-integration, or F3/D3 reliability claims.

## Assets and adversaries

Assets: user authority, tool credentials, sensitive content, business records, approvals, isolation, audit integrity, and inference budget. Adversaries may control external content, model-visible tool responses, direct low-privilege requests, or attempts to tamper with action/review requests. Models may hallucinate or follow injected instructions. The trusted computing base includes policy code, dispatcher, identity validation, deployment configuration, and database administration.

| Boundary             | Threat                                         | Planned control                                                             |
| -------------------- | ---------------------------------------------- | --------------------------------------------------------------------------- |
| Browser/API          | Forged identity, CSRF, tampering               | Verified identity, workspace checks, request validation, protected sessions |
| Identity/application | Forged forwarded claims                        | Private origin, verified gateway, remove caller-supplied identity headers   |
| Goal/envelope        | Model grants itself authority                  | Confirmed typed template intersected with principal permissions             |
| Content/extraction   | Injection, parser exploit, decompression abuse | Inert processing, bounded work, isolated parsers when introduced            |
| Content/model        | Text impersonates authority                    | Structural separation and untrusted provenance; no prompt-only guarantee    |
| Application/provider | Sensitive-data disclosure                      | Approved provider, minimized data, explicit retention                       |
| Model/application    | Forged approvals or malformed calls            | Strict schemas; model output is evidence only                               |
| Proposal/guard       | Tool or scope escalation                       | Exact canonical arguments, registered operations, hard constraints          |
| Review/dispatch      | Replay or argument substitution                | Exact digest, authorized reviewer, expiry, one-time use                     |
| Guard/tool           | Bypass, stale authorization, duplicates        | Private dispatch, final recheck, transaction and idempotency                |
| Tool/workflow        | False success or poisoned output               | Read-back verification, output re-ingress                                   |
| Workspace/workspace  | Object-level access bypass                     | Membership and workspace-scoped relationships                               |
| Evidence/UI/log      | XSS and secret leakage                         | Inert text, access control, redaction, short retention                      |
| Dependencies/runtime | Supply-chain compromise                        | Pinned locks, review, minimum dependencies                                  |

## Attack-family coverage plan

Instruction Override and Role Change: preserve authority hierarchy, inspect impersonation, enforce immutable grants. Secret Extraction and Credential Theft: no agent credential access, narrow data scope, restricted sinks. Tool Abuse: tool-specific validation and quotas. Context Poisoning: source lineage, isolated runs, no automatic trust upgrade. Multi-Step Jailbreaks: cumulative evidence and bounded action attempts; reauthorize every step. Encoded Instructions: bounded decoding with preserved originals. Indirect Prompt Injection: inspect external channels and enforce at the final side-effect boundary.

These are layered mechanisms, not nine regex rules. Detection and prevention must be measured separately. A content detector miss must not expand permissions.

## Constraints and residual risk

No arbitrary fetch, shell, SQL, filesystem, or browser tool in the first slice. Future fetchers must block internal/metadata addresses, validate DNS and every redirect, and constrain egress. External integrations bypassing the gateway are unprotected. Deterministic constraints cannot prove the correctness of arbitrary business semantics. Audit stored solely in PostgreSQL is not tamper-proof against a database administrator. Human review can be socially engineered and must show exact actions.

Never put real secrets in attack tests. Controlled evaluation fixtures are labeled, isolated, and excluded from runtime metrics. Use disposable target data for unprotected comparisons. No attack simulation is implemented in Module 001.

## M003 ingestion threats

This section is the approved threat addition for universal secure ingestion. The controls below are specified in [the Module 003 specification](modules/003-universal-secure-ingestion.md) and [ADR 0003](adr/0003-declared-format-ingestion.md). The five adapters are the live `POST /runs` path. A historical Module 002 row, whose ingestion metadata is null, still uses the pasted-text worker path. New requests cannot send `sanitized`.

| Threat                                                                 | Required control                                                                       | Not claimed                             |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------- |
| Declared type outside the allowlist                                    | 422 `unsupported_media_type`, no run, no Goal Lock, no model call, no inspection audit | A scanned or safe result                |
| Body does not match the declared adapter                               | 422 `malformed_content`, no silent reclassification                                    | Sniffing a "more likely" type           |
| MIME container with an unsupported leaf, charset, or transfer encoding | 422 `unsupported_embedded_content`, no run, no silent omission, no inspection audit    | Complete evidence                       |
| HTML script, remote URL, or entity                                     | Inert extraction only; URLs copied as text; no execution and no fetch                  | Sanitized HTML                          |
| JSON duplicate keys, `NaN`, `Infinity`                                 | Reject before accept                                                                   | Last-key-wins or canonical-only storage |
| NUL, invalid UTF-8, or normalization that would change the original    | Reject, or preserve the exact original when the character is legal                     | Stripping before the digest             |
| Unicode controls, bidi, and invisible characters                       | Preserve and record `Encoded Instructions` evidence                                    | A trust upgrade when they are absent    |
| Base64, depth, and size bombs                                          | Existing and specified caps; incomplete fails closed                                   | Unbounded decode                        |
| Decompression, archive, PDF, Office, image, or audio bombs             | No such adapter                                                                        | Malware detection                       |
| URL fetch and SSRF                                                     | No fetch in M003                                                                       | A fetcher with a blocklist              |
| Filename or path traversal                                             | No filesystem write                                                                    | An upload control                       |
| Parser resource exhaustion                                             | Count and byte budgets; no network inside a transaction                                | A wall-clock SLO                        |
| Client `sanitized` or `source_class`                                   | Live route rejects both as `invalid_input` and does not treat either as trust          | A server trust upgrade                  |
| Cross-workspace content read                                           | Existing membership scope                                                              | A new content catalog                   |

Structural validation is not malware scanning. A detector miss still must not expand authority. Declared media type does not grant authority. The 30 accepted runs per workspace per hour do not cover rejected requests, because a pre-accept 4xx creates no run. Body and parser budgets bound one attempt. Generic and distributed abuse-rate protection remains PARTIAL, and SEC-001 remains PARTIAL. M003 does not add a distributed rate limiter.
