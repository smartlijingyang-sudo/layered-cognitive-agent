"""Assemble default operational skill tools for gateway agents."""

from __future__ import annotations

from lca.contracts.protocols import Sandbox, Tool
from lca.contracts.protocols.operational_skills import (
    SkillImporter,
    SkillPackageInstaller,
)
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.skills.factory import resolve_skill_importer
from lca.layer0_infra.tools.skills.activate_tool import SkillActivateTool
from lca.layer0_infra.tools.skills.exec_tool import SkillExecTool
from lca.layer0_infra.tools.skills.import_tool import SkillImportTool
from lca.layer0_infra.tools.skills.read_reference_tool import SkillReadReferenceTool
from lca.layer0_infra.tools.skills.search_tool import SkillSearchTool


def build_operational_skill_tools(
    *,
    importer: SkillImporter | None = None,
    store: SkillPackageInstaller | None = None,
    sandbox: Sandbox | None = None,
    file_store: FileStore | None = None,
) -> list[Tool]:
    if importer is None:
        default_importer = resolve_skill_importer(store=store)
        resolved_importer: SkillImporter = default_importer
        resolved_store = store if store is not None else default_importer.store
    elif store is not None:
        resolved_importer = importer
        resolved_store = store
    else:
        raise ValueError("自定义 SkillImporter 必须同时注入 SkillPackageInstaller")
    tools: list[Tool] = [
        SkillSearchTool(resolved_importer, resolved_store),
        SkillImportTool(resolved_importer),
        SkillActivateTool(resolved_store),
        SkillReadReferenceTool(resolved_store),
    ]
    if sandbox is not None:
        tools.append(
            SkillExecTool(
                sandbox=sandbox,
                store=resolved_store,
                file_store=file_store,
            )
        )
    return tools
