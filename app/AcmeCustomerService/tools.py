"""Customer Service agent tools.

Pure, testable functions decorated as Strands tools. Kept separate from the
runtime entrypoint so they can be unit-tested without importing the
BedrockAgentCoreApp runtime.
"""

from strands import tool

from data.plans import PLANS, get_plan, format_plan
from data.customers import resolve_customer


@tool
def identify_customer(identifier: str) -> str:
    """Identify the Acme Telco customer by their account number or mobile number.

    Call this before answering account-specific questions. Accepts either a
    12-digit account number or an 8-digit Singapore mobile number (spaces/dashes ok).

    Args:
        identifier: The customer's 12-digit account number or 8-digit mobile number.

    Returns:
        A confirmation with the customer's name and plan when matched, or a
        re-ask message when the identifier is unknown or ambiguous.
    """
    cust = resolve_customer(identifier)
    if not cust:
        return (
            "I couldn't find an account matching that. Please share your "
            "12-digit account number or your 8-digit mobile number."
        )
    plan = get_plan(cust["plan_id"])
    plan_name = plan["name"] if plan else cust["plan_id"]
    return (
        f"Identified customer {cust['name']} (account {cust['account_number']}), "
        f"currently on {cust['plan_id']} — {plan_name}. "
        f"memory_key={cust['memory_key']}"
    )


@tool
def get_plan_fee(plan_id: str) -> str:
    """Get the monthly subscription fee and details for a specific plan.

    Args:
        plan_id: Plan identifier, e.g. 'SIM-20', 'Premium-60', 'Ultimate-80'.

    Returns:
        The plan's monthly fee and details, or a not-found message.
    """
    plan = get_plan(plan_id)
    if not plan:
        valid = ", ".join(PLANS.keys())
        return f"No plan found matching '{plan_id}'. Available plans: {valid}."
    # Resolve canonical id for display.
    lower_map = {pid.lower(): pid for pid in PLANS}
    canonical = lower_map[plan_id.strip().lower()]
    return format_plan(canonical, plan)


@tool
def list_plans(plan_type: str = "all") -> str:
    """List available Acme Telco mobile plans.

    Args:
        plan_type: Filter by 'sim-only', 'postpaid', or 'all' (default).

    Returns:
        A formatted list of plans.
    """
    pt = (plan_type or "all").strip().lower()
    if pt not in ("all", "sim-only", "postpaid"):
        pt = "all"
    lines = [
        format_plan(pid, plan)
        for pid, plan in PLANS.items()
        if pt == "all" or plan["type"] == pt
    ]
    header = "Acme Telco plans" + ("" if pt == "all" else f" ({pt})") + ":"
    return header + "\n" + "\n".join(lines)


# Per-invocation request context (set by the entrypoint before the agent runs)
# so tools can access the caller's bearer token and session without the model
# having to supply them.
_request_ctx = {"auth_header": None, "session_id": None}


def set_request_context(auth_header=None, session_id=None):
    _request_ctx["auth_header"] = auth_header
    _request_ctx["session_id"] = session_id


@tool
def handoff_to_sales(customer_message: str, identifier: str = "") -> str:
    """Hand the conversation to the Sales team for re-contracting or a new device.

    Use this when the customer wants to re-contract their line, renew, upgrade,
    or buy a new device. Pass along the customer's request and, if known, their
    account or mobile number so Sales has context.

    Args:
        customer_message: What the customer wants (their re-contract/device request).
        identifier: The customer's account or mobile number, if already provided.

    Returns:
        The Sales team's response to relay back to the customer.
    """
    from handoff import handoff_to_sales as _do_handoff

    prompt = customer_message
    if identifier:
        prompt = f"[Customer identifier: {identifier}] {customer_message}"
    return _do_handoff(
        prompt,
        session_id=_request_ctx.get("session_id"),
        auth_header=_request_ctx.get("auth_header"),
    )


@tool
def get_customer_account(identifier: str) -> str:
    """Look up a customer's account summary (plan, device, contract) by account or mobile number.

    Args:
        identifier: The customer's 12-digit account number or 8-digit mobile number.

    Returns:
        A summary of the customer's current plan, device, and contract status.
    """
    cust = resolve_customer(identifier)
    if not cust:
        return (
            "I couldn't find an account matching that. Please share your "
            "12-digit account number or your 8-digit mobile number."
        )
    plan = get_plan(cust["plan_id"])
    plan_name = plan["name"] if plan else cust["plan_id"]
    fee = plan["monthly_fee"] if plan else "?"
    parts = [
        f"Account {cust['account_number']} — {cust['name']}",
        f"Plan: {cust['plan_id']} ({plan_name}), ${fee}/mo",
    ]
    if cust["device"]:
        parts.append(f"Device: {cust['device']}")
    else:
        parts.append("Device: none (SIM-only)")
    if cust["contract"]:
        c = cust["contract"]
        parts.append(f"Contract: {c['start']} to {c['end']} ({c['months']} months)")
        parts.append(
            "Re-contract: eligible"
            if cust["recontract_eligible"]
            else "Re-contract: not yet eligible"
        )
    else:
        parts.append("Contract: none")
    return " | ".join(parts)
