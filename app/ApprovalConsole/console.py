"""Acme Telco — Manager Approval Console (Flask).

A small local web console where the human sales manager (Mr Anwar) reviews
device-discount requests that exceed the $100 auto-approval limit and clicks
Approve or Deny. Backed by the same local store the Sales agent polls.

Run:
    python app/ApprovalConsole/console.py
    # then open http://localhost:8600/console
"""

import sys
from pathlib import Path

from flask import Flask, render_template, redirect, url_for, request

# Make the AcmeSales package importable so we share the exact same store.
SALES_DIR = Path(__file__).resolve().parent.parent / "AcmeSales"
sys.path.insert(0, str(SALES_DIR))

from hitl.store import ApprovalStore, APPROVER_NAME  # noqa: E402

_TEMPLATES = str(Path(__file__).resolve().parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

store = ApprovalStore()


@app.after_request
def disable_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def root():
    return redirect(url_for("console"))


@app.route("/console")
def console():
    pending = store.list_pending()
    recent = [r for r in store.list_all() if r["status"] != "pending"][-10:][::-1]
    return render_template(
        "console.html",
        pending=pending,
        recent=recent,
        approver=APPROVER_NAME,
    )


@app.route("/decide", methods=["POST"])
def decide():
    request_id = request.form.get("request_id", "")
    action = request.form.get("action", "")
    if request_id and action in ("approve", "deny"):
        store.set_decision(request_id, approved=(action == "approve"))
    return redirect(url_for("console"))


@app.route("/clear", methods=["POST"])
def clear():
    """Clear the decided-requests history (keeps any pending approvals)."""
    store.clear_decided()
    return redirect(url_for("console"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8600)
