"""Strict declared-media-type normalization.

The result selects an adapter. Body contents are not an input to this function,
so they cannot switch the adapter.
"""

from dataclasses import dataclass
from enum import StrEnum

from vetoq.ingestion.errors import IngestionError, malformed_content, unsupported_media_type
from vetoq.ingestion.limits import BUDGETS

_OWS = " \t"
_TCHAR = frozenset("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


class MediaType(StrEnum):
    TEXT_PLAIN = "text/plain"
    JSON = "application/json"
    MARKDOWN = "text/markdown"
    HTML = "text/html"
    RFC822 = "message/rfc822"


class Charset(StrEnum):
    UTF_8 = "utf-8"
    US_ASCII = "us-ascii"


@dataclass(frozen=True, slots=True)
class DeclaredFormat:
    """Normalized declaration. `media_type` has no parameters."""

    media_type: MediaType
    charset: Charset | None


def normalize_media_type(value: str) -> DeclaredFormat:
    """Return the lowercase type and an optional charset, or fail closed."""
    if not isinstance(value, str) or "\x00" in value:
        raise malformed_content()
    try:
        if len(value.encode("utf-8")) > BUDGETS.source_bytes:
            raise malformed_content()
    except UnicodeEncodeError:
        raise malformed_content() from None
    index = _skip_ows(value, 0)
    type_name, index = _token(value, index)
    if index >= len(value) or value[index] != "/":
        raise malformed_content()
    subtype, index = _token(value, index + 1)
    charset_value: str | None = None
    seen_charset = False
    while True:
        index = _skip_ows(value, index)
        if index == len(value):
            break
        if value[index] != ";":
            raise malformed_content()
        index = _skip_ows(value, index + 1)
        if index == len(value):
            raise malformed_content()
        name, index = _token(value, index)
        if index >= len(value) or value[index] != "=":
            raise malformed_content()
        index += 1
        if index >= len(value):
            raise malformed_content()
        if value[index] == '"':
            parameter, index = _quoted(value, index)
        else:
            parameter, index = _token(value, index)
        if name.lower() != "charset":
            raise malformed_content()
        if seen_charset:
            raise malformed_content()
        seen_charset = True
        charset_value = parameter.lower()
    charset: Charset | None = None
    if charset_value is not None:
        try:
            charset = Charset(charset_value)
        except ValueError:
            raise malformed_content() from None
    try:
        media_type = MediaType(f"{type_name}/{subtype}".lower())
    except ValueError:
        raise unsupported_media_type() from None
    return DeclaredFormat(media_type, charset)


def _skip_ows(value: str, index: int) -> int:
    while index < len(value) and value[index] in _OWS:
        index += 1
    return index


def _token(value: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(value) and value[index] in _TCHAR:
        index += 1
    if index == start:
        raise malformed_content()
    return value[start:index], index


def _quoted(value: str, index: int) -> tuple[str, int]:
    if index >= len(value) or value[index] != '"':
        raise malformed_content()
    index += 1
    characters: list[str] = []
    while index < len(value):
        character = value[index]
        if character == "\\":
            index += 1
            if index >= len(value):
                raise malformed_content()
            characters.append(value[index])
        elif character == '"':
            return "".join(characters), index + 1
        elif character in "\r\n":
            raise malformed_content()
        else:
            characters.append(character)
        index += 1
    raise malformed_content()


def stored_media_type(declaration: DeclaredFormat) -> str:
    """The column value: lowercase type, parameters removed."""
    stored = declaration.media_type.value
    if ";" in stored or stored != stored.lower():
        raise IngestionError("invalid_input", 422)
    return stored
