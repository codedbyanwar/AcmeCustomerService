"""Task 1 tests: Customer Service data + tool logic.

These test the pure data layer (plans, customers) and the tool functions.
Strands @tool wraps functions; we exercise the behavior via the data layer
and via the undecorated logic to keep tests independent of a live model.
"""

import pytest

from conftest import load_module, CS

_plans = load_module(CS / "data" / "plans.py", "cs_plans_test")
_customers = load_module(CS / "data" / "customers.py", "cs_customers_test")

get_plan = _plans.get_plan
format_plan = _plans.format_plan
PLANS = _plans.PLANS
resolve_customer = _customers.resolve_customer
mask_email = _customers.mask_email
CUSTOMERS = _customers.CUSTOMERS


# --- Plan data ---

def test_get_plan_known_case_insensitive():
    assert get_plan("Premium-60")["monthly_fee"] == 60
    assert get_plan("premium-60")["monthly_fee"] == 60
    assert get_plan("  SIM-20 ")["monthly_fee"] == 20


def test_get_plan_unknown():
    assert get_plan("does-not-exist") is None
    assert get_plan("") is None


def test_all_plans_present():
    assert set(PLANS) == {
        "SIM-10", "SIM-20", "SIM-30", "Basic-40", "Premium-60", "Ultimate-80"
    }


def test_format_plan_sim_only_has_no_contract():
    out = format_plan("SIM-20", PLANS["SIM-20"])
    assert "$20/mo" in out
    assert "no contract" in out


def test_format_plan_postpaid_has_contract():
    out = format_plan("Premium-60", PLANS["Premium-60"])
    assert "24-month contract" in out


# --- Customer identification ---

def test_resolve_by_account_number():
    assert resolve_customer("123456789012")["customer_id"] == "CUST-A"
    assert resolve_customer("987654321012")["customer_id"] == "CUST-B"


def test_resolve_by_mobile_number():
    assert resolve_customer("81234567")["customer_id"] == "CUST-A"
    assert resolve_customer("98765432")["customer_id"] == "CUST-B"


def test_resolve_accepts_spaces_and_dashes():
    assert resolve_customer("8123 4567")["customer_id"] == "CUST-A"
    assert resolve_customer("1234-5678-9012")["customer_id"] == "CUST-A"


def test_resolve_unknown_returns_none():
    assert resolve_customer("00000000") is None
    assert resolve_customer("") is None
    assert resolve_customer("not a number") is None


def test_memory_keys_are_stable():
    assert CUSTOMERS["CUST-A"]["memory_key"] == "cust-a-sub"
    assert CUSTOMERS["CUST-B"]["memory_key"] == "cust-b-sub"


# --- Email masking ---

@pytest.mark.parametrize("email,expected", [
    ("alice.tan@mailinator.com", "a***@mailinator.com"),
    ("bob.lee@mailinator.com", "b***@mailinator.com"),
])
def test_mask_email(email, expected):
    assert mask_email(email) == expected


def test_mask_email_handles_malformed():
    assert mask_email("no-at-sign") == "no-at-sign"
