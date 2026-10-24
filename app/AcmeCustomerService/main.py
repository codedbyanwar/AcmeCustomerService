from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

from model.load import load_model
from auth_local import extract_caller
from memory.session import get_memory_session_manager
from data.customers import resolve_customer
from tools import (
    identify_customer,
    get_plan_fee,
    list_plans,
    get_customer_account,
    handoff_to_sales,
    set_request_context,
)

app = BedrockAgentCoreApp()
log = app.logger

SYSTEM_PROMPT = """You are the Customer Service assistant for Acme Telco, a mobile network operator.

Your role:
- Answer questions about Acme Telco mobile plans and subscription fees.
- Help customers understand their current plan, device, and contract.
- Be friendly, concise, and professional.

Identifying the customer:
- Early in the conversation, if the customer asks anything account-specific
  (their plan, their bill, their contract), ask for their 12-digit account
  number OR their 8-digit mobile number, then call `identify_customer`.
- For general plan/pricing questions (e.g. "how much is the Premium plan?"),
  you do NOT need to identify the customer — just use `get_plan_fee` or `list_plans`.
- If the identifier is unknown or ambiguous, politely ask again.

Scope and handoff:
- Stay within plan/subscription topics for general questions.
- If a customer ASKS A QUESTION about re-contracting — e.g. "when can I
  re-contract?", "am I eligible to upgrade?", "how does re-contracting work?" —
  answer it yourself using `get_customer_account` (identify them first if
  needed). Explain their contract status plainly:
    * If they are on a no-contract SIM-only plan, tell them there's nothing to
      re-contract and they're free to change anytime, and gently mention they
      could move to a postpaid plan with a discounted device if interested.
    * If they are on a postpaid contract, tell them their contract dates and
      whether they are eligible to re-contract yet.
  Do NOT hand off just because they asked a question.
- Only hand off to Sales (call `handoff_to_sales`) when the customer clearly
  WANTS TO PROCEED — e.g. "I want to re-contract", "get me a new phone", "let's
  upgrade". Pass their request and account/mobile number, then relay Sales'
  response naturally.

Always use your tools to get accurate, up-to-date information rather than guessing.
"""

_agent = None


def get_or_create_agent(session_id: str | None = None, actor_id: str | None = None):
    global _agent
    if _agent is None:
        session_manager = (
            get_memory_session_manager(session_id, actor_id)
            if session_id and actor_id
            else None
        )
        _agent = Agent(
            model=load_model(),
            session_manager=session_manager,
            system_prompt=SYSTEM_PROMPT,
            tools=[
                identify_customer,
                get_plan_fee,
                list_plans,
                get_customer_account,
                handoff_to_sales,
            ],
        )
    return _agent


def resolve_actor_id(payload) -> str | None:
    """Best-effort resolve the Memory actor id from an identifier in the payload."""
    identifier = payload.get("identifier") if isinstance(payload, dict) else None
    if identifier:
        cust = resolve_customer(identifier)
        if cust:
            return cust["memory_key"]
    return None


def _extract_prompt(payload) -> str:
    """Validate and extract the text prompt from the invocation payload."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid payload: expected an object with a 'prompt' string.")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Invalid payload: 'prompt' must be a non-empty string.")
    return prompt


@app.entrypoint
async def invoke(payload, context):
    log.info("Invoking Acme Customer Service agent...")

    # Caller/security layer: require a bearer token (mock locally, Cognito deployed).
    request_headers = getattr(context, "request_headers", None) or {}
    auth_header = request_headers.get("Authorization", "")
    extract_caller(auth_header)  # raises ValueError if missing/unreadable

    prompt = _extract_prompt(payload)
    session_id = getattr(context, "session_id", None)
    actor_id = resolve_actor_id(payload)
    # Make the caller's token + session available to the handoff tool so it can
    # forward the JWT to the CUSTOM_JWT Sales gateway.
    set_request_context(auth_header=auth_header, session_id=session_id)
    agent = get_or_create_agent(session_id, actor_id)
    stream = agent.stream_async(prompt)
    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
