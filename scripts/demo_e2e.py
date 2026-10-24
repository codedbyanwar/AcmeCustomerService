"""End-to-end demo of the Acme Telco Sales journey (business-logic level).

Walks: eligibility -> device offer -> manager approval (via the shared store,
approved in another process/console) -> OTP -> order confirmation.

This exercises the real store and OTP logic without invoking Bedrock, so it's
a fast, $0 way to see the full HITL + OTP flow end to end.

Usage:
    # Terminal 1: run the approval console so you can click Approve.
    python app/ApprovalConsole/console.py

    # Terminal 2: run the demo (blocks until you approve in the console).
    python scripts/demo_e2e.py --identifier 123456789012 --device DEV-DUO --discount 150

    # Or auto-approve without the console (for a scripted run):
    python scripts/demo_e2e.py --auto-approve
"""

import argparse
import importlib.util
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SALES = ROOT / "app" / "AcmeSales"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser(description="Acme Telco E2E demo")
    parser.add_argument("--identifier", default="123456789012", help="account or mobile")
    parser.add_argument("--device", default="DEV-DUO")
    parser.add_argument("--discount", type=float, default=150)
    parser.add_argument("--auto-approve", action="store_true",
                        help="approve in-process instead of via the console")
    parser.add_argument("--pin", default="123456")
    args = parser.parse_args()

    sales_logic = _load(SALES / "sales_logic.py", "demo_sales_logic")
    store_mod = _load(SALES / "hitl" / "store.py", "demo_store")
    otp_mod = _load(SALES / "otp" / "verify.py", "demo_otp")

    store = store_mod.ApprovalStore()

    print("== Acme Telco — Sales journey demo ==\n")

    elig = sales_logic.eligibility(args.identifier)
    print(f"[eligibility] {elig['message']}")
    if not elig["found"]:
        return

    offer = sales_logic.build_offer(args.device, args.discount)
    print(f"[offer] {offer['message']}")

    if offer["requires_approval"]:
        print('\n[sales] "Let me check with my manager for an additional discount…"')
        if args.auto_approve:
            # Simulate the manager approving shortly after the request is created.
            def approver():
                time.sleep(1.0)
                pend = store.list_pending()
                if pend:
                    store.set_decision(pend[-1]["request_id"], approved=True)
            threading.Thread(target=approver, daemon=True).start()
        else:
            print("   (waiting for Mr Anwar to Approve/Deny in the console…)")

        result = sales_logic.request_manager_approval(
            identifier=args.identifier, device_id=args.device,
            discount=args.discount, reason="loyal customer",
            store=store, timeout=120, poll_interval=1,
        )
        print(f"[manager decision] {result['status']}")
        print(f"[sales] {result['message']}")
        if result["status"] != "approved":
            print("\nStopping — no additional discount approved.")
            return
        final_price = result["offer"]["final_price"]
    else:
        final_price = offer["final_price"]

    # OTP gate before processing the order.
    cust = sales_logic.resolve_customer(args.identifier)
    otp = otp_mod.OtpSession()
    sent = otp.send(cust["email"])
    print(f"\n[otp] {sent['message']}")
    v = otp.verify(args.pin)
    print(f"[otp] {v['message']}")
    if not v["ok"]:
        print("\nStopping — identity not verified.")
        return

    print(
        f"\n[order] Confirmed: {offer['device_name']} for ${final_price:.0f} upfront, "
        f"charged to {cust['name']}'s next bill. Thanks for choosing Acme Telco!"
    )


if __name__ == "__main__":
    main()
