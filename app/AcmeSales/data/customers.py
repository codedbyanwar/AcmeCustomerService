"""Acme Telco seed customers for the prototype.

Two customers:
  - Alice Tan (CUST-A): postpaid Premium-60 with an active device contract, re-contract eligible.
  - Bob Lee  (CUST-B): SIM-only SIM-20, no device/contract, an upsell candidate.

A customer is identified in-chat by either a 12-digit account number or an
8-digit Singapore mobile number. The `memory_key` is the stable identity used
to key AgentCore Memory (analogous to a Cognito `sub`).
"""

CUSTOMERS = {
    "CUST-A": {
        "customer_id": "CUST-A",
        "memory_key": "cust-a-sub",
        "name": "Alice Tan",
        "account_number": "123456789012",
        "mobile": "81234567",
        "email": "alice.tan@mailinator.com",
        "plan_id": "Premium-60",
        "device": "iPhone 16",
        "contract": {
            "start": "2024-09-01",
            "end": "2026-08-31",
            "months": 24,
        },
        "recontract_eligible": True,
    },
    "CUST-B": {
        "customer_id": "CUST-B",
        "memory_key": "cust-b-sub",
        "name": "Bob Lee",
        "account_number": "987654321012",
        "mobile": "98765432",
        "email": "bob.lee@mailinator.com",
        "plan_id": "SIM-20",
        "device": None,
        "contract": None,
        "recontract_eligible": False,
    },
}


def _normalize(identifier: str) -> str:
    """Strip spaces/dashes so '8123 4567' and '81234567' match."""
    return "".join(ch for ch in (identifier or "") if ch.isdigit())


def resolve_customer(identifier: str) -> dict | None:
    """Resolve a customer by account number (12 digits) or mobile (8 digits).

    Returns the customer dict, or None if the identifier matches no one.
    Accepts values with spaces or dashes.
    """
    digits = _normalize(identifier)
    if not digits:
        return None
    for cust in CUSTOMERS.values():
        if digits == cust["account_number"] or digits == cust["mobile"]:
            return cust
    return None


def mask_email(email: str) -> str:
    """Mask an email for display, e.g. alice.tan@mailinator.com -> a***@mailinator.com."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    first = local[0] if local else ""
    return f"{first}***@{domain}"
