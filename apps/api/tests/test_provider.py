import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx2
import pytest
from pydantic import SecretStr

from vetoq.config import Settings
from vetoq.contracts import GoalLock
from vetoq.providers.base import InferenceRequest, ProviderError
from vetoq.providers.groq import GroqProvider

SOURCE = UUID("00000000-0000-4000-8000-000000000001")
WORKSPACE = UUID("00000000-0000-4000-8000-00000000000a")


def request() -> InferenceRequest:
    envelope = GoalLock(
        principal="user_operator",
        workspace_id=WORKSPACE,
        source_id=SOURCE,
        source_digest="a" * 64,
        goal="Create a ticket.",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    return InferenceRequest(envelope, {str(SOURCE): "Synthetic customer cannot sign in."})


def provider() -> GroqProvider:
    settings = Settings(
        _env_file=None,
        groq_api_key=SecretStr("fixture-key"),
        model_timeout=1,
    )
    return GroqProvider(settings)


def response(content: object, status: int = 200) -> MagicMock:
    result = MagicMock()
    result.status_code = status
    result.content = b"{}"
    result.json.return_value = {
        "id": "fixture-request",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
    }
    return result


def valid_analysis() -> dict[str, object]:
    return {
        "findings": [],
        "uncertain": False,
        "summary": "A routine synthetic support request.",
        "proposal": {
            "tool": "tickets.create",
            "tool_version": 1,
            "arguments": {
                "workspace_id": str(WORKSPACE),
                "title": "Cannot sign in",
                "body": "Synthetic customer cannot sign in.",
            },
            "evidence_ids": [str(SOURCE)],
        },
    }


def test_valid_structured_output_crosses_provider_boundary() -> None:
    with patch("vetoq.providers.groq.httpx2.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = response(valid_analysis())
        result = provider().analyze(request())
    assert result.provider == "groq"
    assert result.analysis.proposal is not None
    payload = client.return_value.__enter__.return_value.post.call_args.kwargs["json"]
    assert payload["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize("content", [{}, {"findings": [], "uncertain": False}])
def test_malformed_model_output_fails_closed(content: object) -> None:
    with patch("vetoq.providers.groq.httpx2.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = response(content)
        with pytest.raises(ProviderError, match="provider_invalid_output"):
            provider().analyze(request())


def test_timeout_is_retryable_and_secret_is_not_in_error() -> None:
    with patch("vetoq.providers.groq.httpx2.Client") as client:
        client.return_value.__enter__.return_value.post.side_effect = httpx2.TimeoutException(
            "fixture"
        )
        with pytest.raises(ProviderError) as error:
            provider().analyze(request())
    assert error.value.code == "provider_timeout"
    assert error.value.retryable
    assert "fixture-key" not in str(error.value)


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, "provider_rate_limited", True),
        (503, "provider_unavailable", True),
        (400, "provider_request_rejected", False),
    ],
)
def test_provider_http_failures_are_safely_classified(
    status: int, code: str, retryable: bool
) -> None:
    with patch("vetoq.providers.groq.httpx2.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = response({}, status)
        with pytest.raises(ProviderError) as error:
            provider().analyze(request())
    assert error.value.code == code
    assert error.value.retryable is retryable


def test_invalid_evidence_reference_is_rejected() -> None:
    body = valid_analysis()
    proposal = body["proposal"]
    assert isinstance(proposal, dict)
    proposal["evidence_ids"] = ["00000000-0000-4000-8000-000000000099"]
    with patch("vetoq.providers.groq.httpx2.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = response(body)
        with pytest.raises(ProviderError, match="provider_invalid_evidence"):
            provider().analyze(request())
