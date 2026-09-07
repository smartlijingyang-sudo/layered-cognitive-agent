"""Activation reference hashing.

Per ADR-0199 §2.2.2: activation_ref is the SSOT key that lets doctor /
replay / failure attribution locate the exact plan-bound closure.
Per C8: deterministic — no env, no PID, no time.

Hash inputs:
  plan_ref, graph_ref, plugin_set_ref, session_id
"""

from __future__ import annotations

import hashlib
import json
from typing import Final

# Algorithm — explicit so audits can read it. sha256 hex is 64 chars.
_ACTIVATION_HASH_ALGO: Final[str] = "sha256"
_ACTIVATION_HASH_NAMESPACE: Final[str] = "lca.activation.v1"


def compute_activation_ref(
    *,
    plan_ref: str,
    graph_ref: str,
    plugin_set_ref: str,
    session_id: str,
) -> str:
    """Compute a deterministic activation_ref.

    Order-independent (sorted keys), separator-pinned, no env/clock reads.
    Output: "<namespace>:<sha256-hex>"
    """
    payload = {
        "session_id": session_id,
        "plan_ref": plan_ref,
        "graph_ref": graph_ref,
        "plugin_set_ref": plugin_set_ref,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_ACTIVATION_HASH_NAMESPACE}:{digest}"


def is_activation_ref(value: str) -> bool:
    """Type guard — True iff value is a well-formed activation_ref."""
    prefix = f"{_ACTIVATION_HASH_NAMESPACE}:"
    if not value.startswith(prefix):
        return False
    hex_part = value[len(prefix) :]
    return len(hex_part) == 64 and all(c in "0123456789abcdef" for c in hex_part)


__all__ = ("compute_activation_ref", "is_activation_ref")
