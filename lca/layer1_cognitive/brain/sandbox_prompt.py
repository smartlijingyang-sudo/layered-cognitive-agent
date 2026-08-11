"""Cloud sandbox prompt assembly for agent reasoner (L1).

Aligned with LobeHub ``ToolSystemRoleProvider`` + ``pluginPrompts``:
the cloud sandbox system role is wrapped as a ``<tool>`` with
``<tool.instructions>`` inside the ``<tools>`` block, matching the
format used by ``@lobechat/prompts`` ``toolPrompt()``.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.prompt import render_cloud_sandbox_system_role
from lca.layer0_infra.tools.computer.specs import COMPUTER_TOOL_NAMES
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt

_CLOUD_SANDBOX_TOOL_NAME = "lobe-cloud-sandbox"


def build_cloud_sandbox_prompt(tools: Sequence[Tool]) -> str:
    """Cloud sandbox ``<tool>`` block with ``<tool.instructions>``, or empty.

    Returns LobeHub-compatible XML::

        <tool name="lobe-cloud-sandbox">
        <tool.instructions>
        {rendered system role}
        </tool.instructions>
        </tool>
    """
    if not any(t.name in COMPUTER_TOOL_NAMES for t in tools):
        return ""
    store: FileStore = get_default_file_store()
    template = load_builtin_prompt("cloud_sandbox_system_role")
    rendered = render_cloud_sandbox_system_role(template, store=store)
    return (
        f'<tool name="{_CLOUD_SANDBOX_TOOL_NAME}">\n'
        f"<tool.instructions>\n"
        f"{rendered}\n"
        f"</tool.instructions>\n"
        f"</tool>"
    )
