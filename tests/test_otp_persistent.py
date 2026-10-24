"""Tests for PersistentOtpSession: survives across 'turns' (fresh instances)."""

import sys

import pytest

from conftest import load_module, SALES

_otp_mod = load_module(SALES / "otp" / "verify.py", "otp_persist_test")
PersistentOtpSession = _otp_mod.PersistentOtpSession
FIXED_DEMO_PIN = _otp_mod.FIXED_DEMO_PIN


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ACME_OTP_STORE", str(tmp_path / "otp.json"))
    # Re-point the module-level store path at the temp file.
    import importlib
    from pathlib import Path
    _otp_mod._OTP_STORE = Path(str(tmp_path / "otp.json"))
    yield


def test_send_then_verify_across_instances():
    # Turn 1: send (one instance).
    s1 = PersistentOtpSession("sess-A")
    res = s1.send("alice.tan@mailinator.com")
    assert res["masked_email"] == "a***@mailinator.com"

    # Turn 2: a brand-new instance (simulates a fresh subprocess) verifies.
    s2 = PersistentOtpSession("sess-A")
    out = s2.verify(FIXED_DEMO_PIN)
    assert out["ok"] is True
    assert out["status"] == "verified"


def test_attempts_persist_across_instances():
    PersistentOtpSession("sess-B").send("bob.lee@mailinator.com")
    r1 = PersistentOtpSession("sess-B").verify("000000")
    assert r1["status"] == "mismatch"
    r2 = PersistentOtpSession("sess-B").verify("111111")
    # Second wrong attempt across a new instance -> attempts accumulated.
    assert r2["attempts_remaining"] == 1


def test_sessions_are_isolated():
    PersistentOtpSession("sess-C").send("alice.tan@mailinator.com")
    # A different session has no challenge.
    out = PersistentOtpSession("sess-D").verify(FIXED_DEMO_PIN)
    assert out["ok"] is False
    assert out["status"] == "no_challenge"


def test_verify_before_send_no_challenge():
    out = PersistentOtpSession("sess-E").verify(FIXED_DEMO_PIN)
    assert out["status"] == "no_challenge"
