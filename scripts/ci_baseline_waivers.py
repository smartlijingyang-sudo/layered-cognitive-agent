"""Validate narrowly scoped, owner-assigned, expiring CI baseline waivers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_WAIVER_PATH = (
    Path(__file__).resolve().parent.parent / ".github" / "ci-baseline-waivers.json"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BaselineWaiverError(ValueError):
    """Raised when the waiver manifest is missing, malformed, or expired."""


@dataclass(frozen=True, slots=True)
class BaselineWaiver:
    owner: str
    expires: date
    reason: str
    output_sha256: str


def load_waivers(
    path: Path = DEFAULT_WAIVER_PATH,
    *,
    today: date | None = None,
) -> dict[str, BaselineWaiver]:
    """Load and validate every waiver; an expired entry fails closed."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BaselineWaiverError(f"cannot read waiver manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineWaiverError(f"invalid JSON in waiver manifest {path}: {exc}") from exc

    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise BaselineWaiverError("waiver manifest must be an object with version=1")
    entries = raw.get("waivers")
    if not isinstance(entries, dict):
        raise BaselineWaiverError("waiver manifest must contain a waivers object")

    current_date = today or date.today()
    validated: dict[str, BaselineWaiver] = {}
    for gate, entry in entries.items():
        if not isinstance(gate, str) or not gate.strip() or not isinstance(entry, dict):
            raise BaselineWaiverError("each waiver must have a non-empty gate name and object")
        owner = entry.get("owner")
        reason = entry.get("reason")
        expires_raw = entry.get("expires")
        fingerprint = entry.get("output_sha256")
        if not isinstance(owner, str) or not owner.strip():
            raise BaselineWaiverError(f"{gate}: owner is required")
        if not isinstance(reason, str) or not reason.strip():
            raise BaselineWaiverError(f"{gate}: reason is required")
        if not isinstance(expires_raw, str):
            raise BaselineWaiverError(f"{gate}: expires must be an ISO date")
        try:
            expires = date.fromisoformat(expires_raw)
        except ValueError as exc:
            raise BaselineWaiverError(f"{gate}: invalid expires date {expires_raw!r}") from exc
        if expires < current_date:
            raise BaselineWaiverError(
                f"{gate}: waiver expired on {expires.isoformat()} (owner={owner})"
            )
        if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
            raise BaselineWaiverError(f"{gate}: output_sha256 must be a lowercase SHA-256 digest")
        validated[gate] = BaselineWaiver(
            owner=owner.strip(),
            expires=expires,
            reason=reason.strip(),
            output_sha256=fingerprint,
        )
    return validated


def check_waiver(
    gate: str,
    output: str,
    waivers: dict[str, BaselineWaiver],
) -> tuple[bool, str]:
    """Allow only an exact known failing output; any drift remains blocking."""
    waiver = waivers.get(gate)
    if waiver is None:
        return False, f"{gate}: no waiver registered"
    actual = hashlib.sha256(output.encode("utf-8")).hexdigest()
    if actual != waiver.output_sha256:
        return (
            False,
            f"{gate}: output fingerprint changed (expected {waiver.output_sha256}, got {actual})",
        )
    return (
        True,
        f"temporarily waived until {waiver.expires.isoformat()} "
        f"(owner={waiver.owner}): {waiver.reason}",
    )


__all__ = ["BaselineWaiver", "BaselineWaiverError", "check_waiver", "load_waivers"]
