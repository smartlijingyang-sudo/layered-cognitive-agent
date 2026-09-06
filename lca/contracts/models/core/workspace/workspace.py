"""Run Workspace contracts — run-scoped artifact ledger (ADR-0051)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkspaceArtifact:
    """One deliverable registered in the run workspace."""

    name: str
    mime_type: str
    url: str = ""
    size_bytes: int = 0
    tool_name: str = ""
    agent_role: str = ""
    guest_path: str = ""


@dataclass(frozen=True)
class ArtifactLedgerSnapshot:
    """Immutable view of workspace artifacts for handoff / closure."""

    artifacts: tuple[WorkspaceArtifact, ...] = field(default_factory=tuple)
