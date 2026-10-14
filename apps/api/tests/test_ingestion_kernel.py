"""Ingestion kernel. No format parser, no route, and no database write."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from vetoq.contracts import GoalLock, Proposal, Submission
from vetoq.ingestion.contracts import Canonicalization, RepresentationKind
from vetoq.ingestion.errors import (
    IngestionError,
    ProcessingFailure,
    RegistryError,
    malformed_content,
)
from vetoq.ingestion.identity import SubmissionIdentity, source_digest, submission_digest
from vetoq.ingestion.limits import BUDGETS
from vetoq.ingestion.media_types import (
    Charset,
    DeclaredFormat,
    MediaType,
    normalize_media_type,
    stored_media_type,
)
from vetoq.ingestion.registry import new_registry
from vetoq.ingestion.source_text import (
    prepare_source,
    preserved_control_characters,
    validate_source_text,
)
from vetoq.inspection import content_digest

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = UUID("00000000-0000-4000-8000-000000000001")


def test_security_budgets_match_the_frozen_table() -> None:
    assert BUDGETS.goal_bytes == 4_096
    assert BUDGETS.source_bytes == 65_536
    assert BUDGETS.derived_text_bytes == 131_072
    assert BUDGETS.derivation_depth == 2
    assert BUDGETS.base64_matches_per_representation == 16
    assert BUDGETS.json_nesting_depth == 32
    assert BUDGETS.json_members == 2_048
    assert BUDGETS.html_start_tags == 2_000
    assert BUDGETS.html_attributes == 8_000
    assert BUDGETS.derived_representations_per_run == 32
    assert BUDGETS.transform_steps_per_edge == 4
    assert BUDGETS.email_header_bytes == 16_384
    assert BUDGETS.email_mime_parts == 32
    assert BUDGETS.proposal_evidence_ids == 16
    assert BUDGETS.bff_body_bytes == 512 * 1_024
    assert BUDGETS.accepted_runs_per_workspace_per_hour == 30
    assert BUDGETS.originals_per_run == 1
    assert BUDGETS.network_fetches == 0
    assert BUDGETS.archive_decompression == 0
    assert _field_max(Submission, "goal") == BUDGETS.goal_bytes
    assert _field_max(Submission, "source") == BUDGETS.source_bytes
    assert _field_max(Proposal, "evidence_ids") == BUDGETS.proposal_evidence_ids


def test_supported_media_types_canonicalize() -> None:
    declared = normalize_media_type("text/plain; charset=UTF-8")
    assert declared.media_type is MediaType.TEXT_PLAIN
    assert declared.charset is Charset.UTF_8
    assert stored_media_type(declared) == "text/plain"
    assert ";" not in stored_media_type(declared)


@pytest.mark.parametrize(
    ("raw", "media_type"),
    [
        ("TEXT/PLAIN", MediaType.TEXT_PLAIN),
        ("Application/JSON", MediaType.JSON),
        ("text/markdown", MediaType.MARKDOWN),
        ("Text/HTML", MediaType.HTML),
        ("message/RFC822", MediaType.RFC822),
    ],
)
def test_media_type_case_normalizes_to_the_allowlist(raw: str, media_type: MediaType) -> None:
    assert normalize_media_type(raw).media_type is media_type
    assert normalize_media_type(f" {raw} ").media_type is media_type


@pytest.mark.parametrize(
    ("raw", "charset"),
    [
        ("text/plain; charset=utf-8", Charset.UTF_8),
        ("text/plain; charset=UTF-8", Charset.UTF_8),
        ('text/html; charset="us-ascii"', Charset.US_ASCII),
        ("message/rfc822; CHARSET=US-ASCII", Charset.US_ASCII),
    ],
)
def test_supported_charsets_normalize(raw: str, charset: Charset) -> None:
    declared = normalize_media_type(raw)
    assert declared.charset is charset
    assert declared.media_type.value == declared.media_type.value.lower()
    assert ";" not in declared.media_type.value


@pytest.mark.parametrize("raw", ["application/pdf", "image/png", "application/octet-stream"])
def test_unsupported_media_type_is_rejected(raw: str) -> None:
    with pytest.raises(IngestionError, match="unsupported_media_type") as caught:
        normalize_media_type(raw)
    assert caught.value.status == 422


@pytest.mark.parametrize(
    "raw",
    [
        "text/plain; charset=iso-8859-1",
        "text/plain; charset=utf8",
        "text/plain; charset=ascii",
        "text/plain; charset=UTF8",
    ],
)
def test_unsupported_charset_is_rejected(raw: str) -> None:
    with pytest.raises(IngestionError, match="malformed_content") as caught:
        normalize_media_type(raw)
    assert caught.value.status == 422


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "text",
        "text/",
        "/plain",
        "text/plain;",
        "text/plain; charset",
        "text plain",
        "text/plain; charset=",
    ],
)
def test_malformed_media_type_is_rejected(raw: str) -> None:
    with pytest.raises(IngestionError, match="malformed_content"):
        normalize_media_type(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "text/plain; charset=utf-8; charset=utf-8",
        "text/plain; charset=utf-8; charset=us-ascii",
        'text/plain; charset="utf-8"; charset="utf-8"',
    ],
)
def test_duplicate_or_conflicting_charset_is_rejected(raw: str) -> None:
    with pytest.raises(IngestionError, match="malformed_content"):
        normalize_media_type(raw)


def test_parameters_do_not_change_the_stored_media_type() -> None:
    declared = normalize_media_type("text/markdown; charset=utf-8")
    assert stored_media_type(declared) == "text/markdown"
    with pytest.raises(IngestionError, match="malformed_content"):
        normalize_media_type("text/markdown; charset=utf-8; boundary=mixed")


def test_representation_kinds_are_the_schema_values() -> None:
    assert [kind.value for kind in RepresentationKind] == [
        "original",
        "canonical_text",
        "decoded_text",
        "active_content",
    ]
    migration = (API_ROOT / "migrations" / "versions" / "0003_secure_ingestion.py").read_text(
        encoding="utf-8"
    )
    for kind in RepresentationKind:
        assert f"'{kind.value}'" in migration


def test_unknown_registry_key_fails_closed_without_fallback() -> None:
    class Probe:
        def __init__(self, media_type: MediaType) -> None:
            self.media_type = media_type
            self.parser_id = "probe"
            self.parser_version = "1"
            self.validated = 0

        def validate(self, source: str, declaration: DeclaredFormat) -> str:
            self.validated += 1
            return source

        def canonicalize(self, source: str, declaration: DeclaredFormat) -> Canonicalization:
            raise AssertionError("lookup must not canonicalize")

    registry = new_registry()
    plain = Probe(MediaType.TEXT_PLAIN)
    registry.register(plain)
    assert registry.resolve(MediaType.TEXT_PLAIN) is plain
    assert plain.validated == 0
    with pytest.raises(RegistryError, match="adapter_not_implemented"):
        registry.resolve(MediaType.HTML)
    with pytest.raises(RegistryError, match="adapter_not_implemented"):
        registry.resolve_declared("text/html")
    with pytest.raises(IngestionError, match="unsupported_media_type"):
        registry.resolve_declared("image/png")
    with pytest.raises(RegistryError, match="adapter_already_registered"):
        registry.register(plain)
    assert registry.implemented() == frozenset({MediaType.TEXT_PLAIN})
    assert MediaType.HTML in registry.contract_supported()
    assert registry.contract_supported() == frozenset(MediaType)


def test_json_looking_text_does_not_switch_adapter() -> None:
    accepted = prepare_source('{"switch": true}', "text/plain")
    assert accepted.declaration.media_type is MediaType.TEXT_PLAIN
    assert accepted.source == '{"switch": true}'


def test_source_digest_hashes_the_validated_utf8_string() -> None:
    raw = '{"source":"a\\u0041"}'
    parsed = json.loads(raw)["source"]
    plain = json.loads('{"source":"aA"}')["source"]
    expected = hashlib.sha256(b"aA").hexdigest()
    assert parsed == plain == "aA"
    assert source_digest(parsed) == source_digest(plain) == content_digest(parsed) == expected
    assert source_digest(parsed) != hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_normalized_media_type_changes_submission_identity() -> None:
    plain = _identity(normalize_media_type("TEXT/PLAIN").media_type)
    html = _identity(normalize_media_type("text/html").media_type)
    lower = _identity(normalize_media_type("text/plain").media_type)
    assert submission_digest(plain) != submission_digest(html)
    assert submission_digest(plain) == submission_digest(lower)
    assert "parser_version" not in SubmissionIdentity.__dataclass_fields__
    assert "media_type" not in GoalLock.model_fields
    assert "sanitized" not in Submission.model_fields
    assert "template" not in Submission.model_fields
    assert "media_type" in Submission.model_fields


def test_empty_source_is_rejected() -> None:
    for source in ("", " ", "\t\n"):
        with pytest.raises(IngestionError, match="empty_input") as caught:
            validate_source_text(source)
        assert caught.value.status == 422


def test_source_byte_boundary() -> None:
    assert validate_source_text("a" * BUDGETS.source_bytes) == "a" * BUDGETS.source_bytes
    multibyte = "é" * (BUDGETS.source_bytes // 2)
    assert len(multibyte.encode("utf-8")) == BUDGETS.source_bytes
    assert validate_source_text(multibyte) is multibyte
    with pytest.raises(IngestionError, match="input_limit") as caught:
        validate_source_text("a" * (BUDGETS.source_bytes + 1))
    assert caught.value.status == 413


def test_security_errors_omit_the_source_body() -> None:
    sentinel = "SENTINEL-SOURCE-BODY"
    over_limit = sentinel + ("x" * BUDGETS.source_bytes)
    nul = f"before-{sentinel}\x00after"
    for source in (over_limit, nul):
        with pytest.raises(IngestionError) as caught:
            validate_source_text(source)
        assert sentinel not in str(caught.value)
        assert sentinel not in repr(caught.value)
        assert caught.value.args == (caught.value.code,)
    with pytest.raises(IngestionError, match="malformed_content"):
        validate_source_text("caf\u00e9", Charset.US_ASCII)


def test_original_text_and_preserved_controls_stay_exact() -> None:
    original = "keep\u200bme\ufeff"
    accepted = prepare_source(original, "text/html")
    assert accepted.source is original
    assert preserved_control_characters(original) == ("\u200b", "\ufeff")
    assert "\x00" not in "".join(preserved_control_characters("\x00"))


def test_pre_accept_and_processing_codes_stay_separate() -> None:
    failure = ProcessingFailure("parser_limit_exceeded")
    rejection = malformed_content()
    assert not isinstance(failure, IngestionError)
    assert failure.code == "parser_limit_exceeded"
    assert rejection.code == "malformed_content"
    assert rejection.status == 422


def _field_max(model: type[Submission] | type[Proposal], name: str) -> int:
    for item in model.model_fields[name].metadata:
        limit = getattr(item, "max_length", None)
        if isinstance(limit, int):
            return limit
    raise AssertionError(name)


def _identity(media_type: MediaType) -> SubmissionIdentity:
    return SubmissionIdentity(
        workspace_id=WORKSPACE,
        template="support-triage/1",
        goal="help the customer",
        source="same source",
        confirmed=True,
        declared_media_type=media_type,
    )
