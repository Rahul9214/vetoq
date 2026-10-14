"""json_structured version 1.

Depth is the number of objects and arrays open at once. A scalar root has
depth 0. A member is one object key/value pair or one array element, summed
over the whole document. A scalar root adds no member.

The standard library parses JSON values. The scan below only counts depth so
a deeply nested document cannot escape as a recursion failure.
"""

import json
import math
from collections.abc import Mapping, Sequence
from typing import NoReturn

from vetoq.ingestion.contracts import (
    Canonicalization,
    DerivedRepresentation,
    RepresentationKind,
    TransformStep,
)
from vetoq.ingestion.errors import (
    ProcessingFailure,
    input_limit,
    malformed_content,
    unsupported_media_type,
)
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import DeclaredFormat, MediaType, normalize_media_type
from vetoq.ingestion.source_text import AcceptedSource, validate_source_text

_OPEN = "{["
_CLOSE = "}]"


class JsonStructured:
    """Strict JSON. The original string stays the Goal Lock text."""

    media_type = MediaType.JSON
    parser_id = "json_structured"
    parser_version = "1"

    def validate(self, source: str, declaration: DeclaredFormat) -> str:
        if declaration.media_type is not MediaType.JSON:
            raise unsupported_media_type()
        exact = validate_source_text(source, declaration.charset)
        encoded = _canonical_json(_parse(exact))
        if (
            len(encoded.encode("utf-8")) > BUDGETS.derived_text_bytes
            or 1 > BUDGETS.derived_representations_per_run
        ):
            raise input_limit(422)
        return exact

    def accept(self, source: str, declared: str) -> AcceptedSource:
        declaration = normalize_media_type(declared)
        exact = self.validate(source, declaration)
        return AcceptedSource(
            source=exact,
            declaration=declaration,
            byte_size=len(exact.encode("utf-8")),
        )

    def canonicalize(self, source: str, declaration: DeclaredFormat) -> Canonicalization:
        value = _parse(self.validate(source, declaration))
        content = _bounded_canonical(_canonical_json(value))
        if 1 > BUDGETS.derived_representations_per_run:
            raise ProcessingFailure("parser_limit_exceeded")
        return Canonicalization(
            derived=(
                DerivedRepresentation(
                    kind=RepresentationKind.CANONICAL_TEXT,
                    content=content,
                    parser_id=self.parser_id,
                    parser_version=self.parser_version,
                    transform="json-canonical",
                    transform_version="1",
                    lossy=True,
                    transform_steps=(TransformStep("json-canonical", "1"),),
                ),
            )
        )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _bounded_canonical(content: str) -> str:
    """Return the whole canonical string, or refuse it. Never a prefix."""
    if len(content.encode("utf-8")) > BUDGETS.derived_text_bytes:
        raise ProcessingFailure("parser_limit_exceeded")
    return content


def _parse(source: str) -> object:
    if source.startswith("\ufeff"):
        raise malformed_content()
    _reject_deep_nesting(source)
    try:
        value = json.loads(
            source,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_nonfinite_token,
        )
    except json.JSONDecodeError:
        raise malformed_content() from None
    except RecursionError:
        raise input_limit(422) from None
    except ValueError:
        raise input_limit(422) from None
    if _contains_nonfinite(value):
        raise malformed_content()
    if _member_count(value) > BUDGETS.json_members:
        raise input_limit(422)
    return value


def _reject_deep_nesting(source: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in source:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in _OPEN:
            depth += 1
            if depth > BUDGETS.json_nesting_depth:
                raise input_limit(422)
        elif character in _CLOSE and depth:
            depth -= 1


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise malformed_content()
        value[key] = item
    return value


def _reject_nonfinite_token(_token: str) -> NoReturn:
    raise malformed_content()


def _contains_nonfinite(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, str):
        return any(_contains_nonfinite(item) for item in value)
    return False


def _member_count(value: object) -> int:
    if isinstance(value, Mapping):
        total = len(value)
        for item in value.values():
            total += _member_count(item)
            if total > BUDGETS.json_members:
                return total
        return total
    if isinstance(value, Sequence) and not isinstance(value, str):
        total = len(value)
        for item in value:
            total += _member_count(item)
            if total > BUDGETS.json_members:
                return total
        return total
    return 0
