"""Mock JWT helper for the local prototype ($0, no Cognito).

The JWT here is the CALLER/SESSION identity — it authorizes the runtime
invocation (the security layer). It is NOT the Acme customer identity; the
customer (Alice/Bob) is resolved in-chat by mobile/account number and confirmed
by OTP.

Locally we mint an unsigned token for a single "web app" principal and decode
it with verify_signature=False (matching the reference pattern). In production,
the real Cognito CUSTOM_JWT config in agentcore.json validates genuinely signed
tokens instead; no code change is needed on the reading side.
"""

from __future__ import annotations

import time

import jwt  # PyJWT

# A fixed principal representing the Acme web app calling the runtime.
WEBAPP_SUBJECT = "acme-webapp-client"
WEBAPP_CLIENT_ID = "acme-local-webapp"


def mint_webapp_token(ttl_seconds: int = 3600) -> str:
    """Mint an unsigned mock JWT for the web app principal (local use only)."""
    now = int(time.time())
    claims = {
        "sub": WEBAPP_SUBJECT,
        "client_id": WEBAPP_CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": "acme-local-mock",
    }
    # Unsigned token (alg=none). Decoded locally with verify_signature=False.
    return jwt.encode(claims, key="", algorithm="none")


def extract_caller(auth_header: str | None) -> dict:
    """Validate the bearer token and return its claims.

    Locally this decodes without verifying the signature (the deployed runtime's
    CUSTOM_JWT authorizer performs real validation). Raises ValueError if no
    bearer token is present or the token is unreadable.
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing bearer token: an Authorization header is required.")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("Empty bearer token.")
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as e:  # noqa: BLE001 - surface a clean auth error
        raise ValueError(f"Unreadable bearer token: {e}") from e
    return claims
