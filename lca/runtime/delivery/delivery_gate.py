"""Delivery Gate — Physical stat verification and ephemeral path leak guard.

Enforces:
1. Every deliverable mentioned via sandbox://workspace/... must physically exist on disk (INV-FS-05).
2. The agent cannot leak /tmp or internal scratch paths to the user (INV-FS-06).
"""

from __future__ import annotations

import re
from pathlib import Path


class DeliveryError(Exception):
    """Base exception for delivery contract violations."""


class DeliveryVerificationError(DeliveryError):
    """Raised when a delivered attachment does not physically exist on disk."""


class DeliverySecurityError(DeliveryError):
    """Raised when an ephemeral path (e.g. /tmp) is handed to the user as a deliverable."""


_SANDBOX_LINK_RE = re.compile(r"\[[^\]]*\]\((?:sandbox://workspace/)?([^)]+)\)")
_TMP_LEAK_RE = re.compile(r"\[[^\]]*\]\((?:sandbox://workspace/)?/?(?:tmp|var/tmp)/[^)]+\)")


def extract_delivery_links(text: str) -> list[str]:
    """Extract clean relative workspace paths from sandbox://workspace/... links in text."""
    matches = re.findall(r"\[[^\]]*\]\(sandbox://workspace/([^)]+)\)", text)
    clean_paths: list[str] = []
    for m in matches:
        clean = m.strip().lstrip("/")
        clean_paths.append(clean)
    return clean_paths


def verify_delivery_attachments(text: str, workspace_root: Path | str) -> bool:
    """Verify that all sandbox attachments physically exist and no ephemeral paths are leaked."""
    root = Path(workspace_root)

    # 1. Check for ephemeral /tmp leaks in any markdown link
    if _TMP_LEAK_RE.search(text):
        raise DeliverySecurityError(
            "Security violation: Ephemeral /tmp or /var/tmp path detected in deliverable link. "
            "Deliverables must be written in-place under workspace/your_files/ or goals/<slug>/files/."
        )

    # 2. Check for physical existence of sandbox://workspace/ attachments
    links = extract_delivery_links(text)
    for rel_path in links:
        target = (root / rel_path).resolve()
        # Security sanity: must stay within workspace
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise DeliverySecurityError(
                f"Security violation: path traversal detected outside workspace root: '{rel_path}'"
            )

        if not target.exists():
            raise DeliveryVerificationError(
                f"Deliverable verification failed: file '{rel_path}' does not physically exist on disk "
                f"at '{target}'. Agent is forbidden from claiming delivery of non-existent files."
            )

    return True


__all__ = [
    "DeliveryError",
    "DeliverySecurityError",
    "DeliveryVerificationError",
    "extract_delivery_links",
    "verify_delivery_attachments",
]
