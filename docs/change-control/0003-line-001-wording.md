# Change record 0003 — LINE-001 wording

Status: approved as the M004 GREEN B definition. Applied at M004 GREEN B: the registry row is IMPLEMENTED for the approved sentence.

Human approval: GREEN A on 15 October 2026, for M004 Slice A, following the M004 P0 and P0A reviews. The accompanying architecture decision is [ADR 0004](../adr/0004-run-scoped-relational-lineage.md).

## Required contents

| Item              | Record                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rationale         | The registry meaning of LINE-001 is "per-run audit sequence and execution receipt." The approved M004 meaning is relational execution lineage from Goal Lock through proposal, guard evaluations, review, execution, and verification. That is a material reinterpretation of an existing capability id, so it requires this record. The old meaning is audit chronology. The new one is structural, with audit kept separate.         |
| Affected contract | [PRODUCT_CONTRACT.md](../PRODUCT_CONTRACT.md), capability registry row LINE-001, and its "Execution lineage" requirement bullet. The id is unchanged. [DATA_CONTRACT.md](../DATA_CONTRACT.md) and [ARCHITECTURE_CONTRACT.md](../ARCHITECTURE_CONTRACT.md) describe the planned structures without claiming them.                                                                                                                       |
| Security impact   | None on authority, tenancy, review semantics, or the Action Guard. The sentence states that lineage is never an authorization input. It adds an output record of guard evaluations and does not change a guard rule. A lineage write failure is fail-closed.                                                                                                                                                                           |
| Migration impact  | None in this record. The schema work is M004 Slices B and C (`0005_provenance_lineage`, then `0006_lineage_enforcement`). This record creates no revision and does not change `SCHEMA_REVISION`. Historical runs keep no structural lineage and are reported as not recorded. There is no backfill from audit.                                                                                                                         |
| Alternatives      | Doing nothing, which keeps an audit-only sentence after structural lineage exists. A new capability id, rejected because the id still means execution lineage. Marking the new sentence IMPLEMENTED in Slice A, rejected because no guard decision relation, review link, or execution link exists yet. Dropping the legacy and retention clause, rejected because it would overstate coverage for historical and post-retention runs. |
| Test impact       | GREEN B must show, on the disposable database and a populated upgrade rehearsal: an atomic guard decision per persisted evaluation, review links on both decisions, an execution link to the authorizing ALLOW decision, verified and unverified stages that can be told apart, lineage that the guard never reads, and truthful legacy and retention states. Those tests belong to slices B to G, not this record.                    |
| Human approval    | GREEN A, 15 October 2026, including the instruction that LINE-001 stays PARTIAL during implementation.                                                                                                                                                                                                                                                                                                                                 |
| ADR               | [ADR 0004](../adr/0004-run-scoped-relational-lineage.md). This record changes no invariant.                                                                                                                                                                                                                                                                                                                                            |

## Approved registry sentence

Use this sentence only when M004 GREEN B evidence exists, and set the status in the same edit:

> Run-scoped execution lineage preserving the ordered relationship from Goal Lock through proposal, deterministic guard evaluations, human review, execution, and verification, with explicit legacy and retention gaps. Lineage is evidence of what happened and is never an authorization input.

The status may become IMPLEMENTED at GREEN B only if the complete release evidence supports this exact bounded meaning. Otherwise the row stays PARTIAL.

The sentence does not claim cross-run lineage, external tool lineage, a tamper-proof archive, or lineage for runs that predate the M004 relations.

## What Slice A changed in the registry

Nothing. The row remains:

`LINE-001` — Per-run audit sequence and execution receipt — `PARTIAL`

The audit sequence and execution receipt are still implemented as described there. This record does not remove them.
