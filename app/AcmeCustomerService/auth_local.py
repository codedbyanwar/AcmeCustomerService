"""Caller (JWT) validation for the Customer Service runtime.

This is the security layer: it checks that the invocation carries a bearer
token. Locally the token is a mock, decoded without signature verification
(the deployed CUSTOM_JWT authorizer performs real validation). The Acme
customer is resolved separately in-chat and confirmed by OTP.
"""

import jwt  # PyJWT


def extract_caller(auth_header: str | None) -> dict:
    """Validate the bearer token and return its claims.

    Raises ValueError when no readable bearer token is present.
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing bearer token: an Authorization header is required.")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("Empty bearer token.")
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Unreadable bearer token: {e}") from e
