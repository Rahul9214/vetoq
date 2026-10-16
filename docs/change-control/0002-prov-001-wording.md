# Change record 0002 — PROV-001 wording

Status: approved as the M004 GREEN B definition. Applied at M004 GREEN B: the registry row is IMPLEMENTED for the approved sentence.

Human approval: GREEN A on 15 October 2026, for M004 Slice A, following the M004 P0 and P0A reviews. The accompanying architecture decision is [ADR 0004](../adr/0004-run-scoped-relational-lineage.md).

## Required contents

| Item              | Record                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rationale         | The current sentence, "Provenance-linked untrusted text, including bounded derived nodes," describes the Module 002 text graph. M003 added ordered transform history and ingestion metadata. M004 adds proposal evidence references and explicit gaps. Leaving the old sentence at M004 GREEN B would understate what is proved, and widening it earlier would describe relations the runtime does not yet persist. |
| Affected contract | [PRODUCT_CONTRACT.md](../PRODUCT_CONTRACT.md), capability registry row PROV-001. The id is unchanged.                                                                                                                                                                                                                                                                                                               |
| Security impact   | None on authority, tenancy, review, or the Action Guard. The sentence limits the claim to one run and names its gaps. It does not claim cross-run provenance, a retained content graph, or detection quality. Trust stays `untrusted`.                                                                                                                                                                              |
| Migration impact  | None in this record. The schema work is M004 Slices B and C. This record creates no revision and does not change `SCHEMA_REVISION`.                                                                                                                                                                                                                                                                                 |
| Alternatives      | Doing nothing. A new capability id, rejected because the id still means provenance of untrusted content. Marking the new sentence IMPLEMENTED in Slice A, rejected because none of the evidence relations exists yet. A cross-run wording, rejected because M004 is run-scoped.                                                                                                                                     |
| Test impact       | GREEN B must show, on the disposable database and a populated upgrade rehearsal: immutable original and derived relationships, ordered steps, findings on evidence, proposal evidence ids validated within the same workspace and run, legacy rows reported as not recorded, and retention states that never fabricate a deleted graph. Those tests belong to slices B to G, not this record.                       |
| Human approval    | GREEN A, 15 October 2026, including the instruction that PROV-001 stays PARTIAL during implementation.                                                                                                                                                                                                                                                                                                              |
| ADR               | [ADR 0004](../adr/0004-run-scoped-relational-lineage.md). This record changes no invariant.                                                                                                                                                                                                                                                                                                                         |

## Approved registry sentence

Use this sentence only when M004 GREEN B evidence exists, and set the status in the same edit:

> Run-scoped evidence provenance preserving immutable original/derived relationships, ordered transform history, evidence findings, proposal evidence references, and explicit legacy/retention gaps.

The status may become IMPLEMENTED at GREEN B only if the complete release evidence supports this exact bounded meaning. Otherwise the row stays PARTIAL.

The sentence does not claim cross-run provenance, a retained content graph after retention, or a security clearance of content.

## What Slice A changed in the registry

Nothing. The row remains:

`PROV-001` — Provenance-linked untrusted text, including bounded derived nodes — `PARTIAL`
