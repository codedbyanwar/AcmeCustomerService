"""Email OTP verification for the Sales agent (prototype).

Identity is confirmed by a one-time PIN before an order is processed. For this
local prototype the PIN is a fixed demo value (no real email delivery); the
retry/expiry/masking policy still applies to the verify step.

Policy:
  - 6-digit numeric PIN (fixed demo value 123456)
  - up to 3 verification attempts
  - 5-minute expiry from issue
  - email shown masked (a***@mailinator.com)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

FIXED_DEMO_PIN = "123456"
PIN_LENGTH = 6
MAX_ATTEMPTS = 3
EXPIRY_SECONDS = 5 * 60  # 5 minutes


def mask_email(email: str) -> str:
    """Mask an email for display, e.g. alice.tan@mailinator.com -> a***@mailinator.com."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    first = local[0] if local else ""
    return f"{first}***@{domain}"


@dataclass
class OtpChallenge:
    """A single OTP challenge issued to an email, with attempt/expiry tracking."""

    email: str
    pin: str = FIXED_DEMO_PIN
    issued_at: float = field(default_factory=time.time)
    attempts: int = 0
    verified: bool = False
    expiry_seconds: float = EXPIRY_SECONDS
    max_attempts: int = MAX_ATTEMPTS

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.issued_at) > self.expiry_seconds

    def attempts_remaining(self) -> int:
        return max(0, self.max_attempts - self.attempts)

    def verify(self, pin: str, now: Optional[float] = None) -> dict:
        """Check a submitted PIN against policy.

        Returns a dict:
          {"ok": bool, "status": "verified"|"expired"|"locked"|"mismatch",
           "attempts_remaining": int, "message": str}
        """
        now = time.time() if now is None else now

        if self.verified:
            return {"ok": True, "status": "verified", "attempts_remaining": self.attempts_remaining(),
                    "message": "Already verified."}

        if self.is_expired(now):
            return {"ok": False, "status": "expired", "attempts_remaining": 0,
                    "message": "The verification code has expired. Please request a new code."}

        if self.attempts_remaining() <= 0:
            return {"ok": False, "status": "locked", "attempts_remaining": 0,
                    "message": "Too many incorrect attempts. Verification is locked."}

        self.attempts += 1
        submitted = (pin or "").strip()

        if submitted == self.pin:
            self.verified = True
            return {"ok": True, "status": "verified", "attempts_remaining": self.attempts_remaining(),
                    "message": "Identity verified."}

        remaining = self.attempts_remaining()
        if remaining <= 0:
            return {"ok": False, "status": "locked", "attempts_remaining": 0,
                    "message": "Incorrect code. Too many attempts — verification is locked."}
        return {"ok": False, "status": "mismatch", "attempts_remaining": remaining,
                "message": f"Incorrect code. {remaining} attempt(s) remaining."}


class OtpSession:
    """Holds the active OTP challenge for a single conversation/session (in-memory)."""

    def __init__(self):
        self._challenge: Optional[OtpChallenge] = None

    def send(self, email: str) -> dict:
        """Issue a new OTP challenge for an email. Returns a masked-email message."""
        self._challenge = OtpChallenge(email=email)
        return {
            "ok": True,
            "masked_email": mask_email(email),
            "message": (
                f"I've sent a 6-digit verification code to {mask_email(email)}. "
                "Please enter it to confirm your order."
            ),
        }

    def verify(self, pin: str, now: Optional[float] = None) -> dict:
        if self._challenge is None:
            return {"ok": False, "status": "no_challenge", "attempts_remaining": 0,
                    "message": "No verification is in progress. I'll send you a code first."}
        return self._challenge.verify(pin, now=now)

    @property
    def challenge(self) -> Optional[OtpChallenge]:
        return self._challenge


# --- persistent, session-keyed OTP (survives across subprocess turns) ---

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

_OTP_STORE = Path(
    os.environ.get("ACME_OTP_STORE", str(Path(tempfile.gettempdir()) / "acme_otp_store.json"))
)


def _otp_read() -> dict:
    try:
        return json.loads(_OTP_STORE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _otp_write(data: dict) -> None:
    _OTP_STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_OTP_STORE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, _OTP_STORE)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class PersistentOtpSession:
    """Session-keyed OTP backed by a JSON file.

    Lets send_otp/verify_otp survive across separate Sales subprocess turns (the
    local handoff spawns a fresh interpreter per turn, so an in-memory challenge
    would be lost). Keyed by the conversation/session id.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id or "default"

    def _load(self) -> Optional[OtpChallenge]:
        rec = _otp_read().get(self.session_id)
        if not rec:
            return None
        return OtpChallenge(
            email=rec["email"],
            pin=rec.get("pin", FIXED_DEMO_PIN),
            issued_at=rec.get("issued_at", time.time()),
            attempts=rec.get("attempts", 0),
            verified=rec.get("verified", False),
        )

    def _save(self, ch: OtpChallenge) -> None:
        data = _otp_read()
        data[self.session_id] = {
            "email": ch.email,
            "pin": ch.pin,
            "issued_at": ch.issued_at,
            "attempts": ch.attempts,
            "verified": ch.verified,
        }
        _otp_write(data)

    def send(self, email: str) -> dict:
        ch = OtpChallenge(email=email)
        self._save(ch)
        return {
            "ok": True,
            "masked_email": mask_email(email),
            "message": (
                f"I've sent a 6-digit verification code to {mask_email(email)}. "
                "Please enter it to confirm your order."
            ),
        }

    def verify(self, pin: str, now: Optional[float] = None) -> dict:
        ch = self._load()
        if ch is None:
            return {"ok": False, "status": "no_challenge", "attempts_remaining": 0,
                    "message": "No verification is in progress. I'll send you a code first."}
        result = ch.verify(pin, now=now)
        self._save(ch)  # persist updated attempts/verified
        return result

    @property
    def challenge(self) -> Optional[OtpChallenge]:
        return self._load()
