"""Task 7 tests: mock JWT caller auth + memory session no-op + actor resolution."""

import pytest

from conftest import load_module, APP, CS, SALES

_mock_jwt = load_module(APP / "auth" / "mock_jwt.py", "mock_jwt_test")
_cs_auth = load_module(CS / "auth_local.py", "cs_auth_test")
_cs_memory = load_module(CS / "memory" / "session.py", "cs_memory_test")


# --- Mock JWT mint + extract ---

def test_mint_and_extract_roundtrip():
    token = _mock_jwt.mint_webapp_token()
    claims = _mock_jwt.extract_caller(f"Bearer {token}")
    assert claims["sub"] == _mock_jwt.WEBAPP_SUBJECT
    assert claims["client_id"] == _mock_jwt.WEBAPP_CLIENT_ID


def test_extract_rejects_missing_header():
    with pytest.raises(ValueError):
        _mock_jwt.extract_caller(None)
    with pytest.raises(ValueError):
        _mock_jwt.extract_caller("")


def test_extract_rejects_non_bearer():
    with pytest.raises(ValueError):
        _mock_jwt.extract_caller("Basic abc123")


def test_extract_rejects_empty_token():
    with pytest.raises(ValueError):
        _mock_jwt.extract_caller("Bearer ")


# --- Per-agent caller validation (what the runtime uses) ---

def test_cs_auth_accepts_minted_token():
    token = _mock_jwt.mint_webapp_token()
    claims = _cs_auth.extract_caller(f"Bearer {token}")
    assert claims["sub"] == _mock_jwt.WEBAPP_SUBJECT


def test_cs_auth_rejects_without_token():
    with pytest.raises(ValueError):
        _cs_auth.extract_caller(None)


# --- Memory session no-op when unconfigured ---

def test_memory_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("MEMORY_SHAREDMEMORY_ID", raising=False)
    # Reload so module-level MEMORY_ID reflects the unset env.
    mem = load_module(CS / "memory" / "session.py", "cs_memory_unset_test")
    assert mem.get_memory_session_manager("sess-1", "cust-a-sub") is None


def test_memory_reads_id_when_set(monkeypatch):
    monkeypatch.setenv("MEMORY_SHAREDMEMORY_ID", "mem-123")
    mem = load_module(CS / "memory" / "session.py", "cs_memory_set_test")
    assert mem.MEMORY_ID == "mem-123"


# --- Actor id resolution from payload identifier ---

def test_cs_resolve_actor_id():
    import sys
    sys.path.insert(0, str(CS))
    try:
        cs_main = load_module(CS / "main.py", "cs_main_actor_test")
    finally:
        sys.path.remove(str(CS))
    assert cs_main.resolve_actor_id({"identifier": "123456789012"}) == "cust-a-sub"
    assert cs_main.resolve_actor_id({"identifier": "98765432"}) == "cust-b-sub"
    assert cs_main.resolve_actor_id({"identifier": "00000000"}) is None
    assert cs_main.resolve_actor_id({}) is None
