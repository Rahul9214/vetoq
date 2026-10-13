# Observability and SLO

Production observability is not implemented as a platform. The registry row OBS-001 is PARTIAL. Do not publish a numerical production SLA from this document.

## What exists

- API and BFF errors include a correlation id.
- Request logs omit tokens, SQL parameters, and source text.
- Worker logs include the run id and a stable reason code.
- `/health/live` and `/health/ready` report process and schema readiness.
- Audit events record security decisions for a run.

## Intended signals

These are direction. No collector, dashboard, or alert route exists.

| Signal                | Intent                                                                 |
| --------------------- | ---------------------------------------------------------------------- |
| Structured logs       | One JSON event per failure, with correlation id and reason code        |
| Correlation           | The same id across BFF, API, and worker                                |
| Metrics               | Counters and timings without source content                            |
| Traces                | Spans for submit, inference, guard, and write. Not a trace backend yet |
| Security events       | Guard verdicts, review denial, and authority failures                  |
| Worker health         | Heartbeat, lease age, and quarantined runs                             |
| Provider health       | Timeout, invalid output, and retry counts                              |
| Execution latency     | Time from ALLOW to verified read-back                                  |
| Review latency        | Time from REVIEW to decision or expiry                                 |
| Error rate            | Failed and blocked runs, separated from attacks                        |
| Queue age             | Oldest claimable run                                                   |
| Verification failures | Receipt missing or read-back mismatch                                  |

## Preliminary SLO categories

No production baseline has been measured. Categories, not numbers:

- **Availability of the control plane.** Ready API and a reachable database at the required revision.
- **Integrity of execution.** No unverified success, no duplicate local ticket, no stale-fence write.
- **Timeliness of automation.** Bounded provider retries and a visible run state. Human review is excluded from the automation window.
- **Timeliness of review.** An undecided review expires instead of lingering as authority.
- **Diagnostic access.** An operator can correlate a user-visible failure without reading secrets.

Measured targets in older design notes remain targets. They are not this SLO.
