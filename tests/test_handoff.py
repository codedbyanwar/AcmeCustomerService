"""Task 6 tests: CS->Sales handoff intent detection and transport selection."""

import pytest

from conftest import load_module, CS

_handoff = load_module(CS / "handoff.py", "cs_handoff_test")

is_recontract_intent = _handoff.is_recontract_intent
handoff_to_sales = _handoff.handoff_to_sales


@pytest.mark.parametrize("text", [
    "I want to re-contract my line",
    "I'd like to recontract and get a new phone",
    "I want to upgrade my handset",
    "I want to buy a new phone",
    "let's re-contract and get the DEV-DUO",
    "get me a new phone",
    "re-contract my line please",
])
def test_recontract_intent_positive(text):
    assert is_recontract_intent(text) is True


@pytest.mark.parametrize("text", [
    "How much is the Premium plan?",
    "What's my monthly fee?",
    "Can you tell me my data allowance?",
    "",
    "I love my current plan",
    # Questions ABOUT re-contracting -> answered by Customer Service, not a handoff.
    "when can I re-contract?",
    "my mobile number is 98765432. when can I recontract?",
    "how do I upgrade my phone?",
    "am I eligible to renew?",
    "Can I renew my contract?",
    "Do you have a trade-in offer?",
])
def test_recontract_intent_negative(text):
    assert is_recontract_intent(text) is False


def test_handoff_uses_remote_when_arn_set(monkeypatch):
    calls = {}

    def fake_remote(arn, prompt, session_id):
        calls["arn"] = arn
        calls["prompt"] = prompt
        return "REMOTE SALES REPLY"

    monkeypatch.setenv("SALES_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:111:runtime/Sales-x")
    monkeypatch.setattr(_handoff, "_invoke_sales_remote", fake_remote)

    out = handoff_to_sales("I want a new phone", session_id="s" * 40)
    assert out == "REMOTE SALES REPLY"
    assert calls["arn"].endswith("runtime/Sales-x")
    assert "new phone" in calls["prompt"]


def test_handoff_uses_local_when_no_arn(monkeypatch):
    def fake_local(prompt, history=None, session_id=None):
        return (f"LOCAL SALES REPLY: {prompt}", [])

    monkeypatch.delenv("SALES_RUNTIME_ARN", raising=False)
    monkeypatch.setattr(_handoff, "_invoke_sales_local", fake_local)

    out = handoff_to_sales("I want to re-contract")
    assert out.startswith("LOCAL SALES REPLY")
    assert "re-contract" in out


def test_converse_with_sales_returns_history(monkeypatch):
    def fake_local(prompt, history=None, session_id=None):
        new_hist = (history or []) + [{"role": "user", "content": prompt}]
        return (f"reply to {prompt}", new_hist)

    monkeypatch.delenv("SALES_RUNTIME_ARN", raising=False)
    monkeypatch.setattr(_handoff, "_invoke_sales_local", fake_local)

    text, hist = _handoff.converse_with_sales("hello", history=[], session_id="s")
    assert text == "reply to hello"
    assert hist == [{"role": "user", "content": "hello"}]
