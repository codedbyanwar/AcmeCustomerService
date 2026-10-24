"""Sales agent tools (Strands @tool wrappers over sales_logic)."""

from strands import tool

from sales_logic import (
    DEVICES,
    eligibility,
    build_offer,
    request_manager_approval,
    resolve_customer,
    UPSELL_PLAN_ID,
)
from otp.verify import OtpSession, PersistentOtpSession

# OTP session. Keyed by conversation/session id and persisted to a local store
# so it survives across separate Sales subprocess turns in local dev. Falls back
# to an in-memory session when no session id is set (e.g. deployed runtime, which
# keeps a single warm agent per session, or unit tests).
_SESSION_ID = None
_otp = OtpSession()


def set_otp_session(session_id):
    """Bind OTP to a persistent, session-keyed store (local multi-turn handoff)."""
    global _SESSION_ID, _otp
    _SESSION_ID = session_id
    _otp = PersistentOtpSession(session_id) if session_id else OtpSession()


@tool
def check_recontract_eligibility(identifier: str) -> str:
    """Check whether a customer can re-contract (or should be upsold) for a new device.

    Args:
        identifier: The customer's 12-digit account number or 8-digit mobile number.

    Returns:
        A message describing the re-contract or upsell path.
    """
    result = eligibility(identifier)
    return result["message"]


@tool
def list_devices() -> str:
    """List the devices available for re-contract or upsell, with upfront prices.

    Returns:
        A formatted list of devices and their upfront cost.
    """
    lines = [
        f"{did} — {d['name']}: upfront ${d['upfront']}"
        for did, d in DEVICES.items()
    ]
    return "Available devices:\n" + "\n".join(lines)


@tool
def quote_device_offer(device_id: str, discount: float = 0) -> str:
    """Quote a device offer with an optional discount off the upfront cost.

    A discount of up to $100 is auto-approved and confirmed immediately. A
    discount above $100 is auto-approved only up to $100; use
    `request_additional_discount` to escalate the extra amount to the manager.

    Args:
        device_id: Device identifier, e.g. 'DEV-DUO', 'DEV-PX'.
        discount: Requested discount in dollars off the upfront cost (default 0).

    Returns:
        The offer details, or a note that manager approval is required.
    """
    offer = build_offer(device_id, discount)
    if not offer["ok"]:
        return offer["message"]
    if offer["requires_approval"]:
        return (
            offer["message"]
            + " Let me check with my manager for the additional discount — "
            "call request_additional_discount to escalate it."
        )
    return offer["message"]


@tool
def request_additional_discount(
    identifier: str,
    device_id: str,
    discount: float,
    reason: str = "",
    competitor_price: float = 0,
    competitor_monthly: float = 0,
) -> str:
    """Escalate a device discount above $100 to the sales manager for approval.

    Tell the customer you're checking with your manager, then call this. It
    blocks until the manager (Mr Anwar) approves or denies in the console, and
    returns the outcome so you can confirm the final price to the customer.

    Pass the competitor's offer (if the customer cited one) so the manager sees
    the justification on the approval console.

    Args:
        identifier: The customer's 12-digit account number or 8-digit mobile number.
        device_id: Device identifier, e.g. 'DEV-DUO'.
        discount: The total requested discount in dollars the customer wants (e.g. 200).
        reason: Optional short justification shown to the manager.
        competitor_price: Competitor's device price, if cited (e.g. 799). 0 if none.
        competitor_monthly: Competitor's monthly fee, if cited (e.g. 60). 0 if none.

    Returns:
        A customer-facing message describing the manager's decision.
    """
    justification = reason.strip()
    if competitor_price or competitor_monthly:
        parts = []
        if competitor_price:
            parts.append(f"device ${competitor_price:.0f}")
        if competitor_monthly:
            parts.append(f"${competitor_monthly:.0f}/mo")
        comp = "competitor offers " + " + ".join(parts)
        justification = f"{justification} ({comp})".strip() if justification else comp

    result = request_manager_approval(
        identifier=identifier,
        device_id=device_id,
        discount=discount,
        reason=justification,
    )
    return result["message"]


@tool
def send_otp(identifier: str) -> str:
    """Send a one-time verification code to the customer's email on file.

    Call this only AFTER the final price is settled (including any manager
    approval) and BEFORE processing the order. The code is sent to the email
    on the customer's account and shown masked.

    Args:
        identifier: The customer's 12-digit account number or 8-digit mobile number.

    Returns:
        A message confirming the code was sent to the masked email.
    """
    cust = resolve_customer(identifier)
    if not cust:
        return (
            "I couldn't find that account to send a verification code. "
            "Please confirm your account or mobile number."
        )
    result = _otp.send(cust["email"])
    return result["message"]


@tool
def verify_otp(pin: str) -> str:
    """Verify the one-time code the customer entered.

    Must be preceded by `send_otp`. Enforces up to 3 attempts and a 5-minute
    expiry. On success, you may process the order.

    Args:
        pin: The 6-digit code the customer provided.

    Returns:
        A message indicating whether verification succeeded, with attempts left.
    """
    result = _otp.verify(pin)
    return result["message"]


@tool
def process_order(identifier: str, device_id: str, final_price: float) -> str:
    """Finalize and confirm the device order AFTER successful OTP verification.

    Do not call this unless `verify_otp` has succeeded for this customer.

    Args:
        identifier: The customer's 12-digit account number or 8-digit mobile number.
        device_id: Device identifier being ordered, e.g. 'DEV-DUO'.
        final_price: The agreed upfront price after discount.

    Returns:
        An order confirmation message, or a note that verification is required.
    """
    challenge = _otp.challenge
    if challenge is None or not challenge.verified:
        return (
            "I can't process the order yet — I need to verify your identity "
            "with the code first."
        )
    cust = resolve_customer(identifier)
    name = cust["name"] if cust else "there"
    device = DEVICES.get(device_id, {}).get("name", device_id)
    return (
        f"All set, {name}! Your order for the {device} is confirmed at "
        f"${final_price:.0f} upfront, charged to your next bill. "
        "A confirmation email is on its way. Thanks for choosing Acme Telco."
    )


# Reset helper for a fresh conversation/test (in-memory session).
def reset_otp():
    global _otp, _SESSION_ID
    _SESSION_ID = None
    _otp = OtpSession()


# Expose the upsell target for prompt/reference use.
DEFAULT_UPSELL_PLAN = UPSELL_PLAN_ID
