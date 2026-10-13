import base64
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from vetoq.auth import issuer_for, principal
from vetoq.config import Settings


def publishable_key(host: str = "clerk.example.com") -> str:
    encoded = base64.urlsafe_b64encode((host + "$").encode()).decode().rstrip("=")
    return "pk_test_" + encoded


def request(origin: str = "http://127.0.0.1:3000") -> MagicMock:
    result = MagicMock()
    result.headers = {"authorization": "Bearer fixture-token"}
    result.app.state.settings = Settings(
        _env_file=None,
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=publishable_key(),
        clerk_origins=["http://127.0.0.1:3000"],
    )
    result.origin = origin
    return result


def test_issuer_is_derived_from_trusted_clerk_configuration() -> None:
    assert issuer_for(publishable_key()) == "https://clerk.example.com"


@pytest.mark.parametrize("key", [None, "invalid", "pk_test_not-base64"])
def test_invalid_clerk_configuration_is_rejected(key: str | None) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        issuer_for(key)


def test_verified_clerk_subject_becomes_principal() -> None:
    key = MagicMock()
    key.key = object()
    with (
        patch("vetoq.auth.key_client") as client,
        patch("vetoq.auth.jwt.decode") as decode,
    ):
        client.return_value.get_signing_key_from_jwt.return_value = key
        decode.return_value = {
            "sub": "user_operator",
            "azp": "http://127.0.0.1:3000",
        }
        assert principal(request()) == "user_operator"
        assert decode.call_args.kwargs["algorithms"] == ["RS256"]
        assert decode.call_args.kwargs["issuer"] == "https://clerk.example.com"


def test_standard_clerk_token_without_azp_is_accepted() -> None:
    key = MagicMock()
    key.key = object()
    with (
        patch("vetoq.auth.key_client") as client,
        patch("vetoq.auth.jwt.decode") as decode,
    ):
        client.return_value.get_signing_key_from_jwt.return_value = key
        decode.return_value = {
            "sub": "user_operator",
        }
        assert principal(request()) == "user_operator"


@pytest.mark.parametrize(
    "azp",
    [
        "https://attacker.invalid",
        # The Clerk Frontend API issuer is not a configured application origin.
        "https://clerk.example.com",
        ["http://127.0.0.1:3000"],
    ],
)
def test_unconfigured_authorized_party_is_rejected(azp: object) -> None:
    with (
        patch("vetoq.auth.key_client") as client,
        patch("vetoq.auth.jwt.decode") as decode,
    ):
        client.return_value.get_signing_key_from_jwt.return_value.key = object()
        decode.return_value = {"sub": "user_operator", "azp": azp}
        with pytest.raises(HTTPException) as error:
            principal(request())
    assert error.value.status_code == 401
    assert error.value.detail == "invalid_session"


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "org_operator"},
        {"sub": "user_operator", "aud": "another-api"},
    ],
)
def test_non_user_or_audience_bound_token_is_rejected(claims: dict[str, str]) -> None:
    with (
        patch("vetoq.auth.key_client") as client,
        patch("vetoq.auth.jwt.decode") as decode,
    ):
        client.return_value.get_signing_key_from_jwt.return_value.key = object()
        decode.return_value = claims
        with pytest.raises(HTTPException) as error:
            principal(request())
    assert error.value.status_code == 401


def test_invalid_signature_is_an_invalid_session_without_logging_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        patch("vetoq.auth.key_client") as client,
        patch("vetoq.auth.jwt.decode", side_effect=jwt.InvalidSignatureError("bad")),
    ):
        client.return_value.get_signing_key_from_jwt.return_value.key = object()
        with pytest.raises(HTTPException) as error:
            principal(request())
    assert error.value.status_code == 401
    assert "fixture-token" not in caplog.text
    assert "InvalidSignatureError" in caplog.text


def test_missing_bearer_token_requires_authentication() -> None:
    unauthenticated = request()
    unauthenticated.headers = {}
    with pytest.raises(HTTPException) as error:
        principal(unauthenticated)
    assert error.value.status_code == 401
    assert error.value.detail == "authentication_required"


def test_missing_clerk_configuration_is_an_outage_not_an_invalid_session() -> None:
    misconfigured = request()
    misconfigured.app.state.settings = Settings(_env_file=None)
    with pytest.raises(HTTPException) as error:
        principal(misconfigured)
    assert error.value.status_code == 503
    assert error.value.detail == "identity_not_configured"


def test_unreachable_signing_keys_are_an_outage_not_an_invalid_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch("vetoq.auth.key_client") as client:
        client.return_value.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientConnectionError(
            "Fail to fetch data from the url, err: private"
        )
        with pytest.raises(HTTPException) as error:
            principal(request())
    assert error.value.status_code == 503
    assert error.value.detail == "identity_unavailable"
    assert "private" not in caplog.text
    assert "fixture-token" not in caplog.text
