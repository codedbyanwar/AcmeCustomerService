"""Acme Telco mobile plan catalog.

Single source of truth for plans, shared conceptually with the Sales agent.
SIM-only plans have no contract; postpaid plans are on a 24-month contract.
"""

# plan_id -> plan details
PLANS = {
    "SIM-10": {
        "name": "Acme SIM Starter",
        "monthly_fee": 10,
        "data": "5GB",
        "mins_texts": "unlimited",
        "contract_months": 0,
        "type": "sim-only",
    },
    "SIM-20": {
        "name": "Acme SIM Plus",
        "monthly_fee": 20,
        "data": "50GB",
        "mins_texts": "unlimited",
        "contract_months": 0,
        "type": "sim-only",
    },
    "SIM-30": {
        "name": "Acme SIM Max",
        "monthly_fee": 30,
        "data": "unlimited",
        "mins_texts": "unlimited",
        "contract_months": 0,
        "type": "sim-only",
    },
    "Basic-40": {
        "name": "Acme Postpaid Essential",
        "monthly_fee": 40,
        "data": "200GB",
        "mins_texts": "unlimited",
        "contract_months": 24,
        "type": "postpaid",
    },
    "Premium-60": {
        "name": "Acme Postpaid Premium",
        "monthly_fee": 60,
        "data": "400GB",
        "mins_texts": "unlimited",
        "contract_months": 24,
        "type": "postpaid",
    },
    "Ultimate-80": {
        "name": "Acme Postpaid Ultimate",
        "monthly_fee": 80,
        "data": "800GB",
        "mins_texts": "unlimited",
        "contract_months": 24,
        "type": "postpaid",
    },
}


def get_plan(plan_id: str) -> dict | None:
    """Return plan details by plan id (case-insensitive), or None if unknown."""
    if not plan_id:
        return None
    # Build a case-insensitive lookup so "premium-60" matches "Premium-60".
    lower_map = {pid.lower(): pid for pid in PLANS}
    canonical = lower_map.get(plan_id.strip().lower())
    return PLANS.get(canonical) if canonical else None


def format_plan(plan_id: str, plan: dict) -> str:
    """Format a single plan into a readable one-liner."""
    contract = (
        "no contract"
        if plan["contract_months"] == 0
        else f"{plan['contract_months']}-month contract"
    )
    return (
        f"{plan_id} — {plan['name']}: ${plan['monthly_fee']}/mo, "
        f"{plan['data']} data, {plan['mins_texts']} mins/texts, {contract}"
    )
