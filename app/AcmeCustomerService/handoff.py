"""Customer Service -> Sales handoff transport.

When the customer wants to re-contract or buy a new device, Customer Service
hands the conversation to the Sales runtime. This mirrors the reference
`httpRuntime` gateway pattern:

  - Deployed: invoke the Sales AgentCore Runtime over HTTP via the
    bedrock-agentcore client (ARN from env SALES_RUNTIME_ARN).
  - Local dev: if no ARN is configured, call the Sales agent in-process so the
    whole flow is demoable under `agentcore dev` without deploying.

The intent detector is a small, deterministic helper kept here so it is unit
testable without a model.
"""

from __future__ import annotations

import json
import os
import re

# Topic phrases that are ABOUT re-contracting / a new device.
_RECONTRACT_TOPIC = [
    r"\bre-?contract\b",
    r"\brenew\b",
    r"\bnew (phone|device|handset)\b",
    r"\bupgrade\b",
    r"\bbuy a (phone|device)\b",
    r"\bget a (new )?(phone|device)\b",
    r"\btrade[- ]?in\b",
]

# Framing that signals a QUESTION about the topic (status/eligibility), which
# Customer Service should answer — NOT an actionable request to start Sales.
# e.g. "when can I re-contract?", "how do I upgrade?", "am I eligible to renew?"
_QUESTION_LEAD = re.compile(
    r"^\s*(when|how|can i|could i|may i|am i|do i|is it|what|whether|if i)\b", re.IGNORECASE
)

# Clear intent-to-ACT phrasing that should route to Sales.
_ACTION_INTENT = [
    r"\bi (want|would like|'d like|wanna|wish) to\b",
    r"\bi want\b",
    r"\blet'?s\b",
    r"\bsign me up\b",
    r"\bget me\b",
    r"\bi'?m (looking|keen|ready) to\b",
    r"\bplease (re-?contract|renew|upgrade)\b",
    r"\bgo ahead\b",
]


def is_recontract_intent(text: str) -> bool:
    """Return True only when the customer wants to ACT on re-contracting.

    A mere QUESTION about re-contracting ("when can I re-contract?", "how do I
    upgrade?") stays with Customer Service to answer about account/contract
    status. We route to Sales only on an actionable request.
    """
    if not text:
        return False
    t = text.lower().strip()

    on_topic = any(re.search(p, t) for p in _RECONTRACT_TOPIC)
    if not on_topic:
        return False

    has_action = any(re.search(p, t) for p in _ACTION_INTENT)
    if has_action:
        return True

    # On-topic but no explicit action: if it's framed as a question (lead word
    # or ends with "?"), treat it as a Customer Service question, not a handoff.
    is_question = bool(_QUESTION_LEAD.match(t)) or t.endswith("?")
    if is_question:
        return False

    # On-topic, not a question, no explicit action verb — e.g. a bare command
    # like "re-contract my line" or "upgrade my phone". Treat as intent.
    return True


def _sales_runtime_arn() -> str | None:
    return os.environ.get("SALES_RUNTIME_ARN") or None


def _invoke_sales_remote(arn: str, prompt: str, session_id: str | None) -> str:
    """Invoke the deployed Sales runtime directly (runtime-to-runtime, SigV4).

    The Sales runtime uses AWS_IAM auth; this call is signed with the Customer
    Service runtime's execution role, which is granted
    bedrock-agentcore:InvokeAgentRuntime on the Sales runtime.
    """
    import uuid
    import boto3

    client = boto3.client("bedrock-agentcore")
    # AgentCore requires a runtimeSessionId of at least 33 characters.
    sid = session_id if session_id and len(session_id) >= 33 else uuid.uuid4().hex + uuid.uuid4().hex[:1]
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=sid,
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
    )

    body = resp.get("response")
    if body is None:
        return "Sales did not return a response."
    chunks = []
    if hasattr(body, "iter_chunks"):
        for part in body.iter_chunks():
            chunks.append(part.decode("utf-8", errors="ignore") if isinstance(part, (bytes, bytearray)) else str(part))
    else:
        raw = body.read()
        chunks.append(raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw))
    return "".join(chunks) or "Sales did not return a response."


def _invoke_sales_local(
    prompt: str, history: list | None = None, session_id: str | None = None
) -> tuple[str, list]:
    """Run ONE Sales turn in a SUBPROCESS (local dev / no deployed runtime).

    The Sales runtime ships its own `main.py`, `tools.py`, `model/`, `memory/`
    etc. — same module names as Customer Service. Loading Sales in-process
    collides with CS's already-imported modules in sys.modules (and also nests
    event loops / OTel contexts). Running Sales in a fresh subprocess gives it a
    clean interpreter with its own module namespace and event loop.

    `history` carries the running Sales conversation so multi-turn negotiation
    keeps context across turns. Returns (reply_text, updated_history).
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    sales_dir = Path(__file__).resolve().parent.parent / "AcmeSales"
    runner = sales_dir / "handoff_runner.py"

    env = dict(**_os_environ())
    env["PYTHONIOENCODING"] = "utf-8"
    payload = json.dumps(
        {"prompt": prompt, "history": history or [], "session_id": session_id or "local"}
    )
    proc = subprocess.run(
        [sys.executable, str(runner)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(sales_dir),
        env=env,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Sales subprocess failed: {proc.stderr[-500:]}")
    # The runner prints a JSON line {"text": ..., "history": [...]} on stdout.
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                return obj.get("text", ""), obj.get("history", history or [])
            except Exception:
                continue
    return (proc.stdout.strip() or "Sales did not return a response."), (history or [])


def _os_environ():
    import os
    return os.environ


def converse_with_sales(
    prompt: str, history: list | None = None, session_id: str | None = None
) -> tuple[str, list]:
    """Stateful Sales turn for the local frontend.

    Returns (reply_text, updated_history). Deployed path keeps session state via
    the runtime session id and doesn't need local history; local path threads
    `history` through the subprocess.
    """
    arn = _sales_runtime_arn()
    if arn:
        # Deployed runtime is session-aware; history is maintained server-side.
        return _invoke_sales_remote(arn, prompt, session_id), (history or [])
    return _invoke_sales_local(prompt, history, session_id)


def handoff_to_sales(
    prompt: str, session_id: str | None = None, auth_header: str | None = None
) -> str:
    """Hand the conversation to Sales and return its reply text (first handoff).

    Deployed: invoke the Sales runtime directly (runtime-to-runtime, SigV4) when
    SALES_RUNTIME_ARN is set.
    Local dev: run the Sales agent in a subprocess (no ARN set). Multi-turn
    continuation is handled by the frontend via converse_with_sales().
    """
    arn = _sales_runtime_arn()
    if arn:
        return _invoke_sales_remote(arn, prompt, session_id)
    text, _history = _invoke_sales_local(prompt)
    return text
