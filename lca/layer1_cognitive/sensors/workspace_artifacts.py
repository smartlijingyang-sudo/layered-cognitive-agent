"""WorkspaceArtifactsSensor — emits a ``workspace_artifacts`` ContextItem (PR3b).

Mandatory sensor (per spec §3.5: workspace-artifacts 必做 — 非可选).  The
gate ``ArtifactRespondInjector`` and the ``TerminalRespondGate`` read
from this manifest item at runtime (PR6 §6.2).  The sensor is the only
authorized live workspace read performed by the Hub; the gates do not
issue live reads.
"""

from __future__ import annotations

from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Sensor
from lca.layer0_infra.workspace import get_run_workspace


class WorkspaceArtifactsSensor(Sensor):
    """Snapshot the workspace artifact ledger into a context item."""

    async def read(self, state: AgentState) -> list[ContextItem]:
        workspace = get_run_workspace()
        if workspace is None:
            return []
        snapshot = workspace.artifacts.snapshot()
        if not snapshot.artifacts:
            return []
        # Render minimal JSON-able form for the manifest.
        payload = [
            {
                "path": art.path,
                "url": art.url,
                "mime": art.mime,
                "size": art.size,
            }
            for art in snapshot.artifacts
        ]
        return [
            ContextItem(
                kind="workspace_artifacts",
                payload=payload,
                provenance="workspace_artifacts_sensor",
            )
        ]


def build_workspace_artifacts_sensor() -> Sensor:
    """Named factory: ``sensor.workspace-artifacts`` (PR3b)."""
    return WorkspaceArtifactsSensor()
