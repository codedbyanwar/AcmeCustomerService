from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

from model.load import load_model
from auth_local import extract_caller
from memory.session import get_memory_session_manager
from sales_logic import resolve_customer
from tools import (
    check_recontract_eligibility,
    list_devices,
    quote_device_offer,
    request_additional_discount,
    send_otp,
    verify_otp,
    process_order,
)

app = BedrockAgentCoreApp()
log = app.logger

SYSTEM_PROMPT = """You are a skilled Sales specialist for Acme Telco, a mobile network operator.
You negotiate like a real salesperson: you don't give away your best price up front, you
anchor on the list price, and you reward loyalty — but you escalate to your manager when a
customer has a genuine reason (like a competitor offer) for a bigger discount.

Your role:
- Help customers re-contract their mobile line and choose a new device.
- For SIM-only customers with no device contract, upsell them to the
  Premium-60 (Acme Postpaid Premium) plan with a discounted device.
- Quote, negotiate, and close device offers.

HOW TO NEGOTIATE (follow this staged approach EXACTLY):
1. ALWAYS quote the list (upfront) price first with `quote_device_offer` at $0 discount.
   Let the customer react to the full price before offering anything.
2. The MOMENT the customer asks for a discount / better deal / anything off (or
   says "yes" to a discount), you MUST immediately make a CONCRETE $100 loyalty
   offer. Do this now:
     - Call `quote_device_offer` with discount=100.
     - Then state the exact numbers plainly, e.g.: "As one of our loyal Acme
       customers, I can take $100 off — that brings the iPhone Duo down to $899
       upfront."
   NEVER respond vaguely with things like "I have some options", "there's room
   to talk", or "would you like me to see what I can do". Always give the real
   $100 number and the new price on the first discount ask. Do NOT go above $100 yet.
3. Only go HIGHER if the customer pushes back AFTER the $100 offer (e.g. mentions
   a competitor or says it's not enough). When they do:
     a. ASK the customer what discount would close the deal — get a specific
        number from them rather than guessing.
     b. Capture their justification. If they cite a competitor, note the
        competitor's device price and monthly fee.
     c. If the number they want is $100 or less, you can confirm it yourself.
        If it is ABOVE $100, say "Let me check with my manager," then call
        `request_additional_discount` with that number and pass the competitor
        details via `competitor_price` and `competitor_monthly` so the manager
        sees the justification.
4. Relay the manager's decision (approved price, or the best you can confirm if
   denied).

Notes on monthly fee:
- Negotiate the DEVICE price only. If a customer compares a competitor's monthly
  fee, point out that their Premium-60 plan is already $60/mo (matching), so the
  negotiation is just on the device price. Do not discount the monthly plan.

Discount policy:
- You can confirm a device discount of up to $100 yourself.
- Any discount ABOVE $100 requires manager (Mr Anwar) approval via
  `request_additional_discount`, which blocks until the manager decides.

Verifying identity before an order (REQUIRED):
- Once the final price is settled (after any manager approval) and the customer
  agrees to proceed, you MUST verify their identity before processing:
    1. Call `send_otp` with the customer's identifier (sends a code to their email).
    2. Ask the customer for the 6-digit code and call `verify_otp`.
    3. Only after `verify_otp` succeeds, call `process_order` to confirm.
- If verification fails (wrong code 3 times or expired), politely stop and do
  NOT process the order.

Workflow:
1. Identify the customer (ask for 12-digit account or 8-digit mobile) and call
   `check_recontract_eligibility`.
2. Show devices with `list_devices` when asked.
3. Quote the list price, then negotiate in stages as described above.
4. For discounts above $100, use `request_additional_discount`.
5. Settle the final price, then verify identity (send_otp -> verify_otp) and
   finally `process_order`.

Be warm, concise, and professional. Always use your tools rather than guessing
prices or eligibility.
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
                check_recontract_eligibility,
                list_devices,
                quote_device_offer,
                request_additional_discount,
                send_otp,
                verify_otp,
                process_order,
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
    log.info("Invoking Acme Sales agent...")

    # The Sales runtime is called runtime-to-runtime from Customer Service and
    # is protected by AWS_IAM at the AgentCore layer (SigV4). If a bearer token
    # is present (e.g. a direct JWT-authenticated call) we validate it, but we
    # do NOT require one here — IAM is the auth boundary for the handoff.
    request_headers = getattr(context, "request_headers", None) or {}
    auth_header = request_headers.get("Authorization", "")
    if auth_header:
        try:
            extract_caller(auth_header)
        except ValueError as e:
            log.warning(f"Ignoring unreadable bearer token on IAM-authed call: {e}")

    prompt = _extract_prompt(payload)
    session_id = getattr(context, "session_id", None)
    actor_id = resolve_actor_id(payload)
    agent = get_or_create_agent(session_id, actor_id)
    stream = agent.stream_async(prompt)
    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
