"""Subprocess runner for the Sales agent, used by the Customer Service handoff
in local development.

Reads a JSON payload from stdin:
    {"prompt": "<customer message>", "history": [<prior strands messages>]}

Rebuilds the Sales Strands agent seeded with `history` (so multi-turn
negotiation keeps context across turns), runs ONE turn, and prints a single
JSON line to stdout:
    {"text": "<reply>", "history": [<updated strands messages>]}

Running Sales in its own interpreter gives it a clean module namespace and event
loop, isolated from the Customer Service process.
"""

import json
import sys


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"text": "", "history": []}))
        return

    # Accept either a bare prompt string (back-compat) or a JSON payload.
    prompt = raw
    history = []
    session_id = None
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            prompt = payload.get("prompt", "")
            history = payload.get("history", []) or []
            session_id = payload.get("session_id")
    except (json.JSONDecodeError, ValueError):
        pass

    # `import main` resolves to the Sales runtime entrypoint + its sibling modules.
    import main as sales_main
    import tools as sales_tools

    # Bind OTP to a persistent, session-keyed store so send_otp/verify_otp
    # survive across subprocess turns (each turn is a fresh interpreter).
    if session_id:
        sales_tools.set_otp_session(session_id)

    agent = sales_main.get_or_create_agent()
    # Seed prior conversation so the agent remembers the negotiation so far.
    if history:
        try:
            agent.messages = history
        except Exception:
            pass
    # No-op the printing callback so only our JSON line hits stdout.
    try:
        agent.callback_handler = lambda **_kwargs: None
    except Exception:
        pass

    result = agent(prompt)
    try:
        text = result.message["content"][0]["text"]
    except Exception:
        text = str(result)

    # Return the full updated message history for the next turn.
    try:
        updated = agent.messages
    except Exception:
        updated = history

    print(json.dumps({"text": text, "history": updated}))


if __name__ == "__main__":
    main()
