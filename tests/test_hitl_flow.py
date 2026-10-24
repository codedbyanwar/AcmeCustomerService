"""Task 4 tests: blocking manager-approval flow (request_manager_approval).

Uses injected store/sleep/clock so the blocking poll loop runs instantly and
deterministically — no real waiting.
"""

import pytest

from conftest import load_module, SALES

_store_mod = load_module(SALES / "hitl" / "store.py", "hitl_store_flow_test")
_sales_logic = load_module(SALES / "sales_logic.py", "sales_logic_flow_test")

ApprovalStore = _store_mod.ApprovalStore
request_manager_approval = _sales_logic.request_manager_approval
AUTO_APPROVE_CAP = _sales_logic.AUTO_APPROVE_CAP


@pytest.fixture
def store(tmp_path):
    return ApprovalStore(tmp_path / "flow.json")


class FakeClock:
    """Monotonic clock whose sleep() advances time and can trigger a callback."""

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


def test_approval_resumes_with_approved_quote(store):
    # Manager approves on the 2nd poll.
    state = {"rid": None}

    def on_tick(n):
        if n == 2 and state["rid"]:
            store.set_decision(state["rid"], approved=True)

    clock = FakeClock(on_tick)

    # Pre-create so the callback can find the id: instead, capture via store.
    result = request_manager_approval(
        identifier="123456789012",  # Alice
        device_id="DEV-DUO",
        discount=150,
        reason="loyalty",
        store=_RecordingStore(store, state),
        timeout=100,
        poll_interval=1,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert result["status"] == "approved"
    assert result["offer"]["final_price"] == 849  # 999 - 150
    assert "Mr Anwar" in result["message"]
    assert "849" in result["message"]


def test_denial_offers_best_alternative(store):
    state = {"rid": None}

    def on_tick(n):
        if n == 1 and state["rid"]:
            store.set_decision(state["rid"], approved=False)

    clock = FakeClock(on_tick)
    result = request_manager_approval(
        identifier="123456789012",
        device_id="DEV-DUO",
        discount=150,
        store=_RecordingStore(store, state),
        timeout=100,
        poll_interval=1,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert result["status"] == "denied"
    # Best auto-approvable alternative: $100 off -> 899.
    assert "899" in result["message"]
    assert str(AUTO_APPROVE_CAP) in result["message"]


def test_timeout_when_no_decision(store):
    clock = FakeClock()
    result = request_manager_approval(
        identifier="123456789012",
        device_id="DEV-DUO",
        discount=150,
        store=store,
        timeout=5,
        poll_interval=1,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert result["status"] == "timeout"
    assert result["request_id"] is not None


def test_within_cap_does_not_escalate(store):
    result = request_manager_approval(
        identifier="123456789012",
        device_id="DEV-DUO",
        discount=50,
        store=store,
    )
    assert result["status"] == "approved"
    assert result["request_id"] is None  # no pending record created


def test_unknown_customer_errors(store):
    result = request_manager_approval(
        identifier="00000000",
        device_id="DEV-DUO",
        discount=150,
        store=store,
    )
    assert result["status"] == "error"


class _RecordingStore:
    """Wraps a store to capture the created request id into shared state."""

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
