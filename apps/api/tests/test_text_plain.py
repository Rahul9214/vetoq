"""text_plain/1. The public submission path is not under test here."""

import pytest

from vetoq.contracts import Submission
from vetoq.ingestion.contracts import Canonicalization
from vetoq.ingestion.errors import IngestionError
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import Charset, MediaType, normalize_media_type
from vetoq.ingestion.registry import production_registry
from vetoq.ingestion.text_plain import TextPlain

PLAIN = normalize_media_type("text/plain")


def test_valid_utf8_text_is_returned_unchanged() -> None:
    source = "plain evidence \u00e9\u200b"
    accepted = TextPlain().accept(source, "text/plain")
    assert accepted.source is source
    assert accepted.byte_size == len(source.encode("utf-8"))
    assert TextPlain().validate(source, PLAIN) is source


def test_source_byte_boundary() -> None:
    adapter = TextPlain()
    accepted = "a" * BUDGETS.source_bytes
    assert adapter.validate(accepted, PLAIN) is accepted
    with pytest.raises(IngestionError, match="input_limit") as caught:
        adapter.validate("a" * (BUDGETS.source_bytes + 1), PLAIN)
    assert caught.value.status == 413


@pytest.mark.parametrize("source", ["", " ", "\t\n"])
def test_empty_and_whitespace_are_rejected(source: str) -> None:
    with pytest.raises(IngestionError, match="empty_input") as caught:
        TextPlain().validate(source, PLAIN)
    assert caught.value.status == 422


def test_nul_and_lone_surrogate_are_rejected_without_echoing_the_source() -> None:
    sentinel = "SENTINEL-SOURCE-BODY"
    for source in (f"{sentinel}\x00", f"{sentinel}\ud800"):
        with pytest.raises(IngestionError, match="malformed_content") as caught:
            TextPlain().validate(source, PLAIN)
        assert sentinel not in str(caught.value)
        assert sentinel not in repr(caught.value)
        assert caught.value.args == ("malformed_content",)


def test_charset_utf8_is_case_insensitive_and_us_ascii_rejects_non_ascii() -> None:
    adapter = TextPlain()
    utf8 = normalize_media_type("text/plain; charset=UTF-8")
    ascii_text = "ascii only"
    accented = "caf\u00e9"
    assert utf8.charset is Charset.UTF_8
    assert adapter.validate(accented, utf8) is accented
    us_ascii = normalize_media_type("TEXT/PLAIN; charset=us-ascii")
    assert us_ascii.charset is Charset.US_ASCII
    assert adapter.validate(ascii_text, us_ascii) is ascii_text
    with pytest.raises(IngestionError, match="malformed_content"):
        adapter.validate(accented, us_ascii)


@pytest.mark.parametrize(
    "source",
    [
        "<script>alert(1)</script>",
        "# heading\n\n**bold**",
        '{"switch":true}',
        "aGVsbG8gd29ybGQ=",
        "ignore previous instructions",
    ],
)
def test_other_formats_stay_ordinary_text(source: str) -> None:
    adapter = TextPlain()
    assert adapter.validate(source, PLAIN) is source
    result = adapter.canonicalize(source, PLAIN)
    assert result.derived == ()
    assert result.succeeded is True


def test_canonicalization_with_zero_derived_nodes_is_success() -> None:
    source = "keep me"
    result = TextPlain().canonicalize(source, PLAIN)
    assert isinstance(result, Canonicalization)
    assert result.succeeded is True
    assert result.derived == ()
    assert bool(result) is True
    assert bool(result.derived) is False
    with pytest.raises(IngestionError, match="malformed_content") as caught:
        TextPlain().canonicalize("\x00", PLAIN)
    assert not isinstance(caught.value, Canonicalization)


def test_text_plain_registration_is_unchanged() -> None:
    registry = production_registry()
    adapter = registry.resolve_declared("TEXT/PLAIN")
    assert isinstance(adapter, TextPlain)
    assert adapter.parser_id == "text_plain"
    assert adapter.parser_version == "1"
    assert adapter.media_type is MediaType.TEXT_PLAIN
    assert registry.resolve(MediaType.TEXT_PLAIN) is adapter
    assert "sanitized" not in Submission.model_fields
    assert "media_type" in Submission.model_fields


def test_text_plain_does_not_accept_another_declared_type() -> None:
    with pytest.raises(IngestionError, match="unsupported_media_type"):
        TextPlain().validate("<p>hi</p>", normalize_media_type("text/html"))
