"""Source digest and the staged submission identity.

`source_digest` hashes the validated Python string as UTF-8. It does not hash
HTTP JSON bytes, the media type, parser metadata, or a canonical child.

Parser version is not part of this identity, `source_digest`, or the Goal Lock.
It names the implementation that produced a derived interpretation. An accepted
run is not reprocessed because a newer parser version is deployed. Historical
evidence stays immutable. Reprocessing under a newer version has to be an
explicit future replay and has to write new immutable evidence.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from vetoq.contracts import digest
from vetoq.ingestion.media_types import MediaType
from vetoq.inspection import content_digest


def source_digest(source: str) -> str:
    """SHA-256 of the UTF-8 encoding of the validated source string."""
    return content_digest(source)


@dataclass(frozen=True, slots=True)
class SubmissionIdentity:
    """Canonical idempotency identity for one declared submission.

    The live `POST /runs` digest still hashes the Module 002 body, including
    `sanitized`. `accept_declared_submission` uses this object. Parser version,
    charset spelling, and derived text are not fields.
    """

    workspace_id: UUID
    template: Literal["support-triage/1"]
    goal: str
    source: str
    confirmed: Literal[True]
    declared_media_type: MediaType


def submission_digest(identity: SubmissionIdentity) -> str:
    """Canonical digest of the staged client object, media type included."""
    return digest(
        {
            "workspace_id": str(identity.workspace_id),
            "template": identity.template,
            "goal": identity.goal,
            "source": identity.source,
            "confirmed": identity.confirmed,
            "declared_media_type": identity.declared_media_type.value,
        }
    )
