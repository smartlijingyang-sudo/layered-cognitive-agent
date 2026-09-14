"""Pure delivery predicates — evidence fold only (ADR-0196)."""

from __future__ import annotations


def delivery_satisfied(
    *,
    artifact_count: int,
    producer_ok: int,
    has_user_visible_delivery: bool,
) -> tuple[bool, str]:
    if artifact_count >= 1 and producer_ok >= 1:
        return True, "artifact + producer success"
    if has_user_visible_delivery:
        return True, "substantive tool output ready for respond"
    return False, "insufficient delivery signals"


__all__ = ["delivery_satisfied"]
