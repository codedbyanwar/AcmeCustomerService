"""Task 8 tests: Acme landing page + chat front end routes and auth plumbing."""

import sys

import pytest

from conftest import load_module, CS, APP


@pytest.fixture
def client(monkeypatch):
    # Ensure imports resolve: CS dir (for `main`, `auth_local`) and app/ (for `auth`).
    sys.path.insert(0, str(CS))
    sys.path.insert(0, str(APP))
    fe = load_module(CS / "frontend" / "frontend.py", "cs_frontend_test")

    # Replace the CS agent with a fake that streams without calling Bedrock.
    class _FakeAgent:
        async def stream_async(self, prompt):
            yield {"data": "Hello from Acme. "}
            yield {"data": f"You said: {prompt}"}

    monkeypatch.setattr(fe, "_get_cs_agent", lambda: _FakeAgent())
    fe.app.config.update(TESTING=True)
    client = fe.app.test_client()
    client._fe = fe  # expose module for tests that need to patch handoff
    return client


def test_landing_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Welcome to Acme Customer Service Portal" in resp.data
    assert b"Start chat" in resp.data


def test_chat_page_renders_and_prompts_identification(client):
    resp = client.get("/chat")
    assert resp.status_code == 200
    # The UI nudges the customer to share account/mobile number.
    assert b"account or mobile number" in resp.data


def test_api_chat_streams_reply_with_token_attached(client):
    resp = client.post("/api/chat", json={"prompt": "How much is Premium-60?"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Hello from Acme" in body
    assert "Premium-60" in body


def test_api_chat_rejects_empty_prompt(client):
    resp = client.post("/api/chat", json={"prompt": "   "})
    assert resp.status_code == 400


def test_api_chat_rejects_bad_bearer(client):
    resp = client.post(
        "/api/chat",
        json={"prompt": "hi"},
        headers={"Authorization": "Basic nope"},
    )
    assert resp.status_code == 401


def test_handoff_transition_line_on_recontract(client, monkeypatch):
    """First re-contract message shows a 'connecting you with Sales' line."""
    fe = client._fe
    import handoff as _handoff

    monkeypatch.setattr(
        _handoff, "converse_with_sales",
        lambda prompt, history=None, session_id=None: ("Here's your quote: $999", []),
    )
    resp = client.post("/api/chat", json={"prompt": "I want to re-contract and get a new phone"})
    body = resp.get_data(as_text=True)
    assert "Sales specialist" in body
    assert "$999" in body


def test_manager_wait_line_mid_negotiation(client, monkeypatch):
    """Once negotiation is underway, naming a number shows a 'checking with my manager' beat."""
    fe = client._fe
    import handoff as _handoff

    # Seed an active Sales session with enough history to look mid-negotiation.
    sid = "sess-neg"
    fe._sales_sessions[sid] = {"active": True, "history": [1, 2, 3, 4]}

    monkeypatch.setattr(
        _handoff, "converse_with_sales",
        lambda prompt, history=None, session_id=None: ("Mr Anwar approved $200. You pay $799.", []),
    )
    client.set_cookie("acme_session", sid)
    resp = client.post("/api/chat", json={"prompt": "$200 would close it"})
    body = resp.get_data(as_text=True)
    assert "manager" in body.lower()
    assert "Mr Anwar approved" in body


def test_closing_number_heuristic(client):
    """Only a short, single-amount message counts as a closing offer."""
    fe = client._fe
    f = fe._looks_like_closing_number
    # Concrete closing offers -> True
    assert f("$799") is True
    assert f("200 off") is True
    assert f("I'll do $250") is True
    assert f("make it 150") is True
    # Competitor comparison (two numbers) -> False
    assert f("Another telco offers me $799 with $60/month. Can your manager do better?") is False
    # No number -> False
    assert f("can you do better?") is False
    # Long sentence with one number -> False
    assert f("well my friend told me that a fair price might be around 700 dollars honestly") is False
