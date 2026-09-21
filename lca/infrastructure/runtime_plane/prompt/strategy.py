"""Execution-plane prompt strategies — Strategy pattern (ADR plan A).

One strategy per plane kind owns how that plane's system-role block is
rendered. The prompt assembler picks a strategy by plane kind and always runs
the same ``render(plane)`` pipeline, so there is no hard-coded fallback text
outside templates.
"""

from __future__ import annotations

from typing import Protocol

from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.attachment.system.role_renderer import render_system_role
from lca.infrastructure.file.store import FileStore
from lca.infrastructure.runtime_plane.preinstall.prompt import render_preinstalled_block
from lca.infrastructure.tools.lca_computer.manifest import LOCAL_SYSTEM_ID
from lca.infrastructure.tools.lca_sandbox import IDENTIFIER as CLOUD_SANDBOX_ID


class PlanePromptStrategy(Protocol):
    """Strategy contract: one renderer per execution-plane kind."""

    kind: PlaneKind
    tool_name: str

    def render(self, plane: PlaneRef, *, store: FileStore | None = None) -> str: ...


class SandboxPlaneStrategy:
    """Render the cloud-sandbox system role from its template."""

    kind = PlaneKind.SANDBOX
    tool_name = CLOUD_SANDBOX_ID

    def render(self, plane: PlaneRef, *, store: FileStore | None = None) -> str:
        return render_system_role(
            plane,
            template_name="cloud_sandbox_system_role",
            store=store,
        ).text


class MachinePlaneStrategy:
    """Render the machine system role: template + preinstalled + home note."""

    kind = PlaneKind.MACHINE
    tool_name = LOCAL_SYSTEM_ID

    def render(self, plane: PlaneRef, *, store: FileStore | None = None) -> str:
        result = render_system_role(
            plane,
            template_name="machine_system_role",
            store=store,
            extra_placeholders={
                "{{preinstalled}}": render_preinstalled_block(plane=PlaneKind.MACHINE),
            },
        )
        rendered = result.text
        if plane.home:
            rendered += f"\n- User home (for spoken locations like Desktop only): `{plane.home}`"
        return rendered


__all__ = [
    "MachinePlaneStrategy",
    "PlanePromptStrategy",
    "SandboxPlaneStrategy",
]
