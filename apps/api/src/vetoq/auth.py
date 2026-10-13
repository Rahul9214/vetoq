"""Clerk-signed bearer session verification. Membership is checked separately."""

import base64
import logging
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request

from vetoq.config import Settings

logger = logging.getLogger("vetoq.auth")


def issuer_for(key: str | None) -> str:
    if key is None or not key.startswith(("pk_test_", "pk_live_")):
        raise ValueError("clerk_not_configured")
    encoded = key.split("_", 2)[2]
    host = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode().rstrip("$")
    url = urlsplit("https://" + host)
    if url.hostname != host or url.path or url.query or url.fragment or url.port is not None:
        raise ValueError("invalid_clerk_instance")
    return "https://" + host


@lru_cache(maxsize=4)
def key_client(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(issuer + "/.well-known/jwks.json", timeout=5, lifespan=300)


def correlation(request: Request) -> str:
    if not hasattr(request.state, "correlation_id"):
        request.state.correlation_id = str(uuid4())
    return str(request.state.correlation_id)


def principal(request: Request) -> str:
    settings: Settings = request.app.state.settings
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 8192:
        raise HTTPException(401, "authentication_required", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:]
    try:
        issuer = issuer_for(settings.clerk_publishable_key)
    except (ValueError, UnicodeError):
        logger.error("Clerk verification is not configured correlation_id=%s", correlation(request))
        raise HTTPException(503, "identity_not_configured") from None
    try:
        key = key_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "nbf", "iat", "iss", "sub"], "verify_aud": False},
            leeway=5,
        )
        azp = claims.get("azp")
        if azp is not None and (not isinstance(azp, str) or azp not in settings.clerk_origins):
            raise ValueError("invalid_authorized_party")
        if not isinstance(claims.get("sub"), str) or not claims["sub"].startswith("user_"):
            raise ValueError("invalid_identity")
        # Clerk session tokens do not have an audience by default. Never accept a
        # different token class with an unexpected audience.
        if claims.get("aud") is not None:
            raise ValueError("unexpected_audience")
        return str(claims["sub"])
    except jwt.PyJWKClientConnectionError as err:
        logger.error(
            "Clerk signing keys unavailable: %s correlation_id=%s",
            type(err).__name__,
            correlation(request),
        )
        raise HTTPException(503, "identity_unavailable") from None
    except (jwt.PyJWTError, ValueError, UnicodeError) as err:
        reason = err.args[0] if isinstance(err, ValueError) and err.args else type(err).__name__
        logger.warning(
            "Token verification failed: %s correlation_id=%s",
            str(reason)[:80],
            correlation(request),
        )
        raise HTTPException(
            401, "invalid_session", headers={"WWW-Authenticate": "Bearer"}
        ) from None
