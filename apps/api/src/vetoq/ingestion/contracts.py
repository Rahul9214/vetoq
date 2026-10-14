"""Typed ingestion values. These types do not grant authority."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from vetoq.ingestion.errors import ProcessingFailure, input_limit
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import DeclaredFormat, MediaType


class RepresentationKind(StrEnum):
    ORIGINAL = "original"
    CANONICAL_TEXT = "canonical_text"
    DECODED_TEXT = "decoded_text"
    ACTIVE_CONTENT = "active_content"


@dataclass(frozen=True, slots=True)
class TransformStep:
    """One ordered interpretation step.

    This is not a database id. The edge summary is a separate field.
    `recorded_transform_steps` returns None when the stored count is null.
    """

    transform: str
    version: str

    def __post_init__(self) -> None:
        if not self.transform or not self.version:
            raise ValueError("transform step requires a transform and version")
        if len(self.transform) > 80 or len(self.version) > 80:
            raise ValueError("transform step is bounded")


@dataclass(frozen=True, slots=True)
class DerivedRepresentation:
    """Untrusted child text. An original row is a separate value, not this type.

    `transform`, `transform_version`, and `lossy` are the later edge fields.
    `transform_steps` is the ordered lineage. An empty chain means the single
    edge transform is the only step. This object is not a database row.
    """

    kind: RepresentationKind
    content: str
    parser_id: str
    parser_version: str
    transform: str
    transform_version: str
    lossy: bool
    transform_steps: tuple[TransformStep, ...] = ()

    def __post_init__(self) -> None:
        if self.kind is RepresentationKind.ORIGINAL:
            raise ValueError("original is not a derived representation")
        if not self.parser_id or not self.parser_version:
            raise ValueError("derived representation requires a parser pair")
        if not self.transform or not self.transform_version:
            raise ValueError("derived representation requires a transform")
        if any(not isinstance(step, TransformStep) for step in self.transform_steps):
            raise ValueError("transform steps must be typed")


def recorded_transform_steps(
    transform_step_count: int | None,
    steps: Sequence[TransformStep],
) -> tuple[TransformStep, ...] | None:
    """Return the recorded chain, or None when provenance was not recorded.

    The edge summary is not an argument. A null count stays null. This does
    not invent a step from `content_edges.transform`.
    """

    if transform_step_count is None:
        return None
    if transform_step_count != len(steps) or any(
        not isinstance(step, TransformStep) for step in steps
    ):
        raise ValueError("recorded transform steps are incomplete")
    return tuple(steps)


@dataclass(frozen=True, slots=True)
class Canonicalization:
    """Successful canonicalization.

    `derived` may be empty. Emptiness is not failure. Failure is an exception.
    Do not use the truth of `derived` as the success signal.
    """

    derived: tuple[DerivedRepresentation, ...] = ()
    succeeded: Literal[True] = True

    def __bool__(self) -> bool:
        return True


def require_derived_budget(
    parts: Sequence[DerivedRepresentation],
    *,
    pre_accept: bool,
) -> tuple[DerivedRepresentation, ...]:
    """Return every derived child, or refuse the set. Never a shorter prefix.

    The original source is not included in `parts`. A budget that this check
    can see before acceptance is `input_limit`. Canonicalization passes
    `pre_accept=False` and raises `parser_limit_exceeded` as a backstop.
    """

    total = 0
    over_bytes = False
    for part in parts:
        total += len(part.content.encode("utf-8"))
        if total > BUDGETS.derived_text_bytes:
            over_bytes = True
            break
    over_count = len(parts) > BUDGETS.derived_representations_per_run
    if over_count or over_bytes:
        if pre_accept:
            raise input_limit(422)
        raise ProcessingFailure("parser_limit_exceeded")
    return tuple(parts)


class IngestionAdapter(Protocol):
    """Format adapter.

    `validate` is the pure pre-accept pass and returns the exact source.
    `canonicalize` returns a `Canonicalization`, including one with no children.
    Neither method receives a database, Goal Lock, Action Guard, model client,
    tool credential, or network client.
    """

    media_type: MediaType
    parser_id: str
    parser_version: str

    def validate(self, source: str, declaration: DeclaredFormat) -> str:
        """Return the exact source, or raise a pre-accept error."""
        ...

    def canonicalize(self, source: str, declaration: DeclaredFormat) -> Canonicalization:
        """Return derived text under the original. This result is not trust."""
        ...
