"""email_rfc822 version 1.

The original RFC822 string is the evidence root. Children are derived,
untrusted, and lossy. This adapter does not fetch URLs, write attachments,
or treat a header as an authenticated identity.

Header budget: the UTF-8 length of the original header section from the start
through the first ``\\r\\n\\r\\n`` or ``\\n\\n`` separator, whichever occurs
first, including that separator. If neither separator exists, the whole source
is the header section.

Part budget: every MIME entity below the top-level message counts as one part,
including multipart containers and leaves. The top-level message does not
count. ``message/*`` is not traversed as a container.

Defect policy: defects attached while parsing are fatal ``malformed_content``
except ``ObsoleteHeaderDefect``, ``NonPrintableDefect``,
``NonASCIILocalPartDefect``, and ``InvalidDateDefect``. Those four do not make
the MIME tree ambiguous. Any other defect, including an unknown defect class,
is fatal. A missing boundary or an unclosed boundary is fatal. There is no
best-effort partial message.

Transfer encodings: absent, ``7bit``, ``8bit``, ``quoted-printable``, and
``base64``. ``binary`` and any other token are ``unsupported_embedded_content``.
A duplicate encoding header is ``malformed_content``. ``base64`` or
``quoted-printable`` on a multipart container is ``malformed_content``.

A missing leaf ``Content-Type`` is ``text/plain`` because that is the RFC 2045
default, not because the body was sniffed. A missing charset is ``us-ascii``.
"""

import base64
import binascii
import quopri
from dataclasses import dataclass
from email import errors, policy
from email.message import Message
from email.parser import Parser

from vetoq.ingestion.contracts import (
    Canonicalization,
    DerivedRepresentation,
    RepresentationKind,
    TransformStep,
    require_derived_budget,
)
from vetoq.ingestion.errors import (
    IngestionError,
    ProcessingFailure,
    input_limit,
    malformed_content,
    unsupported_embedded_content,
    unsupported_media_type,
)
from vetoq.ingestion.html_inert import HtmlInert
from vetoq.ingestion.json_structured import JsonStructured
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.markdown import Markdown
from vetoq.ingestion.media_types import Charset, DeclaredFormat, MediaType, normalize_media_type
from vetoq.ingestion.source_text import AcceptedSource, validate_source_text
from vetoq.ingestion.text_plain import TextPlain

_PARSER_ID = "email_rfc822"
_PARSER_VERSION = "1"
_POLICY = policy.default.clone(raise_on_defect=False)
_LEAF_CTE = frozenset({"7bit", "8bit", "quoted-printable", "base64"})
_CONTAINER_CTE = frozenset({"7bit", "8bit"})
_HEADER_NAMES = frozenset(
    {"from", "to", "cc", "bcc", "reply-to", "subject", "message-id", "content-type"}
)
_LEAF_MEDIA = {
    "text/plain": MediaType.TEXT_PLAIN,
    "text/html": MediaType.HTML,
    "text/markdown": MediaType.MARKDOWN,
    "application/json": MediaType.JSON,
}
_CHARSETS = {"utf-8": Charset.UTF_8, "us-ascii": Charset.US_ASCII}
_HTML_TRANSFORMS = {
    "html-visible-text": "email-part-html-visible",
    "html-active-content": "email-part-html-active",
}
_TOLERABLE_DEFECTS: tuple[type[errors.MessageDefect], ...] = (
    errors.ObsoleteHeaderDefect,
    errors.NonPrintableDefect,
    errors.NonASCIILocalPartDefect,
    errors.InvalidDateDefect,
)
_EMPTY_OK = frozenset({MediaType.TEXT_PLAIN, MediaType.MARKDOWN, MediaType.HTML})


@dataclass(frozen=True, slots=True)
class _Decoded:
    media_type: MediaType
    charset: Charset
    text: str


@dataclass(frozen=True, slots=True)
class _Inspected:
    headers: str | None
    leaves: tuple[_Decoded, ...]


class EmailRfc822:
    """Strict RFC822/MIME text. One unsupported leaf rejects the message."""

    media_type = MediaType.RFC822
    parser_id = _PARSER_ID
    parser_version = _PARSER_VERSION

    def validate(self, source: str, declaration: DeclaredFormat) -> str:
        if declaration.media_type is not MediaType.RFC822:
            raise unsupported_media_type()
        exact = validate_source_text(source, declaration.charset)
        if exact.startswith("\ufeff"):
            raise malformed_content()
        if len(_header_section(exact).encode("utf-8")) > BUDGETS.email_header_bytes:
            raise input_limit(422)
        require_derived_budget(_render(_inspect(exact)), pre_accept=True)
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
        exact = self.validate(source, declaration)
        return Canonicalization(derived=_bounded_derived(_render(_inspect(exact))))


def _render(inspected: _Inspected) -> list[DerivedRepresentation]:
    parts: list[DerivedRepresentation] = []
    if inspected.headers is not None:
        parts.append(
            _email_part(
                kind=RepresentationKind.CANONICAL_TEXT,
                content=inspected.headers,
                parser_id=_PARSER_ID,
                parser_version=_PARSER_VERSION,
                transform="email-headers",
                steps=(TransformStep("email-headers", "1"),),
            )
        )
    for leaf in inspected.leaves:
        parts.extend(_parts_for(leaf))
    return parts


def _email_part(
    *,
    kind: RepresentationKind,
    content: str,
    parser_id: str,
    parser_version: str,
    transform: str,
    steps: tuple[TransformStep, ...],
) -> DerivedRepresentation:
    return DerivedRepresentation(
        kind=kind,
        content=content,
        parser_id=parser_id,
        parser_version=parser_version,
        transform=transform,
        transform_version="1",
        lossy=True,
        transform_steps=steps,
    )


def _lineage(child: DerivedRepresentation) -> tuple[TransformStep, ...]:
    """MIME decode, then the child adapter's own ordered steps."""

    tail = child.transform_steps
    if not tail:
        tail = (TransformStep(child.transform, child.transform_version),)
    return (TransformStep("email-part-decode", "1"),) + tail


def _header_section(source: str) -> str:
    """Header block through the separator, as defined in the module docstring."""

    crlf = source.find("\r\n\r\n")
    lf = source.find("\n\n")
    if crlf < 0 and lf < 0:
        return source
    if crlf < 0 or (lf >= 0 and lf < crlf):
        return source[: lf + 2]
    return source[: crlf + 4]


def _header_evidence(section: str) -> str | None:
    if section.endswith("\r\n\r\n"):
        block = section[:-4]
    elif section.endswith("\n\n"):
        block = section[:-2]
    else:
        block = section
    logical: list[str] = []
    for line in block.splitlines():
        if line[:1] in " \t" and logical:
            logical[-1] = f"{logical[-1]}{line}"
        else:
            logical.append(line)
    chosen: list[str] = []
    for line in logical:
        colon = line.find(":")
        if colon <= 0:
            continue
        name = line[:colon].strip().lower()
        if name in _HEADER_NAMES:
            chosen.append(f"{name}:{line[colon + 1 :]}")
    if not chosen:
        return None
    return "\n".join(chosen)


def _inspect(source: str) -> _Inspected:
    message = _parse(source)
    leaves: list[_Decoded] = []
    _reject_defects(message)
    container = message.get_content_maintype() == "multipart"
    if container:
        _transfer_encoding(message, container=True)
        _walk(message, leaves)
    else:
        _keep_leaf(message, leaves)
    return _Inspected(_header_evidence(_header_section(source)), tuple(leaves))


def _parse(source: str) -> Message:
    try:
        return Parser(policy=_POLICY).parsestr(source)
    except RecursionError:
        raise input_limit(422) from None
    except Exception:
        raise malformed_content() from None


def _walk(root: Message, leaves: list[_Decoded]) -> None:
    found = 0
    frames: list[tuple[list[Message], int]] = [(_multipart_children(root), 0)]
    while frames:
        group, index = frames[-1]
        if index >= len(group):
            frames.pop()
            continue
        frames[-1] = (group, index + 1)
        part = group[index]
        _reject_defects(part)
        found += 1
        if found > BUDGETS.email_mime_parts:
            raise input_limit(422)
        if part.get_content_maintype() == "multipart":
            _transfer_encoding(part, container=True)
            frames.append((_multipart_children(part), 0))
        else:
            _keep_leaf(part, leaves)


def _multipart_children(message: Message) -> list[Message]:
    if message.get_content_maintype() != "multipart":
        return []
    payload = message.get_payload()
    if not isinstance(payload, list):
        raise malformed_content()
    children: list[Message] = []
    for item in payload:
        if not isinstance(item, Message):
            raise malformed_content()
        children.append(item)
    return children


def _reject_defects(message: Message) -> None:
    for defect in message.defects:
        if not isinstance(defect, _TOLERABLE_DEFECTS):
            raise malformed_content()


def _transfer_encoding(message: Message, *, container: bool) -> str | None:
    raw_values = message.get_all("content-transfer-encoding")
    if not raw_values:
        return None
    if len(raw_values) != 1:
        raise malformed_content()
    token = str(raw_values[0]).strip().lower()
    allowed = _CONTAINER_CTE if container else _LEAF_CTE
    if token in allowed:
        return token
    if container and token in _LEAF_CTE:
        raise malformed_content()
    raise unsupported_embedded_content()


def _keep_leaf(message: Message, leaves: list[_Decoded]) -> None:
    media = _LEAF_MEDIA.get(message.get_content_type().lower())
    if media is None:
        raise unsupported_embedded_content()
    charset_name, charset = _leaf_charset(message)
    encoding = _transfer_encoding(message, container=False)
    raw = message.get_payload(decode=False)
    if not isinstance(raw, str):
        raise malformed_content()
    text = _decode_text(raw, encoding, charset_name)
    if _child_accepts(media, charset, text):
        leaves.append(_Decoded(media, charset, text))


def _leaf_charset(message: Message) -> tuple[str, Charset]:
    raw = message.get_param("charset")
    if raw is None:
        return "us-ascii", Charset.US_ASCII
    if not isinstance(raw, str):
        raise unsupported_embedded_content()
    name = raw.strip().lower()
    charset = _CHARSETS.get(name)
    if charset is None:
        raise unsupported_embedded_content()
    return name, charset


def _decode_text(raw: str, encoding: str | None, charset_name: str) -> str:
    if encoding in {None, "7bit", "8bit"}:
        if encoding == "7bit" and _non_ascii(raw):
            raise malformed_content()
        if charset_name == "us-ascii" and _non_ascii(raw):
            raise malformed_content()
        return raw
    try:
        transport = raw.encode("ascii")
    except UnicodeEncodeError:
        raise malformed_content() from None
    if encoding == "base64":
        payload = _strict_base64(transport)
    else:
        payload = _strict_quoted_printable(transport)
    try:
        return payload.decode(charset_name)
    except UnicodeDecodeError:
        raise malformed_content() from None


def _non_ascii(value: str) -> bool:
    return any(ord(character) > 127 for character in value)


def _strict_base64(transport: bytes) -> bytes:
    filtered = bytes(byte for byte in transport if byte not in b" \t\r\n")
    try:
        return base64.b64decode(filtered, validate=True)
    except binascii.Error:
        raise malformed_content() from None


def _strict_quoted_printable(transport: bytes) -> bytes:
    _reject_malformed_quoted_printable(transport)
    try:
        return quopri.decodestring(transport)
    except (binascii.Error, ValueError):
        raise malformed_content() from None


def _reject_malformed_quoted_printable(transport: bytes) -> None:
    """Reject a bad escape. Ordinary characters and long lines stay legal.

    A hex escape is `=` plus two hexadecimal digits. A soft line break is
    `=` followed by `\\n` or `\\r\\n`. Any other `=` is malformed.
    """

    hex_digits = b"0123456789abcdefABCDEF"
    index = 0
    length = len(transport)
    while index < length:
        if transport[index] != ord("="):
            index += 1
            continue
        remaining = length - index - 1
        if remaining >= 2 and transport[index + 1 : index + 3] == b"\r\n":
            index += 3
            continue
        if remaining >= 1 and transport[index + 1] == ord("\n"):
            index += 2
            continue
        if (
            remaining >= 2
            and transport[index + 1] in hex_digits
            and transport[index + 2] in hex_digits
        ):
            index += 3
            continue
        raise malformed_content()


def _child_accepts(media: MediaType, charset: Charset, text: str) -> bool:
    declaration = DeclaredFormat(media, charset)
    try:
        _adapter(media).validate(text, declaration)
    except IngestionError as error:
        if error.code == "empty_input" and media in _EMPTY_OK:
            return False
        raise
    return True


def _adapter(media: MediaType) -> TextPlain | Markdown | JsonStructured | HtmlInert:
    if media is MediaType.TEXT_PLAIN:
        return TextPlain()
    if media is MediaType.MARKDOWN:
        return Markdown()
    if media is MediaType.JSON:
        return JsonStructured()
    return HtmlInert()


def _parts_for(leaf: _Decoded) -> tuple[DerivedRepresentation, ...]:
    declaration = DeclaredFormat(leaf.media_type, leaf.charset)
    if leaf.media_type is MediaType.TEXT_PLAIN:
        return _text_part(TextPlain(), leaf.text, declaration, "email-part-text")
    if leaf.media_type is MediaType.MARKDOWN:
        return _text_part(Markdown(), leaf.text, declaration, "email-part-markdown")
    if leaf.media_type is MediaType.JSON:
        result = JsonStructured().canonicalize(leaf.text, declaration)
        if len(result.derived) != 1:
            raise ProcessingFailure("canonicalization_failure")
        child = result.derived[0]
        return (
            DerivedRepresentation(
                kind=child.kind,
                content=child.content,
                parser_id=child.parser_id,
                parser_version=child.parser_version,
                transform="email-part-json",
                transform_version="1",
                lossy=True,
                transform_steps=_lineage(child),
            ),
        )
    result = HtmlInert().canonicalize(leaf.text, declaration)
    parts: list[DerivedRepresentation] = []
    for child in result.derived:
        transform = _HTML_TRANSFORMS.get(child.transform)
        if transform is None:
            raise ProcessingFailure("canonicalization_failure")
        parts.append(
            DerivedRepresentation(
                kind=child.kind,
                content=child.content,
                parser_id=child.parser_id,
                parser_version=child.parser_version,
                transform=transform,
                transform_version="1",
                lossy=True,
                transform_steps=_lineage(child),
            )
        )
    return tuple(parts)


def _text_part(
    adapter: TextPlain | Markdown,
    text: str,
    declaration: DeclaredFormat,
    transform: str,
) -> tuple[DerivedRepresentation, ...]:
    try:
        exact = adapter.validate(text, declaration)
    except IngestionError as error:
        if error.code == "empty_input":
            return ()
        raise
    return (
        DerivedRepresentation(
            kind=RepresentationKind.CANONICAL_TEXT,
            content=exact,
            parser_id=adapter.parser_id,
            parser_version=adapter.parser_version,
            transform=transform,
            transform_version="1",
            lossy=True,
            transform_steps=(
                TransformStep("email-part-decode", "1"),
                TransformStep(transform, "1"),
            ),
        ),
    )


def _bounded_derived(parts: list[DerivedRepresentation]) -> tuple[DerivedRepresentation, ...]:
    """Canonicalization backstop. Pre-accept refusal uses `input_limit`."""

    return require_derived_budget(parts, pre_accept=False)
