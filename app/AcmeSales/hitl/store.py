"""Local pending-approval store for human-in-the-loop discount approvals.

A tiny JSON-file-backed store shared between the Sales agent (which creates
pending requests and polls for a decision) and the Flask approval console
(where Mr Anwar approves or denies). No AWS infra — this keeps the prototype
$0 and fully local.

Concurrency: a best-effort file lock via atomic replace. For a single-user
local demo this is sufficient; it is not a production datastore.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

# The store file location can be overridden (tests point it at a temp file).
DEFAULT_STORE_PATH = Path(
    os.environ.get(
        "ACME_HITL_STORE",
        str(Path(tempfile.gettempdir()) / "acme_hitl_store.json"),
    )
)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"

APPROVER_NAME = "Mr Anwar"


class ApprovalStore:
    """JSON-file-backed approval store."""

    def __init__(self, path: Optional[Path | str] = None):
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        if not self.path.exists():
            self._write({})

    # --- low-level persistence ---

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to a temp file in the same dir, then replace.
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    # --- API ---

    def create_pending(
        self,
        *,
        customer_id: str,
        customer_name: str,
        device_id: str,
        device_name: str,
        base_price: float,
        requested_discount: float,
        reason: str = "",
    ) -> str:
        """Create a pending approval request. Returns the request id."""
        request_id = uuid.uuid4().hex[:12]
        record = {
            "request_id": request_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "device_id": device_id,
            "device_name": device_name,
            "base_price": base_price,
            "requested_discount": requested_discount,
            "auto_cap": 100,
            "reason": reason,
            "status": STATUS_PENDING,
            "approver": None,
            "created_at": time.time(),
            "decided_at": None,
        }
        data = self._read()
        data[request_id] = record
        self._write(data)
        return request_id

    def get(self, request_id: str) -> Optional[dict]:
        return self._read().get(request_id)

    def get_decision(self, request_id: str) -> Optional[str]:
        """Return the status of a request (pending/approved/denied), or None if missing."""
        rec = self.get(request_id)
        return rec["status"] if rec else None

    def set_decision(
        self, request_id: str, approved: bool, approver: str = APPROVER_NAME
    ) -> Optional[dict]:
        """Approve or deny a pending request. Returns the updated record, or None."""
        data = self._read()
        rec = data.get(request_id)
        if not rec:
            return None
        rec["status"] = STATUS_APPROVED if approved else STATUS_DENIED
        rec["approver"] = approver
        rec["decided_at"] = time.time()
        data[request_id] = rec
        self._write(data)
        return rec

    def list_pending(self) -> list[dict]:
        """Return all pending requests, oldest first."""
        data = self._read()
        pending = [r for r in data.values() if r["status"] == STATUS_PENDING]
        return sorted(pending, key=lambda r: r["created_at"])

    def list_all(self) -> list[dict]:
        data = self._read()
        return sorted(data.values(), key=lambda r: r["created_at"])

    def clear(self) -> None:
        """Remove all records (test helper)."""
        self._write({})

    def clear_decided(self) -> int:
        """Remove all decided (approved/denied) records, keeping any pending.

        Returns the number of records removed.
        """
        data = self._read()
        kept = {rid: r for rid, r in data.items() if r["status"] == STATUS_PENDING}
        removed = len(data) - len(kept)
        self._write(kept)
        return removed
