"""Cloud sandbox prompt assembly for agent reasoner (L1)."""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.prompt import render_cloud_sandbox_system_role
from lca.layer0_infra.tools.computer.specs import COMPUTER_TOOL_NAMES
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt


def build_cloud_sandbox_prompt(tools: Sequence[Tool]) -> str:
    """Full cloud sandbox system block, or empty when computer tools are disabled."""
    if not any(t.name in COMPUTER_TOOL_NAMES for t in tools):
        return ""
    store: FileStore = get_default_file_store()
    template = load_builtin_prompt("cloud_sandbox_system_role")
    return render_cloud_sandbox_system_role(template, store=store)
