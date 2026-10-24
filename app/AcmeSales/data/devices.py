"""Acme Telco device catalog and discount logic for the Sales agent.

Discount policy:
  - A device discount of up to and including $100 off the upfront cost is
    auto-approved by the Sales agent.
  - Anything above $100 requires human (Mr Anwar) approval via the console.
"""

AUTO_APPROVE_CAP = 100  # dollars; <= is auto-approved, > requires manager approval

# device_id -> device details. `upfront` is the price charged to the next bill.
DEVICES = {
    "DEV-DUO": {"name": "iPhone Duo Star White 512GB", "upfront": 999},
    "DEV-PX": {"name": "Acme Pixel X", "upfront": 699},
    "DEV-GS": {"name": "Acme Universe S", "upfront": 899},
    "DEV-LT": {"name": "Acme Lite", "upfront": 299},
}


def get_device(device_id: str) -> dict | None:
    """Return device details by id (case-insensitive), or None if unknown."""
    if not device_id:
        return None
    lower_map = {did.lower(): did for did in DEVICES}
    canonical = lower_map.get(device_id.strip().lower())
    return DEVICES.get(canonical) if canonical else None


def canonical_device_id(device_id: str) -> str | None:
    """Return the canonical device id for a case-insensitive match, or None."""
    if not device_id:
        return None
    lower_map = {did.lower(): did for did in DEVICES}
    return lower_map.get(device_id.strip().lower())


def discount_decision(discount: float) -> dict:
    """Decide how a requested device discount is handled.

    Returns a dict:
      {"auto_approved": bool, "requires_approval": bool, "cap": AUTO_APPROVE_CAP}

    - discount <= cap -> auto_approved True, requires_approval False
    - discount  > cap -> auto_approved False, requires_approval True
    Negative discounts are treated as 0.
    """
    d = max(0.0, float(discount))
    within_cap = d <= AUTO_APPROVE_CAP
    return {
        "discount": d,
        "auto_approved": within_cap,
        "requires_approval": not within_cap,
        "cap": AUTO_APPROVE_CAP,
    }
