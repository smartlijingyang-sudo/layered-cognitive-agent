"""Shared default tool set for gateway casting and L4 auto-casting."""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.tools.skills.tool_set import build_operational_skill_tools
from lca.layer0_infra.tools.write_file_tool import WriteFileTool

# Low-level sandbox tools remain importable for tests and internal runtime;
# they are intentionally excluded from the LLM-facing default set (LobeHub-aligned:
# agents use activate_skill → run_skill_script, not raw sandbox_execute).


def build_default_tools(store: FileStore | None = None) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    Production defaults (skill-first, LobeHub-aligned):
    - ``write_file`` — downloadable text products
    - operational skill tools — search / import / activate / read / execScript
    - ``run_skill_script`` when execution backend is configured (Onlyboxes)

    Raw ``sandbox_execute`` / ``sandbox_inspect`` are internal execution-plane
    details; the model sees ``run_skill_script`` as ``runCommand``-style exec.
    """
    file_store = store if store is not None else get_default_file_store()
    sandbox = resolve_sandbox()
    return [
        WriteFileTool(store=file_store),
        *build_operational_skill_tools(sandbox=sandbox, file_store=file_store),
    ]
