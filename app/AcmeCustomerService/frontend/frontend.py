"""Acme Telco Customer Portal — front end (Flask), live models.

Pages:
  /        Acme-branded landing page with a "Start chat" button.
  /chat    Responsive customer chat UI. A mock JWT is attached under the hood
           (no login/credential form). The agent asks for a mobile/account
           number to identify the customer in-conversation.

The chat endpoint drives the Customer Service agent in-process (real Bedrock)
and streams its reply. Re-contract requests route to the Sales agent; when
SALES_RUNTIME_ARN is set the handoff reaches the deployed Sales runtime,
otherwise it runs Sales in a local subprocess.

Run:
    python app/AcmeCustomerService/frontend/frontend.py
    # then open http://localhost:8500/
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Force UTF-8 stdout/stderr so emoji in model output never crash the process on
# Windows consoles (cp1252). Harmless on other platforms.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from flask import Flask, render_template, request, Response, stream_with_context

# Make the AcmeCustomerService package and this frontend dir importable.
FRONTEND_DIR = Path(__file__).resolve().parent
CS_DIR = FRONTEND_DIR.parent
sys.path.insert(0, str(FRONTEND_DIR))
sys.path.insert(0, str(CS_DIR))        # for main, auth_local

# auth helper lives one level up in app/auth; vendor the per-agent copy instead.
from auth_local import extract_caller  # noqa: E402  (validation parity)

_TEMPLATES = str(Path(__file__).resolve().parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# A mock JWT representing the Acme web app principal (caller/security layer).
# Minted once at startup; attached to agent invocations under the hood.
sys.path.insert(0, str(CS_DIR.parent))  # app/ for the shared auth package
from auth.mock_jwt import mint_webapp_token  # noqa: E402

WEBAPP_TOKEN = mint_webapp_token()


@app.after_request
def disable_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _get_cs_agent():
    """Import the CS runtime module and return its (singleton) agent."""
    import importlib
    cs_main = importlib.import_module("main")
    return cs_main.get_or_create_agent()


class ThinkingFilter:
    """Streaming filter that hides the model's internal reasoning.

    Suppresses anything inside <thinking>...</thinking> and strips stray
    <response>/</response> wrapper tags, buffering across chunk boundaries so a
    tag split between chunks is still caught. Call feed() per chunk and flush()
    at the end.
    """

    _TAGS = ("<thinking>", "</thinking>", "<response>", "</response>")
    _MAXTAG = len("</response>")  # longest tag length, for partial-tag buffering

    def __init__(self):
        self._buf = ""
        self._in_thinking = False

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out = []
        while self._buf:
            if self._in_thinking:
                idx = self._buf.find("</thinking>")
                if idx == -1:
                    keep = self._MAXTAG - 1
                    self._buf = self._buf[-keep:] if len(self._buf) > keep else self._buf
                    return "".join(out)
                self._buf = self._buf[idx + len("</thinking>"):]
                self._in_thinking = False
                continue

            open_idx = self._buf.find("<thinking>")
            if open_idx == -1:
                safe = self._buf
                tail = ""
                for n in range(1, self._MAXTAG):
                    frag = self._buf[-n:]
                    if any(t.startswith(frag) for t in self._TAGS):
                        tail = frag
                        safe = self._buf[:-n]
                        break
                out.append(self._strip_response(safe))
                self._buf = tail
                return "".join(out)

            out.append(self._strip_response(self._buf[:open_idx]))
            self._buf = self._buf[open_idx + len("<thinking>"):]
            self._in_thinking = True

        return "".join(out)

    def flush(self) -> str:
        if self._in_thinking:
            return ""
        rest = self._strip_response(self._buf)
        self._buf = ""
        return rest

    @staticmethod
    def _strip_response(text: str) -> str:
        return text.replace("<response>", "").replace("</response>", "")


# --- Sales session routing ---
# Once a conversation hands off to Sales, subsequent customer turns continue
# going to Sales (with accumulated history) rather than back to Customer
# Service — mirroring the deployed runtime's session continuity. Keyed by the
# browser session cookie.
_sales_sessions = {}  # session_id -> {"active": bool, "history": [...]}


def _sales_state(session_id: str) -> dict:
    st = _sales_sessions.get(session_id)
    if st is None:
        st = {"active": False, "history": []}
        _sales_sessions[session_id] = st
    return st


def _order_complete(text: str) -> bool:
    """Heuristic: the Sales turn confirmed an order, so hand back to CS."""
    t = text.lower()
    return "order" in t and ("confirmed" in t or "all set" in t)


_HANDOFF_LINE = (
    "Sure — let me connect you with our Sales specialist to help you re-contract "
    "and pick a new device. One moment…\n\n"
)

_MANAGER_WAIT_LINE = (
    "Let me get approval from my manager for that — please hold on a moment…\n\n"
)

import re as _re

_AMOUNT_RE = _re.compile(r"\d{2,4}")


def _looks_like_closing_number(text: str) -> bool:
    """True when the message is the customer naming a single closing amount.

    Shows the "checking with my manager" beat only for a concrete closing offer
    like "$799", "200 off", or "I'll do $250" — NOT a competitor comparison
    sentence such as "another telco offers $799 with $60/month" (multiple
    numbers) or a long descriptive message. The actual >$100 escalation is still
    decided by the Sales agent/tools; this only controls the UX beat.
    """
    t = (text or "").strip()
    nums = _AMOUNT_RE.findall(t)
    if len(nums) != 1:
        return False
    return len(t.split()) <= 6


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/chat")
def chat():
    resp = Response(render_template("chat.html"))
    # Stable session id so the Sales conversation keeps state across turns.
    if not request.cookies.get("acme_session"):
        resp.set_cookie("acme_session", uuid.uuid4().hex, samesite="Lax")
    return resp


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return {"error": "empty prompt"}, 400

    # Caller/security layer parity: validate the mock bearer token.
    auth_header = request.headers.get("Authorization", f"Bearer {WEBAPP_TOKEN}")
    try:
        extract_caller(auth_header)
    except ValueError as e:
        return {"error": str(e)}, 401

    session_id = request.cookies.get("acme_session", "default")
    st = _sales_state(session_id)

    # Route to Sales if we're already mid-Sales-conversation, or this message
    # expresses re-contract / new-device intent. Sales keeps its own history so
    # the negotiation continues across turns (stateful, like the deployed runtime).
    import handoff as _handoff
    first_handoff = (not st["active"]) and _handoff.is_recontract_intent(prompt)
    route_to_sales = st["active"] or first_handoff

    if route_to_sales:
        def generate_sales():
            # Transition line on the first handoff from Customer Service.
            if first_handoff:
                yield _HANDOFF_LINE
            # "Checking with my manager" beat before a likely-escalating turn.
            elif len(st.get("history") or []) >= 4 and _looks_like_closing_number(prompt):
                yield _MANAGER_WAIT_LINE

            try:
                text, new_history = _handoff.converse_with_sales(
                    prompt, history=st["history"], session_id=session_id
                )
            except Exception as e:  # noqa: BLE001
                yield f"Sorry, I hit a problem reaching Sales: {e}"
                return
            st["history"] = new_history
            st["active"] = not _order_complete(text)
            tf = ThinkingFilter()
            out = tf.feed(text) + tf.flush()
            yield out or text

        return Response(stream_with_context(generate_sales()), mimetype="text/plain")

    agent = _get_cs_agent()

    def generate():
        # Run the ENTIRE async agent stream inside one asyncio.run() on a
        # dedicated thread, pushing chunks to a queue, to keep the agent's async
        # context intact (driving the generator one chunk at a time from sync
        # code corrupts OpenTelemetry context tokens).
        import queue
        import threading

        q: "queue.Queue" = queue.Queue()
        _DONE = object()

        def worker():
            async def run():
                async for event in agent.stream_async(prompt):
                    if "data" in event and isinstance(event["data"], str):
                        q.put(event["data"])
            try:
                asyncio.run(run())
            except Exception as e:  # surface a clean message to the client
                q.put(f"\n\n[error] {e}")
            finally:
                q.put(_DONE)

        threading.Thread(target=worker, daemon=True).start()

        tf = ThinkingFilter()
        while True:
            item = q.get()
            if item is _DONE:
                break
            visible = tf.feed(item)
            if visible:
                yield visible
        tail = tf.flush()
        if tail:
            yield tail

    return Response(stream_with_context(generate()), mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8500)
