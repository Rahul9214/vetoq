"""html_inert version 1.

Submitted HTML is untrusted evidence. This adapter does not execute it, render
it, fetch URLs, or describe it as sanitized. Visible text and active content
are lossy children. The original string stays the evidence root.

A start tag is one `html.parser` start tag. An attribute is one attribute on
those tags, summed across the document. Depth is not a separate budget.
"""

from html.parser import HTMLParser

from vetoq.ingestion.contracts import (
    Canonicalization,
    DerivedRepresentation,
    RepresentationKind,
    TransformStep,
    require_derived_budget,
)
from vetoq.ingestion.errors import (
    IngestionError,
    input_limit,
    malformed_content,
    unsupported_media_type,
)
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import DeclaredFormat, MediaType, normalize_media_type
from vetoq.ingestion.source_text import AcceptedSource, validate_source_text

_PARSER_ID = "html_inert"
_PARSER_VERSION = "1"
_SPECIAL = frozenset({"script", "style", "template"})
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "option",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
# Exact names, plus any `on*` event handler longer than "on".
# `data` is the object/embed URL attribute, not a data-* dump.
_ACTIVE_ATTRIBUTES = frozenset(
    {
        "action",
        "alt",
        "aria-label",
        "background",
        "cite",
        "data",
        "formaction",
        "href",
        "longdesc",
        "ping",
        "placeholder",
        "poster",
        "src",
        "srcdoc",
        "srcset",
        "style",
        "title",
        "value",
    }
)


class HtmlInert:
    """Inert text/html extraction. Tolerance is not trust."""

    media_type = MediaType.HTML
    parser_id = _PARSER_ID
    parser_version = _PARSER_VERSION

    def validate(self, source: str, declaration: DeclaredFormat) -> str:
        if declaration.media_type is not MediaType.HTML:
            raise unsupported_media_type()
        exact = validate_source_text(source, declaration.charset)
        require_derived_budget(_html_parts(exact), pre_accept=True)
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
        return Canonicalization(derived=_bounded_derived(_html_parts(exact)))


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.active: list[tuple[str, str, str]] = []
        self._modes: list[str] = []
        self._buffers: list[list[str]] = []
        self._start_tags = 0
        self._attributes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start_tags += 1
        if self._start_tags > BUDGETS.html_start_tags:
            raise input_limit(422)
        self._attributes += len(attrs)
        if self._attributes > BUDGETS.html_attributes:
            raise input_limit(422)
        for name, value in attrs:
            if value and value.strip() and _is_active_attribute(name):
                self.active.append(("attr", name.lower(), value))
        if tag == "meta":
            _capture_meta_refresh(attrs, self.active)
        if tag in _SPECIAL:
            self._modes.append(tag)
            self._buffers.append([])
        elif not self._modes and tag in _BLOCK_TAGS:
            self.visible.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._modes and self._modes[-1] == tag:
            self._flush_mode()
        elif not self._modes and tag in _BLOCK_TAGS:
            self.visible.append("\n")

    def handle_data(self, data: str) -> None:
        if self._modes:
            self._buffers[-1].append(data)
        else:
            self.visible.append(data)

    def handle_comment(self, data: str) -> None:
        if data.strip():
            self.active.append(("comment", "", data))

    def finish(self) -> None:
        while self._modes:
            self._flush_mode()

    def _flush_mode(self) -> None:
        tag = self._modes.pop()
        body = "".join(self._buffers.pop())
        if body.strip():
            self.active.append((tag, "", body))


def _collect(source: str) -> _Collector:
    collector = _Collector()
    try:
        collector.feed(source)
        collector.close()
        collector.finish()
    except IngestionError:
        raise
    except RecursionError:
        raise input_limit(422) from None
    except Exception:
        raise malformed_content() from None
    return collector


def _capture_meta_refresh(
    attrs: list[tuple[str, str | None]],
    active: list[tuple[str, str, str]],
) -> None:
    """Record a refresh directive. Other `content` attributes stay out."""

    equiv: str | None = None
    content: str | None = None
    for name, value in attrs:
        lowered = name.lower()
        if lowered == "http-equiv":
            equiv = value
        elif lowered == "content":
            content = value
    if equiv and content and equiv.strip().lower() == "refresh" and content.strip():
        active.append(("attr", "http-equiv", equiv))
        active.append(("attr", "content", content))


def _html_parts(source: str) -> list[DerivedRepresentation]:
    collector = _collect(source)
    parts: list[DerivedRepresentation] = []
    visible = _collapse_whitespace(collector.visible)
    if visible:
        parts.append(_derived(RepresentationKind.CANONICAL_TEXT, visible, "html-visible-text"))
    active = _active_text(collector.active)
    if active:
        parts.append(_derived(RepresentationKind.ACTIVE_CONTENT, active, "html-active-content"))
    return parts


def _is_active_attribute(name: str) -> bool:
    lowered = name.lower()
    if lowered in _ACTIVE_ATTRIBUTES:
        return True
    return lowered.startswith("on") and len(lowered) > 2


def _collapse_whitespace(parts: list[str]) -> str:
    """Join text, then collapse every whitespace run to one space.

    Block tags have already inserted separators. Inline tags have not, so
    `<em>c</em>at` stays `cat`. This is not browser layout.
    """

    text = "".join(parts)
    collapsed: list[str] = []
    pending = False
    started = False
    for character in text:
        if character.isspace():
            pending = True
            continue
        if pending and started:
            collapsed.append(" ")
        pending = False
        started = True
        collapsed.append(character)
    return "".join(collapsed)


def _active_text(records: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for label, name, value in records:
        if not value.strip():
            continue
        if label == "attr":
            lines.append(f"attr {name}\n{value}")
        else:
            lines.append(f"{label}\n{value}")
    return "\n".join(lines)


def _derived(kind: RepresentationKind, content: str, transform: str) -> DerivedRepresentation:
    return DerivedRepresentation(
        kind=kind,
        content=content,
        parser_id=_PARSER_ID,
        parser_version=_PARSER_VERSION,
        transform=transform,
        transform_version="1",
        lossy=True,
        transform_steps=(TransformStep(transform, "1"),),
    )


def _bounded_derived(parts: list[DerivedRepresentation]) -> tuple[DerivedRepresentation, ...]:
    """Canonicalization backstop. Pre-accept refusal uses `input_limit`."""

    return require_derived_budget(parts, pre_accept=False)
