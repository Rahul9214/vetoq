"""email_rfc822/1. One unsupported leaf rejects the whole message."""

from dataclasses import replace
from email import errors
from pathlib import Path

import pytest

from vetoq.contracts import Submission
from vetoq.ingestion.contracts import DerivedRepresentation, RepresentationKind
from vetoq.ingestion.email_rfc822 import (
    _TOLERABLE_DEFECTS,
    EmailRfc822,
    _bounded_derived,
    _header_section,
)
from vetoq.ingestion.errors import IngestionError, ProcessingFailure, RegistryError
from vetoq.ingestion.html_inert import HtmlInert
from vetoq.ingestion.json_structured import JsonStructured
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.markdown import Markdown
from vetoq.ingestion.media_types import MediaType, normalize_media_type
from vetoq.ingestion.registry import new_registry, production_registry
from vetoq.ingestion.text_plain import TextPlain

RFC = normalize_media_type("message/rfc822")


def _assert_code(source: str, code: str) -> None:
    with pytest.raises(IngestionError, match=code) as caught:
        EmailRfc822().validate(source, RFC)
    assert caught.value.code == code
    assert caught.value.status == 422
    assert "SENTINEL" not in str(caught.value)


def _mixed(parts: list[tuple[str, str]]) -> str:
    chunks = ["Content-Type: multipart/mixed; boundary=b\n\n"]
    for media, body in parts:
        chunks.append(f"--b\nContent-Type: {media}\n\n{body}\n")
    chunks.append("--b--\n")
    return "".join(chunks)


def _flat(count: int) -> str:
    parts = [("text/plain", f"part-{index}") for index in range(count)]
    return _mixed(parts)


def _nested(wraps: int) -> str:
    body = "Content-Type: text/plain\n\nx\n"
    for index in range(wraps):
        boundary = f"b{index}"
        body = (
            f"Content-Type: multipart/mixed; boundary={boundary}\n\n"
            f"--{boundary}\n{body}--{boundary}--\n"
        )
    return body


def test_simple_text_and_utf8_and_absent_charset() -> None:
    source = "From: Ada <ada@example.invalid>\n\nhello\n"
    assert EmailRfc822().validate(source, RFC) is source
    result = EmailRfc822().canonicalize(source, RFC)
    assert result.succeeded is True
    assert result.derived[0].transform == "email-headers"
    assert result.derived[0].content == "from: Ada <ada@example.invalid>"
    assert result.derived[1].content == "hello\n"
    assert result.derived[1].transform == "email-part-text"
    assert result.derived[1].parser_id == "text_plain"
    assert result.derived[1].lossy is True
    utf8 = "Content-Type: text/plain; charset=utf-8\n\ncafé\n"
    assert "café" in EmailRfc822().canonicalize(utf8, RFC).derived[1].content
    ascii_body = "Content-Type: text/plain\n\ncafe\n"
    plain = EmailRfc822().canonicalize(ascii_body, RFC)
    assert plain.derived[1].content == "cafe\n"
    _assert_code("Content-Type: text/plain\n\ncafé SENTINEL\n", "malformed_content")


def test_quoted_printable_and_base64_and_bad_base64() -> None:
    quoted = (
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: quoted-printable\n"
        "\n"
        "h=C3=A9llo\n"
    )
    assert "héllo" in EmailRfc822().canonicalize(quoted, RFC).derived[1].content
    encoded = (
        "Content-Type: text/plain; charset=us-ascii\n"
        "Content-Transfer-Encoding: base64\n"
        "\n"
        "aGVsbG8=\n"
    )
    assert EmailRfc822().canonicalize(encoded, RFC).derived[1].content == "hello"
    _assert_code(
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: base64\n"
        "\n"
        "!!!! SENTINEL\n",
        "malformed_content",
    )


def test_unsupported_encoding_charset_and_undecodable_bytes() -> None:
    _assert_code(
        "Content-Type: text/plain\nContent-Transfer-Encoding: binary\n\nSENTINEL\n",
        "unsupported_embedded_content",
    )
    _assert_code(
        "Content-Type: text/plain; charset=iso-8859-1\n\nSENTINEL\n",
        "unsupported_embedded_content",
    )
    _assert_code(
        "Content-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: base64\n\n/w==\n",
        "malformed_content",
    )
    _assert_code(
        "Content-Transfer-Encoding: 7bit\nContent-Transfer-Encoding: base64\n\nSENTINEL\n",
        "malformed_content",
    )


def test_multipart_visits_every_alternative_and_reuses_adapters() -> None:
    source = (
        "Content-Type: multipart/alternative; boundary=b\n"
        "\n"
        "--b\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "plain-leaf\n"
        "--b\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        "<p>shown</p><script>hidden</script>\n"
        "--b\n"
        "Content-Type: text/markdown; charset=utf-8\n"
        "\n"
        "# title\n\n<script>stay</script>\n"
        "--b\n"
        "Content-Type: application/json; charset=utf-8\n"
        "\n"
        '{"b":1,"a":2}\n'
        "--b--\n"
    )
    result = EmailRfc822().canonicalize(source, RFC)
    transforms = [part.transform for part in result.derived]
    assert transforms == [
        "email-headers",
        "email-part-text",
        "email-part-html-visible",
        "email-part-html-active",
        "email-part-markdown",
        "email-part-json",
    ]
    assert result.derived[1].content == "plain-leaf"
    assert result.derived[2].content == "shown"
    assert "hidden" in result.derived[3].content
    assert "shown" not in result.derived[3].content
    assert result.derived[3].kind is RepresentationKind.ACTIVE_CONTENT
    assert result.derived[3].parser_id == "html_inert"
    assert "<script>stay</script>" in result.derived[4].content
    assert result.derived[4].parser_id == "markdown"
    assert result.derived[5].content == '{"a":2,"b":1}'
    assert result.derived[5].parser_id == "json_structured"
    _assert_code(
        _mixed([("application/json", '{"a":"SENTINEL","a":2}')]),
        "malformed_content",
    )


@pytest.mark.parametrize(
    "media",
    [
        "application/pdf",
        "image/png",
        "application/zip",
        "application/octet-stream",
        "message/rfc822",
        "application/x-unknown",
        "message/external-body",
    ],
)
def test_unsupported_leaf_rejects_the_whole_message(media: str) -> None:
    _assert_code(
        _mixed([("text/plain", "ok"), (media, "SENTINEL")]),
        "unsupported_embedded_content",
    )


def test_nested_containers_count_and_part_budget_is_exact() -> None:
    assert EmailRfc822().validate(_nested(32), RFC)
    _assert_code(_nested(33), "input_limit")
    _assert_code(_flat(33), "input_limit")


def test_header_budget_includes_the_separator() -> None:
    crlf = "From: a@b.invalid\r\n\r\nbody\r\n"
    assert _header_section(crlf) == "From: a@b.invalid\r\n\r\n"
    assert len(_header_section(crlf).encode("utf-8")) == len(b"From: a@b.invalid\r\n\r\n")
    folded = "Subject: hello\n world\n\nbody\n"
    headers = EmailRfc822().canonicalize(folded, RFC).derived[0].content
    assert headers == "subject: hello world"

    def sized(total: int) -> str:
        separator = "\n\n"
        prefix = "From: "
        filler = total - len(prefix) - len(separator)
        return prefix + ("a" * filler) + separator + "SENTINEL\n"

    assert len(_header_section(sized(BUDGETS.email_header_bytes)).encode("utf-8")) == (
        BUDGETS.email_header_bytes
    )
    assert EmailRfc822().validate(sized(BUDGETS.email_header_bytes), RFC)
    _assert_code(sized(BUDGETS.email_header_bytes + 1), "input_limit")


def test_html_part_does_not_fetch_and_attachment_is_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fetch")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    monkeypatch.setattr("socket.create_connection", explode)
    monkeypatch.chdir(tmp_path)
    source = (
        "Content-Type: text/html; charset=utf-8\n"
        "Content-Disposition: attachment; filename=secret.bin\n"
        "\n"
        '<a href="https://example.invalid/path">label</a>\n'
    )
    result = EmailRfc822().canonicalize(source, RFC)
    active = next(
        part.content for part in result.derived if part.transform == "email-part-html-active"
    )
    assert "https://example.invalid/path" in active
    assert list(tmp_path.iterdir()) == []


def test_aggregate_budgets_fail_before_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    accepted = _flat(31)
    assert EmailRfc822().validate(accepted, RFC) is accepted
    result = EmailRfc822().canonicalize(accepted, RFC)
    assert result.succeeded is True
    assert len(result.derived) == 32
    assert accepted not in {part.content for part in result.derived}
    over = _flat(32)
    with pytest.raises(IngestionError, match="input_limit") as caught:
        EmailRfc822().validate(over, RFC)
    assert caught.value.status == 422
    assert "part-0" not in str(caught.value)
    with pytest.raises(IngestionError, match="input_limit"):
        EmailRfc822().canonicalize(over, RFC)
    source = "Content-Type: text/plain\n\nhello\n"
    sized = EmailRfc822().canonicalize(source, RFC)
    total = sum(len(part.content.encode("utf-8")) for part in sized.derived)
    monkeypatch.setattr(
        "vetoq.ingestion.contracts.BUDGETS",
        replace(BUDGETS, derived_text_bytes=total),
    )
    assert EmailRfc822().validate(source, RFC) is source
    monkeypatch.setattr(
        "vetoq.ingestion.contracts.BUDGETS",
        replace(BUDGETS, derived_text_bytes=total - 1),
    )
    with pytest.raises(IngestionError, match="input_limit") as caught:
        EmailRfc822().validate(source, RFC)
    assert "hello" not in str(caught.value)


def test_source_identity_and_from_header_are_not_authority() -> None:
    source = "From: Mallory <mallory@example.invalid>\nBcc: hidden@example.invalid\n\nbody\n"
    first = EmailRfc822().canonicalize(source, RFC)
    second = EmailRfc822().canonicalize(source, RFC)
    assert first == second
    assert (
        source == "From: Mallory <mallory@example.invalid>\nBcc: hidden@example.invalid\n\nbody\n"
    )
    assert first.derived[0].content == (
        "from: Mallory <mallory@example.invalid>\nbcc: hidden@example.invalid"
    )
    absent = EmailRfc822().canonicalize("Subject: hi\n\nbody\n", RFC)
    assert "bcc" not in absent.derived[0].content
    assert not hasattr(first, "principal")
    assert not hasattr(first, "authenticated")
    assert "sanitized" not in Submission.model_fields
    assert "media_type" in Submission.model_fields


def test_fatal_defects_and_tolerable_policy() -> None:
    assert _TOLERABLE_DEFECTS == (
        errors.ObsoleteHeaderDefect,
        errors.NonPrintableDefect,
        errors.NonASCIILocalPartDefect,
        errors.InvalidDateDefect,
    )
    _assert_code("Content-Type: multipart/mixed\n\nSENTINEL\n", "malformed_content")
    _assert_code(
        "Content-Type: multipart/mixed; boundary=b\n\n--b\nContent-Type: text/plain\n\nSENTINEL\n",
        "malformed_content",
    )
    _assert_code(" Subject: SENTINEL\n\nbody\n", "malformed_content")
    _assert_code("\ufeffFrom: a@b.invalid\n\nSENTINEL\n", "malformed_content")
    dated = "Date: not-a-date\n\nhello\n"
    text = next(
        part.content
        for part in EmailRfc822().canonicalize(dated, RFC).derived
        if part.transform == "email-part-text"
    )
    assert text == "hello\n"


def _chain(source: str, transform: str) -> tuple[tuple[str, str], ...]:
    result = EmailRfc822().canonicalize(source, RFC)
    part = next(item for item in result.derived if item.transform == transform)
    return tuple((step.transform, step.version) for step in part.transform_steps)


def test_email_transform_lineage_is_ordered_and_deterministic() -> None:
    plain = "Content-Type: text/plain\n\nhello\n"
    markdown = "Content-Type: text/markdown\n\n# title\n"
    structured = 'Content-Type: application/json\n\n{"b":1,"a":2}\n'
    html = "Content-Type: text/html\n\n<p>shown</p><script>hidden</script>\n"
    assert _chain(plain, "email-part-text") == (
        ("email-part-decode", "1"),
        ("email-part-text", "1"),
    )
    assert _chain(markdown, "email-part-markdown") == (
        ("email-part-decode", "1"),
        ("email-part-markdown", "1"),
    )
    assert _chain(structured, "email-part-json") == (
        ("email-part-decode", "1"),
        ("json-canonical", "1"),
    )
    assert _chain(html, "email-part-html-visible") == (
        ("email-part-decode", "1"),
        ("html-visible-text", "1"),
    )
    assert _chain(html, "email-part-html-active") == (
        ("email-part-decode", "1"),
        ("html-active-content", "1"),
    )
    json_part = next(
        part
        for part in EmailRfc822().canonicalize(structured, RFC).derived
        if part.transform == "email-part-json"
    )
    assert json_part.parser_id == "json_structured"
    assert json_part.content == '{"a":2,"b":1}'
    again = EmailRfc822().canonicalize(html, RFC)
    assert again == EmailRfc822().canonicalize(html, RFC)


def test_quoted_printable_escapes_are_strict() -> None:
    ordinary = (
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: quoted-printable\n"
        "\n"
        "Hello there.\n"
    )
    assert "Hello there." in EmailRfc822().canonicalize(ordinary, RFC).derived[1].content
    encoded = (
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: quoted-printable\n"
        "\n"
        "h=C3=A9llo\n"
    )
    assert "héllo" in EmailRfc822().canonicalize(encoded, RFC).derived[1].content
    soft = (
        "Content-Type: text/plain; charset=us-ascii\n"
        "Content-Transfer-Encoding: quoted-printable\n"
        "\n"
        "hel=\nlo\n"
    )
    assert "hello" in EmailRfc822().canonicalize(soft, RFC).derived[1].content
    crlf_soft = (
        "Content-Type: text/plain; charset=us-ascii\r\n"
        "Content-Transfer-Encoding: quoted-printable\r\n"
        "\r\n"
        "hel=\r\nlo\r\n"
    )
    assert "hello" in EmailRfc822().canonicalize(crlf_soft, RFC).derived[1].content
    _assert_code(
        "Content-Type: text/plain\nContent-Transfer-Encoding: quoted-printable\n\n=GG SENTINEL\n",
        "malformed_content",
    )
    _assert_code(
        "Content-Type: text/plain\nContent-Transfer-Encoding: quoted-printable\n\nend=SENTINEL\n",
        "malformed_content",
    )
    _assert_code(
        "Content-Type: text/plain\nContent-Transfer-Encoding: quoted-printable\n\n=A SENTINEL\n",
        "malformed_content",
    )


def test_empty_supported_leaf_is_traversed_and_omitted() -> None:
    source = _mixed([("text/plain", "   "), ("text/plain", "kept")])
    result = EmailRfc822().canonicalize(source, RFC)
    texts = [part.content for part in result.derived if part.transform == "email-part-text"]
    assert texts == ["kept"]
    assert result.succeeded is True


def test_derived_budget_backstop_is_parser_limit_exceeded() -> None:
    oversized = DerivedRepresentation(
        kind=RepresentationKind.CANONICAL_TEXT,
        content="SENTINEL" + ("y" * BUDGETS.derived_text_bytes),
        parser_id="text_plain",
        parser_version="1",
        transform="email-part-text",
        transform_version="1",
        lossy=True,
    )
    with pytest.raises(ProcessingFailure, match="parser_limit_exceeded") as caught:
        _bounded_derived([oversized])
    assert "SENTINEL" not in str(caught.value)


def test_production_registry_has_exactly_the_five_adapters() -> None:
    assert new_registry().implemented() == frozenset()
    registry = production_registry()
    assert isinstance(registry.resolve(MediaType.TEXT_PLAIN), TextPlain)
    assert isinstance(registry.resolve(MediaType.JSON), JsonStructured)
    assert isinstance(registry.resolve(MediaType.MARKDOWN), Markdown)
    assert isinstance(registry.resolve_declared("text/html"), HtmlInert)
    assert isinstance(registry.resolve_declared("message/rfc822"), EmailRfc822)
    html = registry.resolve(MediaType.HTML)
    mail = registry.resolve(MediaType.RFC822)
    assert html.parser_id == "html_inert" and html.parser_version == "1"
    assert mail.parser_id == "email_rfc822" and mail.parser_version == "1"
    assert registry.implemented() == frozenset(MediaType)
    assert registry.contract_supported() == frozenset(MediaType)
    with pytest.raises(IngestionError, match="unsupported_media_type"):
        registry.resolve_declared("application/pdf")
    with pytest.raises(RegistryError, match="adapter_not_implemented"):
        new_registry().resolve(MediaType.HTML)
    text = (
        Path(__file__)
        .parents[1]
        .joinpath("src/vetoq/ingestion/email_rfc822.py")
        .read_text(encoding="utf-8")
    )
    assert "urlopen" not in text
    assert "open(" not in text
