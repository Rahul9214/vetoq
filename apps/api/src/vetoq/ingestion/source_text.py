"""Generic source checks shared by later adapters.

The returned text is the caller's original string. These checks do not fold,
strip, or delete characters.
"""

from dataclasses import dataclass
from typing import Final

from vetoq.ingestion.errors import empty_input, input_limit, malformed_content
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import Charset, DeclaredFormat, normalize_media_type


def _character_set(ranges: tuple[tuple[int, int], ...], singles: tuple[int, ...]) -> frozenset[str]:
    found = {chr(code) for start, end in ranges for code in range(start, end)}
    found.update(chr(code) for code in singles)
    return frozenset(found)


# Preserved inspection evidence from the Module 003 threat rules. NUL is absent
# because a NUL is rejected rather than stored.
PRESERVED_CONTROL_CHARACTERS: Final[frozenset[str]] = _character_set(
    (
        (0x0001, 0x0009),
        (0x000E, 0x0020),
        (0x200B, 0x2010),
        (0x202A, 0x202F),
        (0x2060, 0x2065),
        (0x2066, 0x206A),
    ),
    (0x000B, 0x000C, 0x007F, 0x00AD, 0x2028, 0x2029, 0xFEFF),
)


@dataclass(frozen=True, slots=True)
class AcceptedSource:
    """Generic pre-accept success. Not a Goal Lock and not a completed parse."""

    source: str
    declaration: DeclaredFormat
    byte_size: int


def validate_goal_text(goal: str) -> str:
    return _validate(goal, limit=BUDGETS.goal_bytes, charset=None)


def validate_source_text(source: str, charset: Charset | None = None) -> str:
    return _validate(source, limit=BUDGETS.source_bytes, charset=charset)


def prepare_source(source: str, declared: str) -> AcceptedSource:
    """Normalize the declaration and check the source without selecting a parser."""
    declaration = normalize_media_type(declared)
    exact = validate_source_text(source, declaration.charset)
    return AcceptedSource(
        source=exact,
        declaration=declaration,
        byte_size=len(exact.encode("utf-8")),
    )


def preserved_control_characters(source: str) -> tuple[str, ...]:
    """Return preserved control characters in order. The source is not modified."""
    return tuple(character for character in source if character in PRESERVED_CONTROL_CHARACTERS)


def _validate(value: str, *, limit: int, charset: Charset | None) -> str:
    if not isinstance(value, str):
        raise malformed_content()
    size = 0
    visible = False
    ascii_only = True
    for character in value:
        if character == "\x00":
            raise malformed_content()
        code = ord(character)
        if code > 127:
            ascii_only = False
        if not character.isspace():
            visible = True
        try:
            size += len(character.encode("utf-8"))
        except UnicodeEncodeError:
            raise malformed_content() from None
        if size > limit:
            raise input_limit(413)
    if not visible:
        raise empty_input()
    if charset is Charset.US_ASCII and not ascii_only:
        raise malformed_content()
    return value
