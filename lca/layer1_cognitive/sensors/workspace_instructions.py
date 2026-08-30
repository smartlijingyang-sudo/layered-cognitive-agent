"""WorkspaceInstructionsSensor — emit ``AGENTS.md`` content as a manifest item (PR13).

The sensor reads the project-level ``AGENTS.md`` (or any path supplied via
settings) and publishes its content as a ``workspace_instructions``
``ContextItem``.  A missing file is a no-op (the manifest simply lacks
that item) so cold-start and CI environments do not error.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Sensor

DEFAULT_AGENTS_MD_PATH = Path("./AGENTS.md")


class WorkspaceInstructionsSensor(Sensor):
    """Publish ``AGENTS.md`` content into the manifest (PR13)."""

    def __init__(
        self,
        *,
        path: Path | str | None = None,
    ) -> None:
        self._path = Path(path) if path is not None else DEFAULT_AGENTS_MD_PATH

    async def read(self, state: AgentState) -> list[ContextItem]:
        del state
        if not self._path.is_file():
            return []
        try:
            content = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        return [
            ContextItem(
                kind="workspace_instructions",
                payload=content,
                provenance="workspace_instructions_sensor",
            )
        ]


def build_workspace_instructions_sensor() -> Sensor:
    """Named factory: ``sensor.workspace-instructions`` (PR13)."""
    return WorkspaceInstructionsSensor()
