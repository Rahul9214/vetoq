"""The one M003 v1 security-budget source.

Adapters and later slices read `BUDGETS`. These values are not environment
settings and they are not caller configuration. The Module 002 worker lease is
not a field here.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class IngestionBudgets:
    goal_bytes: int
    source_bytes: int
    derived_text_bytes: int
    derivation_depth: int
    base64_matches_per_representation: int
    json_nesting_depth: int
    json_members: int
    html_start_tags: int
    html_attributes: int
    # Derived children only. The one original source is not part of this count.
    derived_representations_per_run: int
    # Ordered interpretation steps on one edge. Not a representation count.
    transform_steps_per_edge: int
    email_header_bytes: int
    email_mime_parts: int
    proposal_evidence_ids: int
    bff_body_bytes: int
    accepted_runs_per_workspace_per_hour: int
    originals_per_run: int
    network_fetches: int
    archive_decompression: int


BUDGETS: Final[IngestionBudgets] = IngestionBudgets(
    goal_bytes=4_096,
    source_bytes=65_536,
    derived_text_bytes=131_072,
    derivation_depth=2,
    base64_matches_per_representation=16,
    json_nesting_depth=32,
    json_members=2_048,
    html_start_tags=2_000,
    html_attributes=8_000,
    derived_representations_per_run=32,
    transform_steps_per_edge=4,
    email_header_bytes=16_384,
    email_mime_parts=32,
    proposal_evidence_ids=16,
    bff_body_bytes=512 * 1_024,
    accepted_runs_per_workspace_per_hour=30,
    originals_per_run=1,
    network_fetches=0,
    archive_decompression=0,
)
