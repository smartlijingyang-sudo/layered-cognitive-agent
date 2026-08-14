"""Cloud sandbox prompt assembly for agent reasoner (L1).

Aligned with LobeHub ``ToolSystemRoleProvider`` + ``pluginPrompts``:
the cloud sandbox system role is wrapped as a ``<tool>`` with
``<tool.instructions>`` inside the ``<tools>`` block, matching the
format used by ``@lobechat/prompts`` ``toolPrompt()``.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.prompt import render_cloud_sandbox_system_role
from lca.layer0_infra.sandbox.surface import plane_system_role
from lca.layer0_infra.tools.lca_computer.manifest import LOCAL_SYSTEM_ID as _LOCAL_SYSTEM_ID
from lca.layer0_infra.tools.lca_computer.types import CLOUD_SANDBOX_APIS, MACHINE_APIS
from lca.layer0_infra.tools.lca_sandbox import IDENTIFIER as _CLOUD_SANDBOX_ID
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt

_CLOUD_SANDBOX_TOOL_NAME = _CLOUD_SANDBOX_ID
_LOCAL_SYSTEM_TOOL_NAME = _LOCAL_SYSTEM_ID


def build_cloud_sandbox_prompt(tools: Sequence[Tool]) -> str:
    """Computer-environment ``<tool>`` blocks. One per registered face."""
    names = {t.name for t in tools}
    blocks: list[str] = []
    cloud_values = {api.value for api in CLOUD_SANDBOX_APIS}
    if any(name in cloud_values for name in names):
        store: FileStore = get_default_file_store()
        template = load_builtin_prompt("cloud_sandbox_system_role")
        rendered = render_cloud_sandbox_system_role(template, store=store)
        blocks.append(_tool_block(_CLOUD_SANDBOX_TOOL_NAME, rendered))
    machine_values = {f"local_{api.value}" for api in MACHINE_APIS}
    if any(name in machine_values for name in names):
        rendered = _machine_role()
        if rendered:
            blocks.append(_tool_block(_LOCAL_SYSTEM_TOOL_NAME, rendered))
    return "\n".join(blocks)


def _machine_role() -> str:
    from lca.layer0_infra.plane.machine import resolve_machine
    from lca.layer0_infra.plane.resolve import ref_of
    from lca.layer0_infra.plane.scope import current_bindings

    bound = current_bindings()
    machine = ref_of(bound, PlaneKind.MACHINE) if bound is not None else None
    if machine is None:
        machine = resolve_machine()
    if machine is None:
        return (
            "You are operating on the user's machine. "
            "Working directory is the machine root. Write deliverables under outputs/."
        )
    return plane_system_role(machine)


def _tool_block(name: str, instructions: str) -> str:
    return (
        f'<tool name="{name}">\n<tool.instructions>\n{instructions}\n</tool.instructions>\n</tool>'
    )
