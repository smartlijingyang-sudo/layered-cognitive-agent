"""Execution-plane prompt assembler — single pipeline for plane system roles.

Consolidates the former ``cognition/brain/prompt/sandbox_prompt.py`` into the
infrastructure layer. The assembler decides which plane blocks to render,
picks a :class:`PlanePromptStrategy` per plane, and always renders through the
same strategy pipeline. No Python string fallbacks live here.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.contracts.protocols import Tool
from lca.infrastructure.file.store import FileStore
from lca.infrastructure.runtime_plane.bindings.bindings import current_bindings, current_primary
from lca.infrastructure.runtime_plane.prompt.strategy import (
    MachinePlaneStrategy,
    PlanePromptStrategy,
    SandboxPlaneStrategy,
)
from lca.infrastructure.runtime_plane.resolve.resolve import (
    default_machine_ref,
    make_sandbox_ref,
    ref_of,
)
from lca.infrastructure.tools.lca_computer.types import CLOUD_SANDBOX_APIS, MACHINE_APIS

_STRATEGIES: dict[PlaneKind, PlanePromptStrategy] = {
    PlaneKind.SANDBOX: SandboxPlaneStrategy(),
    PlaneKind.MACHINE: MachinePlaneStrategy(),
}


def _strategy(kind: PlaneKind) -> PlanePromptStrategy:
    return _STRATEGIES[kind]


def _sandbox_plane() -> PlaneRef:
    bound = current_bindings()
    if bound is not None:
        ref = ref_of(bound, PlaneKind.SANDBOX)
        if ref is not None:
            return ref
    return make_sandbox_ref()


def _machine_plane() -> PlaneRef:
    bound = current_bindings()
    if bound is not None:
        ref = ref_of(bound, PlaneKind.MACHINE)
        if ref is not None:
            return ref
    return default_machine_ref()


def _tool_block(name: str, instructions: str) -> str:
    return (
        f'<tool name="{name}">\n<tool.instructions>\n{instructions}\n</tool.instructions>\n</tool>'
    )


def render_plane_role(
    plane: PlaneRef | None = None,
    *,
    store: FileStore | None = None,
) -> str:
    """Render the current/fallback plane's system-role text without ``<tool>`` wrap.

    Used for inline ``{{sandbox_environment_note}}``-style slots. Falls back to
    the cloud sandbox when no plane is bound, mirroring the legacy
    ``environment_note`` contract.
    """
    if plane is None:
        primary = current_primary()
        if primary is not None:
            return _strategy(primary.kind).render(primary, store=store)
        plane = _sandbox_plane()
    return _strategy(plane.kind).render(plane, store=store)


def render_plane_prompt(
    tools: Sequence[Tool] = (),
    store: FileStore | None = None,
) -> str:
    """Render computer-environment ``<tool>`` blocks. One per bound face.

    Mirrors the former ``build_cloud_sandbox_prompt`` contract: tool names are
    the addressing authority when present; otherwise the bound plane decides.
    """
    names = {getattr(tool, "name", "") for tool in tools}
    cloud_values = {api.value for api in CLOUD_SANDBOX_APIS}
    machine_values = {f"local_{api.value}" for api in MACHINE_APIS}
    bound = current_primary()
    if names:
        want_cloud = any(name in cloud_values for name in names)
        want_machine = any(name in machine_values for name in names)
    elif bound is not None:
        want_cloud = bound.kind is PlaneKind.SANDBOX
        want_machine = bound.kind is PlaneKind.MACHINE
    else:
        want_cloud = True
        want_machine = False

    blocks: list[str] = []
    if want_cloud:
        plane = _sandbox_plane()
        strategy = _strategy(PlaneKind.SANDBOX)
        rendered = strategy.render(plane, store=store)
        if rendered:
            blocks.append(_tool_block(strategy.tool_name, rendered))
    if want_machine:
        plane = _machine_plane()
        strategy = _strategy(PlaneKind.MACHINE)
        rendered = strategy.render(plane, store=store)
        if rendered:
            blocks.append(_tool_block(strategy.tool_name, rendered))
    return "\n".join(blocks)


__all__ = ["render_plane_prompt", "render_plane_role"]
