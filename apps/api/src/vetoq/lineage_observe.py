"""Bounded lineage-read telemetry on the existing stdlib logger.

There is no metrics abstraction, collector, or dashboard. One success event per completed
HTTP lineage read, at INFO, using the same `vetoq.api` logger as the rest of the API.
A 404 is a visibility miss, not a read failure, and is not logged: logging the selector
would distinguish existence. Unexpected failures stay with the global exception handler
so this module never duplicates a traceback or a raw database message.

Allowed fields follow [SECURITY_INVARIANTS.md](SECURITY_INVARIANTS.md): correlation id,
run id of an already-authorized run, and stable codes. Forbidden: bodies, ticket text,
finding explanations, proposal or Goal Lock free text, producer response ids, SQL,
exception strings, workspace names, and principal identifiers.
"""

import logging
from collections.abc import Sequence

from vetoq.lineage_model import IntegrityFinding, RunLineage

logger = logging.getLogger("vetoq.api")

_MAX_CODES = 16


def _codes(findings: Sequence[IntegrityFinding]) -> str:
    ordered: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.code in seen:
            continue
        seen.add(finding.code)
        ordered.append(finding.code)
        if len(ordered) >= _MAX_CODES:
            break
    return ",".join(ordered) or "-"


def read_completed(
    *,
    correlation_id: str,
    kind: str,
    run_id: str,
    duration_ms: int,
    lineage: RunLineage,
) -> None:
    observed = lineage.bounds.observed
    logger.info(
        "lineage_read_completed correlation_id=%s kind=%s run_id=%s duration_ms=%s "
        "node_count=%s edge_count=%s finding_count=%s action_count=%s "
        "decision_count=%s max_depth=%s truncated=%s truncated_sets=%s "
        "anomaly_count=%s anomaly_codes=%s",
        correlation_id,
        kind,
        run_id,
        duration_ms,
        observed.nodes,
        observed.edges,
        observed.findings,
        observed.actions,
        observed.decisions,
        observed.max_depth,
        lineage.bounds.truncated,
        ",".join(lineage.bounds.truncated_sets) or "-",
        len(lineage.integrity),
        _codes(lineage.integrity),
    )
