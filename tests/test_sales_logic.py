"""Task 2 tests: Sales device data, discount boundary, and eligibility."""

import pytest

from conftest import load_module, SALES

_devices = load_module(SALES / "data" / "devices.py", "sales_devices_test")
_sales_logic = load_module(SALES / "sales_logic.py", "sales_logic_test")

DEVICES = _devices.DEVICES
get_device = _devices.get_device
discount_decision = _devices.discount_decision
AUTO_APPROVE_CAP = _devices.AUTO_APPROVE_CAP
build_offer = _sales_logic.build_offer
eligibility = _sales_logic.eligibility
UPSELL_PLAN_ID = _sales_logic.UPSELL_PLAN_ID


# --- Device data ---

def test_devices_present():
    assert set(DEVICES) == {"DEV-DUO", "DEV-PX", "DEV-GS", "DEV-LT"}
    assert DEVICES["DEV-DUO"]["upfront"] == 999
    assert DEVICES["DEV-DUO"]["name"] == "iPhone Duo Star White 512GB"


def test_get_device_case_insensitive():
    assert get_device("dev-duo")["upfront"] == 999
    assert get_device("unknown") is None


# --- Discount boundary ---

@pytest.mark.parametrize("amount", [0, 1, 50, 99.99, 100])
def test_discount_at_or_below_cap_auto_approved(amount):
    d = discount_decision(amount)
    assert d["auto_approved"] is True
    assert d["requires_approval"] is False


@pytest.mark.parametrize("amount", [100.01, 101, 150, 500])
def test_discount_above_cap_requires_approval(amount):
    d = discount_decision(amount)
    assert d["auto_approved"] is False
    assert d["requires_approval"] is True


def test_cap_is_100():
    assert AUTO_APPROVE_CAP == 100


def test_negative_discount_treated_as_zero():
    d = discount_decision(-25)
    assert d["discount"] == 0.0
    assert d["auto_approved"] is True


# --- Offer building ---

def test_build_offer_auto_approved_price():
    offer = build_offer("DEV-DUO", 75)
    assert offer["ok"] is True
    assert offer["upfront"] == 999
    assert offer["discount"] == 75
    assert offer["final_price"] == 924
    assert offer["auto_approved"] is True
    assert "approved" in offer["message"].lower()


def test_build_offer_requires_approval_above_cap():
    offer = build_offer("DEV-DUO", 150)
    assert offer["ok"] is True
    assert offer["requires_approval"] is True
    assert offer["final_price"] == 849
    assert "manager approval" in offer["message"].lower()


def test_build_offer_unknown_device():
    offer = build_offer("DEV-NOPE", 10)
    assert offer["ok"] is False
    assert "unknown device" in offer["message"].lower()


# --- Eligibility ---

def test_eligibility_alice_recontract():
    res = eligibility("123456789012")  # Alice, account number
    assert res["found"] is True
    assert res["path"] == "recontract"
    assert "Alice" in res["message"]


def test_eligibility_bob_upsell():
    res = eligibility("98765432")  # Bob, mobile number
    assert res["found"] is True
    assert res["path"] == "upsell"
    assert UPSELL_PLAN_ID in res["message"]


def test_eligibility_unknown_customer():
    res = eligibility("00000000")
    assert res["found"] is False
    assert res["path"] is None
