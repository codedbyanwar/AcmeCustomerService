"""Task 5 tests: email OTP verification policy."""

import pytest

from conftest import load_module, SALES

_otp_mod = load_module(SALES / "otp" / "verify.py", "otp_verify_test")

OtpSession = _otp_mod.OtpSession
OtpChallenge = _otp_mod.OtpChallenge
mask_email = _otp_mod.mask_email
FIXED_DEMO_PIN = _otp_mod.FIXED_DEMO_PIN
MAX_ATTEMPTS = _otp_mod.MAX_ATTEMPTS
EXPIRY_SECONDS = _otp_mod.EXPIRY_SECONDS


def test_mask_email_format():
    assert mask_email("alice.tan@mailinator.com") == "a***@mailinator.com"
    assert mask_email("bob.lee@mailinator.com") == "b***@mailinator.com"


def test_send_returns_masked_email():
    s = OtpSession()
    res = s.send("alice.tan@mailinator.com")
    assert res["ok"] is True
    assert res["masked_email"] == "a***@mailinator.com"
    assert "a***@mailinator.com" in res["message"]


def test_correct_pin_verifies():
    s = OtpSession()
    s.send("alice.tan@mailinator.com")
    res = s.verify(FIXED_DEMO_PIN)
    assert res["ok"] is True
    assert res["status"] == "verified"


def test_wrong_pin_retries_then_locks():
    s = OtpSession()
    s.send("bob.lee@mailinator.com")
    r1 = s.verify("000000")
    assert r1["ok"] is False and r1["status"] == "mismatch"
    assert r1["attempts_remaining"] == MAX_ATTEMPTS - 1

    r2 = s.verify("111111")
    assert r2["attempts_remaining"] == MAX_ATTEMPTS - 2

    r3 = s.verify("222222")
    # Third wrong attempt exhausts attempts -> locked.
    assert r3["ok"] is False
    assert r3["status"] in ("mismatch", "locked")
    assert r3["attempts_remaining"] == 0

    # Further attempts (even correct) are locked.
    r4 = s.verify(FIXED_DEMO_PIN)
    assert r4["ok"] is False
    assert r4["status"] == "locked"


def test_expiry_blocks_verification():
    c = OtpChallenge(email="alice.tan@mailinator.com", issued_at=1000.0)
    # 5 minutes + 1 second later.
    res = c.verify(FIXED_DEMO_PIN, now=1000.0 + EXPIRY_SECONDS + 1)
    assert res["ok"] is False
    assert res["status"] == "expired"


def test_verify_before_send_has_no_challenge():
    s = OtpSession()
    res = s.verify(FIXED_DEMO_PIN)
    assert res["ok"] is False
    assert res["status"] == "no_challenge"


def test_correct_pin_within_window_passes():
    c = OtpChallenge(email="alice.tan@mailinator.com", issued_at=1000.0)
    res = c.verify(FIXED_DEMO_PIN, now=1000.0 + 60)  # 1 min later
    assert res["ok"] is True
    assert res["status"] == "verified"
