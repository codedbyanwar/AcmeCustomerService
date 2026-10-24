"""Task 9 tests: end-to-end business-logic flow across both agents.

Drives the full journey deterministically (no model): CS handoff intent ->
Sales eligibility -> offer -> manager approval (via shared store) -> OTP ->
order. Also covers denial, OTP-failure, and Bob's upsell variant.
"""

import pytest

from conftest import load_module, CS, SALES

# Load the pieces by path (avoids the dual-`data`-package collision).
_handoff = load_module(CS / "handoff.py", "e2e_handoff")
_sales_logic = load_module(SALES / "sales_logic.py", "e2e_sales_logic")
_store_mod = load_module(SALES / "hitl" / "store.py", "e2e_store")
_otp_mod = load_module(SALES / "otp" / "verify.py", "e2e_otp")

is_recontract_intent = _handoff.is_recontract_intent
eligibility = _sales_logic.eligibility
build_offer = _sales_logic.build_offer
request_manager_approval = _sales_logic.request_manager_approval
AUTO_APPROVE_CAP = _sales_logic.AUTO_APPROVE_CAP
ApprovalStore = _store_mod.ApprovalStore
OtpSession = _otp_mod.OtpSession
FIXED_DEMO_PIN = _otp_mod.FIXED_DEMO_PIN


@pytest.fixture
def store(tmp_path):
    return ApprovalStore(tmp_path / "e2e.json")


class FakeClock:
    def __init__(self, on_tick=None):
        self.t = 0.0
        self.on_tick = on_tick
        self.ticks = 0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        self.ticks += 1
        if self.on_tick:
            self.on_tick(self.ticks)


class _RecordingStore:
    def __init__(self, inner, state):
        self._inner = inner
        self._state = state

    def create_pending(self, **kwargs):
        rid = self._inner.create_pending(**kwargs)
        self._state["rid"] = rid
        return rid

    def get_decision(self, rid):
        return self._inner.get_decision(rid)

    def get(self, rid):
        return self._inner.get(rid)


def test_full_flow_alice_recontract_approved_then_order(store):
    # 1. Customer expresses re-contract intent -> handoff triggers.
    assert is_recontract_intent("I want to re-contract and get a new phone") is True

    # 2. Sales eligibility: Alice is a re-contract candidate.
    elig = eligibility("123456789012")
    assert elig["path"] == "recontract"

    # 3. She wants $150 off the DEV-DUO -> above cap -> manager approval.
    offer = build_offer("DEV-DUO", 150)
    assert offer["requires_approval"] is True

    # 4. Manager (Mr Anwar) approves on the 2nd poll.
    state = {"rid": None}

    def approve(n):
        if n == 2 and state["rid"]:
            store.set_decision(state["rid"], approved=True)

    clock = FakeClock(approve)
    result = request_manager_approval(
        identifier="123456789012", device_id="DEV-DUO", discount=150,
        store=_RecordingStore(store, state), timeout=100, poll_interval=1,
        sleep=clock.sleep, now=clock.now,
    )
    assert result["status"] == "approved"
    final_price = result["offer"]["final_price"]
    assert final_price == 849

    # 5. OTP gate before order.
    otp = OtpSession()
    sent = otp.send("alice.tan@mailinator.com")
    assert sent["masked_email"] == "a***@mailinator.com"
    verified = otp.verify(FIXED_DEMO_PIN)
    assert verified["ok"] is True

    # 6. Order can proceed (verified).
    assert otp.challenge.verified is True


def test_full_flow_denied_falls_back_to_cap(store):
    state = {"rid": None}

    def deny(n):
        if n == 1 and state["rid"]:
            store.set_decision(state["rid"], approved=False)

    clock = FakeClock(deny)
    result = request_manager_approval(
        identifier="123456789012", device_id="DEV-DUO", discount=150,
        store=_RecordingStore(store, state), timeout=100, poll_interval=1,
        sleep=clock.sleep, now=clock.now,
    )
    assert result["status"] == "denied"
    # Best auto-approvable alternative: $100 off -> $899.
    assert "899" in result["message"]


def test_full_flow_otp_failure_blocks_order():
    otp = OtpSession()
    otp.send("alice.tan@mailinator.com")
    for _ in range(3):
        r = otp.verify("000000")
    assert r["ok"] is False
    # Locked / not verified -> order must not proceed.
    assert otp.challenge.verified is False


def test_bob_upsell_path_then_within_cap_order(store):
    # Bob is SIM-only -> upsell path.
    elig = eligibility("98765432")
    assert elig["path"] == "upsell"

    # A $100 discount is within cap -> no manager approval needed.
    offer = build_offer("DEV-PX", 100)
    assert offer["auto_approved"] is True
    assert offer["requires_approval"] is False
    assert offer["final_price"] == 599  # 699 - 100

    # OTP still gates the order.
    otp = OtpSession()
    sent = otp.send("bob.lee@mailinator.com")
    assert sent["masked_email"] == "b***@mailinator.com"
    assert otp.verify(FIXED_DEMO_PIN)["ok"] is True
