# Threat model — planned product

Module 001 provides a shell and health endpoints only; it does not mitigate prompt injection. This model governs subsequent approved implementation.

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
