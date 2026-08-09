"""Workspace-aware artifact closure for loop exit (ADR-0051)."""

from __future__ import annotations

from lca.layer0_infra.workspace import get_run_workspace


def synthesize_artifact_closure(*, fallback: str = "") -> str | None:
    """Return user-facing closure from workspace ledger, or None if empty."""
    workspace = get_run_workspace()
    if workspace is None:
        return fallback or None
    text = workspace.artifacts.closure_text()
    if text:
        return text
    return fallback or None
