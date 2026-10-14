# Change record 0001 — INGEST-001 wording

Status: approved as the GREEN B definition. The registry row is not changed in Slice A.

Human approval: GREEN A on 13 October 2026. The accompanying architecture decision is [ADR 0003](../adr/0003-declared-format-ingestion.md).

## Required contents

| Item              | Record                                                                                                                                                                                                                                                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rationale         | The current sentence, "Secure ingestion of confirmed pasted text," describes the Module 002 paste path. M003's truthful capability is adapter-governed ingestion for an explicit allowlist, with every other declared type failing closed. Leaving the old sentence in place at GREEN B would hide that boundary. Changing it earlier would describe adapters the runtime does not yet run.       |
| Affected contract | [PRODUCT_CONTRACT.md](../PRODUCT_CONTRACT.md), capability registry row INGEST-001. The id is unchanged.                                                                                                                                                                                                                                                                                           |
| Security impact   | None on authority, tenancy, review, or the Action Guard. The future sentence forbids reading IMPLEMENTED as universal media coverage or as malware scanning. Trust stays `untrusted`.                                                                                                                                                                                                             |
| Migration impact  | None in this record. No schema, audit, or in-flight run changes here. This record specified `0003_secure_ingestion` and did not create it. Slice B later created that revision as nullable storage only.                                                                                                                                                                                          |
| Alternatives      | Doing nothing, which keeps a paste-only sentence after five adapters exist. A new capability id, rejected because the id still means secure ingestion of confirmed content. Marking the broader sentence IMPLEMENTED in Slice A, rejected because the adapters are not in the runtime.                                                                                                            |
| Test impact       | GREEN B must show, on the disposable database, accept paths for all five types, a 422 with zero rows for an unsupported declaration and for an unsupported embedded leaf, distinct idempotency digests for the same source under two declared types, and no ALLOW on incomplete post-accept evidence. Those tests are slices B–K, not this record. Amendment A1 does not change the registry row. |
| Human approval    | GREEN A, 13 October 2026, including the instruction that INGEST-001 stays PARTIAL until GREEN B.                                                                                                                                                                                                                                                                                                  |
| ADR               | [ADR 0003](../adr/0003-declared-format-ingestion.md). This record does not change an invariant. The provenance clarification in SECURITY_INVARIANTS.md restates the existing trust rule for ingestion.                                                                                                                                                                                            |

## Approved registry sentence

Use this sentence only when GREEN B evidence exists, and set the status to IMPLEMENTED in the same edit:

> Secure adapter-governed ingestion for explicitly supported declared formats, with unsupported formats failing closed.

Do not add a claim that all media types are supported. MULTI-001 stays PLANNED. PROV-001, THREAT-001, UX-001, A11Y-001, OBS-001, and SEC-001 stay PARTIAL unless a later record changes them.

## What Slice A changed in the registry

Nothing. Through Slice J the row remained:

`INGEST-001` — Secure ingestion of confirmed pasted text — `PARTIAL`

## GREEN B closeout

On 15 October 2026 the disposable-database security suite, the five-format live route, and `pnpm verify` passed. The registry row is now the approved sentence above, with status IMPLEMENTED. The evidence is recorded in [handoff.md](../handoff.md). This closeout does not change the sentence.
