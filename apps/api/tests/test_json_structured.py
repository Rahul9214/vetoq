"""json_structured/1. POST /runs does not call this adapter."""

import pytest

from vetoq.contracts import Submission
from vetoq.ingestion.contracts import Canonicalization, RepresentationKind
from vetoq.ingestion.errors import IngestionError, ProcessingFailure
from vetoq.ingestion.identity import source_digest
from vetoq.ingestion.json_structured import JsonStructured, _bounded_canonical
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.markdown import Markdown
from vetoq.ingestion.media_types import MediaType, normalize_media_type
from vetoq.ingestion.registry import new_registry, production_registry
from vetoq.ingestion.text_plain import TextPlain

JSON = normalize_media_type("application/json")


def test_objects_arrays_and_scalar_roots() -> None:
    adapter = JsonStructured()
    for source in ('{"b":1,"a":2}', "[1,2]", '"hi"', "1", "true", "false", "null"):
        assert adapter.validate(source, JSON) is source
    result = adapter.canonicalize('{"b":1,"a":2}', JSON)
    assert result.succeeded is True
    assert len(result.derived) == 1
    child = result.derived[0]
    assert child.content == '{"a":2,"b":1}'
    assert child.kind is RepresentationKind.CANONICAL_TEXT
    assert child.parser_id == "json_structured"
    assert child.parser_version == "1"
    assert child.transform == "json-canonical"
    assert child.transform_version == "1"
    assert child.lossy is True


def test_depth_boundary() -> None:
    adapter = JsonStructured()
    assert adapter.validate(_nested(BUDGETS.json_nesting_depth), JSON)
    with pytest.raises(IngestionError, match="input_limit") as caught:
        adapter.validate(_nested(BUDGETS.json_nesting_depth + 1), JSON)
    assert caught.value.status == 422


def test_member_boundary() -> None:
    adapter = JsonStructured()
    assert adapter.validate(_array(BUDGETS.json_members), JSON)
    with pytest.raises(IngestionError, match="input_limit") as caught:
        adapter.validate(_array(BUDGETS.json_members + 1), JSON)
    assert caught.value.status == 422


@pytest.mark.parametrize(
    "source",
    [
        '{"SENTINEL":1,"SENTINEL":2}',
        '{"a":{"SENTINEL":1,"SENTINEL":2}}',
        '[{"SENTINEL":1,"SENTINEL":2}]',
    ],
)
def test_duplicate_keys_are_rejected(source: str) -> None:
    with pytest.raises(IngestionError, match="malformed_content") as caught:
        JsonStructured().validate(source, JSON)
    assert "SENTINEL" not in str(caught.value)


@pytest.mark.parametrize("source", ["NaN", "Infinity", "-Infinity", '{"a":NaN}', "1e309"])
def test_nonfinite_numbers_are_rejected(source: str) -> None:
    with pytest.raises(IngestionError, match="malformed_content") as caught:
        JsonStructured().validate(source, JSON)
    assert source not in str(caught.value)


@pytest.mark.parametrize("source", ["{", '{"a":', "[1,2", '{"a":"line\nbreak"}', "\ufeff{}"])
def test_malformed_and_truncated_json_is_rejected(source: str) -> None:
    with pytest.raises(IngestionError, match="malformed_content"):
        JsonStructured().validate(source, JSON)


def test_strings_do_not_change_structural_depth() -> None:
    source = r'{"z":"[[[]]]", "a":"quo\"te", "m":{"c":1}}'
    result = JsonStructured().canonicalize(source, JSON)
    assert result.succeeded is True
    assert result.derived[0].content == r'{"a":"quo\"te","m":{"c":1},"z":"[[[]]]"}'


def test_deep_nesting_fails_as_input_limit() -> None:
    source = "[" * 4000 + "0" + "]" * 4000
    with pytest.raises(IngestionError, match="input_limit") as caught:
        JsonStructured().validate(source, JSON)
    assert caught.value.status == 422
    assert not isinstance(caught.value, RecursionError)
    assert "[" not in str(caught.value)


def test_canonical_form_is_deterministic_and_distinct_from_the_source_digest() -> None:
    spaced = '{ "b" : 1, "a" : 2 }'
    compact = '{"a":2,"b":1}'
    adapter = JsonStructured()
    left = adapter.canonicalize(spaced, JSON).derived[0].content
    right = adapter.canonicalize(compact, JSON).derived[0].content
    assert left == right == '{"a":2,"b":1}'
    assert " " not in left
    assert source_digest(spaced) != source_digest(compact)
    original = '{"é":"你","b":1}'
    assert adapter.validate(original, JSON) is original
    assert adapter.canonicalize(original, JSON).derived[0].content == '{"b":1,"é":"你"}'


def test_numeric_reencoding_is_not_truncated() -> None:
    result = JsonStructured().canonicalize("[1e2,1.0]", JSON)
    assert result.derived[0].content == "[100.0,1.0]"
    oversized = "SENTINEL" + ("y" * BUDGETS.derived_text_bytes)
    with pytest.raises(ProcessingFailure, match="parser_limit_exceeded") as caught:
        _bounded_canonical(oversized)
    assert "SENTINEL" not in str(caught.value)
    assert caught.value.args == ("parser_limit_exceeded",)


def test_huge_integer_is_a_bounded_error_without_the_digits() -> None:
    source = "9" * 5000
    with pytest.raises(IngestionError, match="input_limit") as caught:
        JsonStructured().validate(source, JSON)
    assert "999" not in str(caught.value)
    assert caught.value.status == 422


def test_registry_still_resolves_json_without_fallback() -> None:
    assert new_registry().implemented() == frozenset()
    registry = production_registry()
    plain = registry.resolve(MediaType.TEXT_PLAIN)
    structured = registry.resolve_declared("application/json")
    markdown = registry.resolve_declared("text/markdown")
    assert isinstance(plain, TextPlain)
    assert plain.parser_id == "text_plain" and plain.parser_version == "1"
    assert isinstance(structured, JsonStructured)
    assert structured.parser_id == "json_structured" and structured.parser_version == "1"
    assert isinstance(markdown, Markdown)
    assert markdown.parser_id == "markdown" and markdown.parser_version == "1"
    with pytest.raises(IngestionError, match="unsupported_media_type"):
        registry.resolve_declared("application/pdf")
    assert registry.resolve(MediaType.JSON) is structured
    assert frozenset({MediaType.TEXT_PLAIN, MediaType.JSON, MediaType.MARKDOWN}) <= (
        registry.implemented()
    )
    assert registry.contract_supported() == frozenset(MediaType)
    assert "sanitized" not in Submission.model_fields
    assert "media_type" in Submission.model_fields
    success = structured.canonicalize("{}", JSON)
    assert isinstance(success, Canonicalization)
    assert success.succeeded is True
    assert len(success.derived) == 1


def _nested(depth: int) -> str:
    return "[" * depth + "0" + "]" * depth


def _array(members: int) -> str:
    return "[" + ",".join(["0"] * members) + "]"
