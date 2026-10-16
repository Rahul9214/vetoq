# Product contract

Canonical product authority for VETOQ. Later documents, ADRs, module specifications, and code do not override this file. If this contract and another contract above the implementation materially contradict each other, stop and report the contradiction. Do not choose silently.

## Source-of-truth hierarchy

1. `docs/PRODUCT_CONTRACT.md`
2. `docs/SECURITY_INVARIANTS.md`
3. `docs/ARCHITECTURE_CONTRACT.md`
4. `docs/DATA_CONTRACT.md`
5. `docs/API_CONTRACT.md`
6. `docs/AGENT_CONTRACT.md`
7. `docs/TOOL_EXECUTION_CONTRACT.md`
8. `docs/UI_UX_CONTRACT.md`
9. Accepted ADRs in `docs/adr/`
10. The current module specification in `docs/modules/`
11. `docs/ENGINEERING_CONTEXT.md`
12. The verified implementation and its tests

`docs/TEST_RELEASE_GATES.md`, `docs/OBSERVABILITY_SLO.md`, `docs/DEPLOYMENT_RUNBOOK.md`, and `docs/CHANGE_CONTROL.md` govern how changes are proven, observed, released, and approved. They do not outrank the eight contracts above. A change to authority, Goal Lock, Action Guard, tenancy, review, the execution boundary, a capability ID, or a security invariant follows [CHANGE_CONTROL.md](CHANGE_CONTROL.md).

## Identity

| Field    | Locked value                       |
| -------- | ---------------------------------- |
| Product  | VETOQ                              |
| Category | Agent Execution Security Platform  |
| Tagline  | Trust the Goal. Verify the Action. |

VETOQ governs what autonomous and semi-autonomous agents are allowed to do. It is not a prompt-injection firewall, a content filter, or a guarantee that untrusted text has been fully understood.

## Problem

Agents fail when untrusted content is treated as permission. A model can summarize, classify, and propose. Those outputs do not create, expand, or waive the authority to cause a side effect. The protected question is whether a specific action stays inside authority that was granted outside the model.

## Protected path

```text
Content → Context / Evidence → Agent Proposal → Action Guard → Side Effect → Verification → Execution Lineage / Audit
```

Module 002 implements that path for one text channel and one local tool. Later modules extend the path. They do not replace it.

## Decision outcomes

The only execution decisions are:

- **ALLOW** — the exact persisted action may pass the final guard and the private dispatcher.
- **REVIEW** — that same action waits for a different authorized reviewer.
- **BLOCK** — the action is refused and the reason is recorded. A reviewer cannot turn a hard prohibition into ALLOW.

`NO_ACTION` is a workflow outcome when no proposal is executed. It is not a fourth authority grant.

## Requirements

- **Verified execution.** An ALLOW is not success until the side effect is committed and read back. Module 002 does this for a local PostgreSQL ticket. External tools must reconcile; an unknown result is not success.
- **Provenance.** A consequential proposal references persisted evidence. Derived content stays linked to its parents. Incomplete or unknown evidence never enlarges authority.
- **Execution lineage.** Each run has an ordered audit trail and, when a write commits, an execution receipt bound to that action. M004 adds run-scoped relational execution lineage in PostgreSQL for the exact LINE-001 sentence in the registry. There is no lineage UI. Lineage is evidence of what happened and is never an authorization input.
- **Review.** Material uncertainty requires an exact-action decision by a different active reviewer. The approval is digest-bound, expiring, and single-use.
- **Policy.** The Action Guard enforces the current policy revision. The model does not select the policy outcome.
- **Identity and tenancy.** A server-verified principal and an active workspace membership are required. Membership is not Goal Lock authority. Enterprise organization hierarchy, SSO administration, and cross-workspace delegation are not implemented.

## Direction that is not implemented

These are product direction. None of them is a current runtime capability.

- **MCP, tools, and connectors.** Future tools cross the same Action Guard. MCP and enterprise connectors are later modules.
- **Shadow Guard.** Compare a decision without granting a second execution path.
- **Policy Replay.** Re-evaluate historical proposals under a named policy revision without rewriting history.
- **Evaluation Lab.** Measure detection, authorization, and utility on labeled corpora. Current fixtures are engineering regressions, not that lab.
- **Enterprise connectors.** Systems outside the local ticket store. They are unprotected until they are behind the dispatcher.

## Roadmap

M003, universal secure ingestion, is complete at GREEN B (15 October 2026) and is the stable runtime baseline. Its specification is [modules/003-universal-secure-ingestion.md](modules/003-universal-secure-ingestion.md).

M004, provenance graph and execution lineage, is complete at GREEN B. Its specification is [modules/004-provenance-lineage.md](modules/004-provenance-lineage.md). Schema readiness is `0007_lineage_execution_lookup`. Lineage is run-scoped relational data in PostgreSQL. It describes what happened and never grants authority. There is no lineage UI. Do not start M005, or a later module, without approval.

| Module | Name                                                       |
| ------ | ---------------------------------------------------------- |
| M002   | Production baseline stabilization                          |
| M003   | Universal secure ingestion                                 |
| M004   | Provenance graph and execution lineage                     |
| M005   | Multi-agent security intelligence                          |
| M006   | Agent registry and tool registry                           |
| M007   | Enterprise policy engine                                   |
| M008   | Human review and escalation                                |
| M009   | Verified execution and production connectors               |
| M010   | Shadow Guard and policy replay                             |
| M011   | Evaluation lab and continuous red teaming                  |
| M012   | MCP and enterprise integration platform                    |
| M013   | Enterprise security, observability, and operations         |
| M014   | Scale architecture and reliability engineering             |
| M015   | Production deployment, hardening, and general availability |

Historical hackathon dates and the organizer F/D definitions remain context in [product.md](product.md). They are not the current engineering schedule. F3 and D3 are targets, not achieved results.

## Capability registry

Status values are defined in [TEST_RELEASE_GATES.md](TEST_RELEASE_GATES.md). This table is the only capability registry. A capability is IMPLEMENTED only where the current tests and runtime support that row. IDs are stable. Removing, renaming, weakening, or materially reinterpreting an ID requires change control and an ADR.

| ID           | Capability                                                                                                                                                                                                                                                                                       | Status      |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------- |
| AUTH-001     | Server-authoritative authenticated principal                                                                                                                                                                                                                                                     | IMPLEMENTED |
| TENANT-001   | Active workspace membership and non-enumerating object isolation                                                                                                                                                                                                                                 | IMPLEMENTED |
| GOAL-001     | Immutable Goal Lock for one confirmed support-triage envelope                                                                                                                                                                                                                                    | IMPLEMENTED |
| PROV-001     | Run-scoped evidence provenance preserving immutable original/derived relationships, ordered transform history, evidence findings, proposal evidence references, and explicit legacy/retention gaps.                                                                                              | IMPLEMENTED |
| LINE-001     | Run-scoped execution lineage preserving the ordered relationship from Goal Lock through proposal, deterministic guard evaluations, human review, execution, and verification, with explicit legacy and retention gaps. Lineage is evidence of what happened and is never an authorization input. | IMPLEMENTED |
| INGEST-001   | Secure adapter-governed ingestion for explicitly supported declared formats, with unsupported formats failing closed.                                                                                                                                                                            | IMPLEMENTED |
| MULTI-001    | Heterogeneous multimodal input                                                                                                                                                                                                                                                                   | PLANNED     |
| THREAT-001   | Nine-family threat evidence from deterministic inspection plus one model stage                                                                                                                                                                                                                   | PARTIAL     |
| INTENT-001   | Intent-alignment specialist                                                                                                                                                                                                                                                                      | PLANNED     |
| RISK-001     | Action-risk specialist                                                                                                                                                                                                                                                                           | PLANNED     |
| VERIFY-001   | Adversarial-verification specialist                                                                                                                                                                                                                                                              | PLANNED     |
| AGENT-001    | One provider-neutral analysis stage that cannot execute or grant authority                                                                                                                                                                                                                       | IMPLEMENTED |
| TOOL-001     | Closed tool identity, version, and destination                                                                                                                                                                                                                                                   | PARTIAL     |
| POLICY-001   | Versioned policy revision checked before execution                                                                                                                                                                                                                                               | PARTIAL     |
| GUARD-001    | Deterministic final Action Guard                                                                                                                                                                                                                                                                 | IMPLEMENTED |
| REVIEW-001   | Exact-action review, expiry, single use, and separation of duties                                                                                                                                                                                                                                | IMPLEMENTED |
| EXEC-001     | Idempotent local `tickets.create` with read-back                                                                                                                                                                                                                                                 | IMPLEMENTED |
| RECOVER-001  | Worker fencing, bounded provider retry, and per-run failure isolation                                                                                                                                                                                                                            | IMPLEMENTED |
| SHADOW-001   | Shadow Guard                                                                                                                                                                                                                                                                                     | PLANNED     |
| REPLAY-001   | Policy Replay                                                                                                                                                                                                                                                                                    | PLANNED     |
| EVAL-001     | Evaluation lab and operational efficacy metrics                                                                                                                                                                                                                                                  | PLANNED     |
| ATTACK-001   | Demonstrated detection reliability across the nine official families                                                                                                                                                                                                                             | PLANNED     |
| MCP-001      | MCP integration                                                                                                                                                                                                                                                                                  | PLANNED     |
| CONNECT-001  | Enterprise connectors outside the local ticket store                                                                                                                                                                                                                                             | PLANNED     |
| AUDIT-001    | Append-only audit for the application retention window                                                                                                                                                                                                                                           | IMPLEMENTED |
| INCIDENT-001 | Incident-response operations                                                                                                                                                                                                                                                                     | PLANNED     |
| OBS-001      | Production metrics, traces, and SLO reporting                                                                                                                                                                                                                                                    | PARTIAL     |
| SEC-001      | Production security program beyond the implemented slice controls                                                                                                                                                                                                                                | PARTIAL     |
| PERF-001     | Measured performance against a production baseline                                                                                                                                                                                                                                               | PLANNED     |
| UX-001       | Truthful product UI on the canonical visual foundation                                                                                                                                                                                                                                           | PARTIAL     |
| A11Y-001     | Release accessibility across required viewports and assistive technology                                                                                                                                                                                                                         | PARTIAL     |
| DEPLOY-001   | Production deployment and general availability                                                                                                                                                                                                                                                   | PLANNED     |

EVAL-001 stays PLANNED. The 27 attack fixtures and 20 benign controls are labeled engineering regressions. They do not establish the evaluation lab or an efficacy metric. ATTACK-001 stays PLANNED because family coverage in fixtures and detectors is not demonstrated detection reliability.

INGEST-001 is IMPLEMENTED for the approved sentence in [change-control/0001-ingest-001-wording.md](change-control/0001-ingest-001-wording.md). The live declarations are `text/plain`, `application/json`, `text/markdown`, `text/html`, and `message/rfc822`. Unsupported declarations fail closed. MULTI-001 stays PLANNED. The five text formats are not multimodal input. SEC-001, UX-001, and A11Y-001 stay PARTIAL.

PROV-001 and LINE-001 are IMPLEMENTED at M004 GREEN B for the exact sentences in [change record 0002](change-control/0002-prov-001-wording.md) and [change record 0003](change-control/0003-line-001-wording.md). The sentences do not claim cross-run lineage, a retained content graph after retention, a lineage UI, or that lineage grants authority. OBS-001 and SEC-001 stay PARTIAL.

## What VETOQ is not

VETOQ is not a prompt-injection firewall, a chatbot, a SIEM, a DLP suite, an operating-system sandbox, or a proof of arbitrary natural-language intent. It does not protect tools that bypass the Action Guard. It does not claim F3, D3, universal detection, exactly-once external side effects, malware scanning, or a public deployment. An unsupported media type is not inspected content.
