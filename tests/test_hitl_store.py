"""Task 3 tests: pending-approval store + Flask approval console routes."""

import pytest

from conftest import load_module, SALES, APP

_store_mod = load_module(SALES / "hitl" / "store.py", "hitl_store_test")
ApprovalStore = _store_mod.ApprovalStore
STATUS_PENDING = _store_mod.STATUS_PENDING
STATUS_APPROVED = _store_mod.STATUS_APPROVED
STATUS_DENIED = _store_mod.STATUS_DENIED
APPROVER_NAME = _store_mod.APPROVER_NAME


@pytest.fixture
def store(tmp_path):
    return ApprovalStore(tmp_path / "store.json")


def _mk(store, discount=150):
    return store.create_pending(
        customer_id="CUST-A",
        customer_name="Alice Tan",
        device_id="DEV-DUO",
        device_name="iPhone Duo Star White 512GB",
        base_price=999,
        requested_discount=discount,
        reason="loyal customer",
    )


def test_create_pending_is_pending(store):
    rid = _mk(store)
    assert store.get_decision(rid) == STATUS_PENDING
    assert len(store.list_pending()) == 1


def test_approve_transition(store):
    rid = _mk(store)
    rec = store.set_decision(rid, approved=True)
    assert rec["status"] == STATUS_APPROVED
    assert rec["approver"] == APPROVER_NAME
    assert rec["decided_at"] is not None
    assert store.get_decision(rid) == STATUS_APPROVED
    assert store.list_pending() == []


def test_deny_transition(store):
    rid = _mk(store)
    rec = store.set_decision(rid, approved=False)
    assert rec["status"] == STATUS_DENIED
    assert store.get_decision(rid) == STATUS_DENIED


def test_decision_on_missing_request(store):
    assert store.set_decision("nope", approved=True) is None
    assert store.get_decision("nope") is None


def test_pending_ordering(store):
    rid1 = _mk(store, 110)
    rid2 = _mk(store, 200)
    ids = [r["request_id"] for r in store.list_pending()]
    assert ids == [rid1, rid2]


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "shared.json"
    s1 = ApprovalStore(path)
    rid = _mk(s1)
    # A fresh instance (e.g. the console process) sees the same record.
    s2 = ApprovalStore(path)
    assert s2.get_decision(rid) == STATUS_PENDING
    s2.set_decision(rid, approved=True)
    assert s1.get_decision(rid) == STATUS_APPROVED


# --- Flask console routes ---

@pytest.fixture
def console_client(tmp_path, monkeypatch):
    # Point the console's store at a temp file via env before import.
    store_path = tmp_path / "console_store.json"
    monkeypatch.setenv("ACME_HITL_STORE", str(store_path))
    console_mod = load_module(APP / "ApprovalConsole" / "console.py", "console_test")
    console_mod.app.config.update(TESTING=True)
    client = console_mod.app.test_client()
    return client, console_mod.store


def test_console_lists_pending(console_client):
    client, store = console_client
    _mk(store, 150)
    resp = client.get("/console")
    assert resp.status_code == 200
    assert b"Alice Tan" in resp.data
    assert b"150" in resp.data


def test_console_approve_persists_decision(console_client):
    client, store = console_client
    rid = _mk(store, 150)
    resp = client.post("/decide", data={"request_id": rid, "action": "approve"})
    assert resp.status_code == 302  # redirect back to /console
    assert store.get_decision(rid) == STATUS_APPROVED


def test_console_deny_persists_decision(console_client):
    client, store = console_client
    rid = _mk(store, 150)
    client.post("/decide", data={"request_id": rid, "action": "deny"})
    assert store.get_decision(rid) == STATUS_DENIED
