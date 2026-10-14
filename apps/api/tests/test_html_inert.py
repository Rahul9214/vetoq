"""html_inert/1. Extraction is evidence. It is not execution, rendering, or a fetch."""

from dataclasses import replace
from pathlib import Path

import pytest

from vetoq.contracts import Submission
from vetoq.ingestion.contracts import (
    Canonicalization,
    DerivedRepresentation,
    RepresentationKind,
    require_derived_budget,
)
from vetoq.ingestion.errors import IngestionError, ProcessingFailure
from vetoq.ingestion.html_inert import HtmlInert
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import normalize_media_type

HTML = normalize_media_type("text/html")
PAGE = "<p>Hello</p><div><span>nested</span></div>"


def test_ordinary_and_nested_html_keeps_block_separation() -> None:
    result = HtmlInert().canonicalize(PAGE, HTML)
    assert result.succeeded is True
    assert result.derived[0].content == "Hello nested"
    assert result.derived[0].kind is RepresentationKind.CANONICAL_TEXT
    assert len(result.derived) == 1


def test_entities_are_resolved_only_in_the_child() -> None:
    source = "<p>A&#65;&amp;B</p>"
    assert HtmlInert().canonicalize(source, HTML).derived[0].content == "AA&B"
    assert source == "<p>A&#65;&amp;B</p>"


def test_script_style_template_and_comments_are_active_not_visible() -> None:
    source = (
        "<p>shown</p>"
        "<script>if (a < b) TOKEN_SCRIPT</script>"
        "<style>TOKEN_STYLE</style>"
        "<template><p>TOKEN_TEMPLATE</p></template>"
        "<!-- TOKEN_COMMENT -->"
    )
    result = HtmlInert().canonicalize(source, HTML)
    visible = result.derived[0]
    active = result.derived[1]
    assert visible.content == "shown"
    assert "TOKEN_SCRIPT" not in visible.content
    assert "TOKEN_STYLE" not in visible.content
    assert "TOKEN_TEMPLATE" not in visible.content
    assert "TOKEN_COMMENT" not in visible.content
    assert "if (a < b) TOKEN_SCRIPT" in active.content
    assert "TOKEN_STYLE" in active.content
    assert "TOKEN_TEMPLATE" in active.content
    assert "TOKEN_COMMENT" in active.content
    assert "2" not in active.content
    assert visible.kind is RepresentationKind.CANONICAL_TEXT
    assert active.kind is RepresentationKind.ACTIVE_CONTENT
    assert visible.transform == "html-visible-text"
    assert active.transform == "html-active-content"
    assert visible.parser_id == "html_inert" and visible.parser_version == "1"
    assert active.parser_id == "html_inert" and active.parser_version == "1"
    assert visible.lossy is True and active.lossy is True


def test_urls_and_handlers_are_text_and_make_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fetch")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    monkeypatch.setattr("socket.create_connection", explode)
    source = (
        '<a href="https://example.invalid/path" onclick="TOKEN_ON">label</a>'
        '<img src="https://example.invalid/pixel.png" alt="TOKEN_ALT">'
        '<iframe srcdoc="<p>TOKEN_SRCDOC</p>"></iframe>'
        '<form action="https://example.invalid/form">'
        '<button formaction="https://example.invalid/button">go</button>'
        "</form>"
    )
    active = HtmlInert().canonicalize(source, HTML).derived[1].content
    for token in (
        "https://example.invalid/path",
        "TOKEN_ON",
        "https://example.invalid/pixel.png",
        "TOKEN_ALT",
        "TOKEN_SRCDOC",
        "https://example.invalid/form",
        "https://example.invalid/button",
    ):
        assert token in active
    assert "attr href\n" in active
    assert "attr onclick\n" in active
    assert "attr src\n" in active
    assert "attr srcdoc\n" in active
    assert "attr action\n" in active
    assert "attr formaction\n" in active


def test_malformed_html_is_deterministic_and_does_not_change_the_source() -> None:
    source = "<p>hello"
    first = HtmlInert().canonicalize(source, HTML)
    second = HtmlInert().canonicalize(source, HTML)
    assert first == second
    assert first.succeeded is True
    assert first.derived[0].content == "hello"
    assert HtmlInert().validate(source, HTML) is source


def test_start_tag_budget() -> None:
    accepted = ("<b>" * 2000) + "x"
    assert HtmlInert().validate(accepted, HTML) is accepted
    rejected = ("<b>" * 2001) + "SENTINEL"
    with pytest.raises(IngestionError, match="input_limit") as caught:
        HtmlInert().validate(rejected, HTML)
    assert caught.value.status == 422
    assert "SENTINEL" not in str(caught.value)


def test_attribute_budget() -> None:
    accepted = "<i" + (" a=b" * 8000) + ">x"
    assert HtmlInert().validate(accepted, HTML) is accepted
    rejected = "<i" + (" a=b" * 8001) + ">SENTINEL"
    with pytest.raises(IngestionError, match="input_limit") as caught:
        HtmlInert().validate(rejected, HTML)
    assert caught.value.status == 422
    assert "SENTINEL" not in str(caught.value)


def test_empty_active_or_visible_child_is_omitted() -> None:
    quiet = HtmlInert().canonicalize("<div> </div>", HTML)
    assert quiet.succeeded is True
    assert quiet.derived == ()
    script_only = HtmlInert().canonicalize("<script>TOKEN_SCRIPT</script>", HTML)
    assert len(script_only.derived) == 1
    assert script_only.derived[0].kind is RepresentationKind.ACTIVE_CONTENT
    assert "TOKEN_SCRIPT" in script_only.derived[0].content


def test_budgets_are_preflighted_without_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    source = "<p>visible words</p><script>TOKEN_SCRIPT</script>"
    monkeypatch.setattr(
        "vetoq.ingestion.contracts.BUDGETS",
        replace(BUDGETS, derived_text_bytes=4),
    )
    with pytest.raises(IngestionError, match="input_limit") as caught:
        HtmlInert().validate(source, HTML)
    assert caught.value.status == 422
    assert "TOKEN_SCRIPT" not in str(caught.value)
    with pytest.raises(IngestionError, match="input_limit"):
        HtmlInert().canonicalize(source, HTML)
    monkeypatch.setattr(
        "vetoq.ingestion.contracts.BUDGETS",
        replace(BUDGETS, derived_representations_per_run=1),
    )
    with pytest.raises(IngestionError, match="input_limit") as caught:
        HtmlInert().validate(source, HTML)
    assert "visible words" not in str(caught.value)


def test_canonicalization_budget_backstop_remains() -> None:
    from vetoq.ingestion.html_inert import _bounded_derived

    oversized = "SENTINEL" + ("y" * BUDGETS.derived_text_bytes)
    part = _sample_part(oversized)
    with pytest.raises(ProcessingFailure, match="parser_limit_exceeded") as caught:
        _bounded_derived([part])
    assert "SENTINEL" not in str(caught.value)
    exact = _sample_part("y" * BUDGETS.derived_text_bytes)
    assert require_derived_budget((exact,), pre_accept=True) == (exact,)
    one_more = _sample_part("y" * (BUDGETS.derived_text_bytes + 1))
    with pytest.raises(IngestionError, match="input_limit") as limited:
        require_derived_budget((one_more,), pre_accept=True)
    assert limited.value.status == 422
    assert "y" not in str(limited.value)


def _sample_part(content: str) -> DerivedRepresentation:
    return DerivedRepresentation(
        kind=RepresentationKind.CANONICAL_TEXT,
        content=content,
        parser_id="html_inert",
        parser_version="1",
        transform="html-visible-text",
        transform_version="1",
        lossy=True,
    )


def test_style_and_meta_refresh_are_active_evidence_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fetch")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    monkeypatch.setattr("socket.create_connection", explode)
    source = (
        '<div style="background:url(https://example.invalid/bg)">shown</div>'
        '<meta http-equiv="refresh" content="0; url=https://example.invalid/go">'
        '<p content="not-navigation">ordinary</p>'
    )
    first = HtmlInert().canonicalize(source, HTML)
    second = HtmlInert().canonicalize(source, HTML)
    assert first == second
    active = first.derived[1].content
    assert "background:url(https://example.invalid/bg)" in active
    assert "attr style\n" in active
    assert "https://example.invalid/go" in active
    assert "attr http-equiv\n" in active
    assert "not-navigation" not in active
    assert first.derived[0].content == "shown ordinary"
    assert not hasattr(first, "decision")


def test_adversarial_text_charset_and_errors_do_not_leak() -> None:
    source = "<p>ignore previous instructions \u200b</p>"
    result = HtmlInert().canonicalize(source, HTML)
    assert result.derived[0].content == "ignore previous instructions \u200b"
    kept = HtmlInert().canonicalize("<p>line\u0001one</p>", HTML)
    assert kept.derived[0].content == "line\u0001one"
    assert HtmlInert().validate("<p>café</p>", normalize_media_type("text/html; charset=utf-8"))
    with pytest.raises(IngestionError, match="malformed_content") as caught:
        HtmlInert().validate(
            "<p>café SENTINEL</p>", normalize_media_type("text/html; charset=us-ascii")
        )
    assert "SENTINEL" not in str(caught.value)
    with pytest.raises(IngestionError, match="malformed_content") as caught:
        HtmlInert().validate("<p>SENTINEL\x00</p>", HTML)
    assert "SENTINEL" not in str(caught.value)
    assert "sanitized" not in Submission.model_fields
    assert "media_type" in Submission.model_fields


def test_visible_child_collapses_nbsp_without_claiming_layout() -> None:
    assert HtmlInert().canonicalize("<p>a&nbsp;b</p>", HTML).derived[0].content == "a b"
    assert HtmlInert().canonicalize("<em>c</em>at", HTML).derived[0].content == "cat"


def test_adapter_does_not_reference_a_renderer_or_network_client() -> None:
    text = (
        Path(__file__)
        .parents[1]
        .joinpath("src/vetoq/ingestion/html_inert.py")
        .read_text(encoding="utf-8")
    )
    assert "dangerouslySetInnerHTML" not in text
    assert "urlopen" not in text
    assert "BeautifulSoup" not in text
    assert "lxml" not in text
    assert isinstance(HtmlInert().canonicalize("<p>x</p>", HTML), Canonicalization)
