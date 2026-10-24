"""Pure, testable Sales business logic (no model, no runtime).

Separated from tools.py so discount/eligibility rules can be unit-tested
directly and reused by the HITL flow.
"""

import importlib.util
import sys
import time
from pathlib import Path

# Sales data lives under this package's own data/ dir, so it is packaged with
# the Sales runtime's codeLocation and resolves both locally and in the
# deployed container (everything under the codeLocation sits at /var/task/).
_DATA = Path(__file__).resolve().parent / "data"


def _load_data(filename: str, module_name: str):
    """Load a data module from this package's data/ dir under a unique name.

    A unique module name avoids the dual-`data`-package collision when the
    whole test suite runs in one interpreter; registering it in sys.modules
    keeps features like @dataclass resolving correctly.
    """
    spec = importlib.util.spec_from_file_location(module_name, _DATA / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Device catalog + discount policy.
_devices = _load_data("devices.py", "sales_devices_data")
DEVICES = _devices.DEVICES
get_device = _devices.get_device
canonical_device_id = _devices.canonical_device_id
discount_decision = _devices.discount_decision
AUTO_APPROVE_CAP = _devices.AUTO_APPROVE_CAP

# Plan + customer data (vendored copy kept in sync with the Customer Service
# agent — single conceptual source of truth, duplicated so each runtime is
# self-contained when packaged).
_plans = _load_data("plans.py", "sales_plans_data")
_customers = _load_data("customers.py", "sales_customers_data")
get_plan = _plans.get_plan
resolve_customer = _customers.resolve_customer

# Default upsell target plan for SIM-only customers who want a device.
UPSELL_PLAN_ID = "Premium-60"


def eligibility(identifier: str) -> dict:
    """Determine re-contract / upsell eligibility for a customer.

    Returns a structured dict describing the path:
      {"found": bool, "customer": <dict|None>, "path": "recontract"|"upsell"|None,
       "message": str}
    """
    cust = resolve_customer(identifier)
    if not cust:
        return {
            "found": False,
            "customer": None,
            "path": None,
            "message": (
                "I couldn't find that account. Please share your 12-digit "
                "account number or 8-digit mobile number."
            ),
        }

    plan = get_plan(cust["plan_id"])
    is_postpaid = plan and plan["type"] == "postpaid"

    if is_postpaid and cust.get("recontract_eligible"):
        return {
            "found": True,
            "customer": cust,
            "path": "recontract",
            "message": (
                f"{cust['name']} is on {cust['plan_id']} with an active device "
                f"contract and is eligible to re-contract with a new device."
            ),
        }

    # SIM-only (or not yet eligible postpaid) -> upsell to a postpaid plan + device.
    return {
        "found": True,
        "customer": cust,
        "path": "upsell",
        "message": (
            f"{cust['name']} is on {cust['plan_id']} (no device contract). "
            f"I can upsell to {UPSELL_PLAN_ID} (Acme Postpaid Premium) with a "
            f"discounted device."
        ),
    }


def build_offer(device_id: str, discount: float) -> dict:
    """Build a device offer applying the discount policy.

    Returns:
      {"ok": bool, "device_id": str|None, "device_name": str|None,
       "upfront": float|None, "discount": float, "final_price": float|None,
       "auto_approved": bool, "requires_approval": bool, "cap": int,
       "message": str}
    """
    device = get_device(device_id)
    if not device:
        valid = ", ".join(DEVICES.keys())
        return {
            "ok": False,
            "device_id": None,
            "device_name": None,
            "upfront": None,
            "discount": 0.0,
            "final_price": None,
            "auto_approved": False,
            "requires_approval": False,
            "cap": AUTO_APPROVE_CAP,
            "message": f"Unknown device '{device_id}'. Available: {valid}.",
        }

    did = canonical_device_id(device_id)
    decision = discount_decision(discount)
    d = decision["discount"]
    final_price = device["upfront"] - d

    if decision["requires_approval"]:
        message = (
            f"A ${d:.0f} discount on the {device['name']} exceeds the "
            f"${AUTO_APPROVE_CAP} auto-approval limit and needs manager approval."
        )
    else:
        message = (
            f"Offer for {device['name']}: upfront ${device['upfront']:.0f}, "
            f"discount ${d:.0f}, you pay ${final_price:.0f} (charged to your next bill). "
            f"This discount is approved."
        )

    return {
        "ok": True,
        "device_id": did,
        "device_name": device["name"],
        "upfront": float(device["upfront"]),
        "discount": d,
        "final_price": float(final_price),
        "auto_approved": decision["auto_approved"],
        "requires_approval": decision["requires_approval"],
        "cap": AUTO_APPROVE_CAP,
        "message": message,
    }


# --- Human-in-the-loop manager approval (blocking within one turn) ---

# Default blocking behavior: poll the shared store until the manager decides.
DEFAULT_APPROVAL_TIMEOUT = 180  # seconds to wait for a manager decision
DEFAULT_POLL_INTERVAL = 2       # seconds between store checks

# Load the HITL store module from this package's hitl/ dir (container-safe).
_store_spec = importlib.util.spec_from_file_location(
    "sales_hitl_store", Path(__file__).resolve().parent / "hitl" / "store.py"
)
_store_mod = importlib.util.module_from_spec(_store_spec)
sys.modules["sales_hitl_store"] = _store_mod
_store_spec.loader.exec_module(_store_mod)
ApprovalStore = _store_mod.ApprovalStore
STATUS_APPROVED = _store_mod.STATUS_APPROVED
STATUS_DENIED = _store_mod.STATUS_DENIED
STATUS_PENDING = _store_mod.STATUS_PENDING


def request_manager_approval(
    *,
    identifier: str,
    device_id: str,
    discount: float,
    reason: str = "",
    store=None,
    timeout: float = DEFAULT_APPROVAL_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    sleep=time.sleep,
    now=time.monotonic,
) -> dict:
    """Request manager (Mr Anwar) approval for a discount above the auto-cap.

    Creates a pending record in the shared store and blocks, polling until the
    manager approves/denies or the timeout elapses. Designed so the customer
    hears "let me check with my manager" and the final answer arrives in the
    same turn.

    `store`, `sleep`, and `now` are injectable for fast, deterministic tests.

    Returns a dict:
      {"status": "approved"|"denied"|"timeout"|"error",
       "request_id": str|None, "offer": <offer dict>|None,
       "approver": str|None, "message": str}
    """
    offer = build_offer(device_id, discount)
    if not offer["ok"]:
        return {"status": "error", "request_id": None, "offer": None,
                "approver": None, "message": offer["message"]}

    if not offer["requires_approval"]:
        # Shouldn't normally be called for <= cap, but handle gracefully.
        return {"status": "approved", "request_id": None, "offer": offer,
                "approver": None,
                "message": "This discount is within the auto-approval limit; approved."}

    cust = resolve_customer(identifier)
    if not cust:
        return {"status": "error", "request_id": None, "offer": None,
                "approver": None,
                "message": "Could not identify the customer for approval."}

    s = store if store is not None else ApprovalStore()
    request_id = s.create_pending(
        customer_id=cust["customer_id"],
        customer_name=cust["name"],
        device_id=offer["device_id"],
        device_name=offer["device_name"],
        base_price=offer["upfront"],
        requested_discount=offer["discount"],
        reason=reason,
    )

    deadline = now() + timeout
    while now() < deadline:
        status = s.get_decision(request_id)
        if status == STATUS_APPROVED:
            rec = s.get(request_id)
            return {"status": "approved", "request_id": request_id, "offer": offer,
                    "approver": rec.get("approver"),
                    "message": (
                        f"Good news — {rec.get('approver')} approved the "
                        f"${offer['discount']:.0f} discount. Your {offer['device_name']} "
                        f"is ${offer['final_price']:.0f} upfront (charged to your next bill)."
                    )}
        if status == STATUS_DENIED:
            rec = s.get(request_id)
            return {"status": "denied", "request_id": request_id, "offer": offer,
                    "approver": rec.get("approver"),
                    "message": (
                        f"My manager wasn't able to approve the extra discount this time. "
                        f"The best I can confirm right away is ${AUTO_APPROVE_CAP} off, "
                        f"bringing the {offer['device_name']} to "
                        f"${offer['upfront'] - AUTO_APPROVE_CAP:.0f} upfront."
                    )}
        sleep(poll_interval)

    return {"status": "timeout", "request_id": request_id, "offer": offer,
            "approver": None,
            "message": (
                "My manager is still reviewing the additional discount. I can "
                f"confirm ${AUTO_APPROVE_CAP} off now, or follow up once the "
                "review is complete."
            )}
