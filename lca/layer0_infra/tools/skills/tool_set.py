"""Assemble default operational skill tools for gateway agents."""

from __future__ import annotations

from lca.contracts.protocols import Sandbox, Tool
from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.skills.factory import resolve_skill_importer
from lca.layer0_infra.skills.http_importer import HttpSkillImporter
from lca.layer0_infra.tools.skills.activate_tool import SkillActivateTool
from lca.layer0_infra.tools.skills.exec_tool import SkillExecTool
from lca.layer0_infra.tools.skills.import_tool import SkillImportTool
from lca.layer0_infra.tools.skills.read_reference_tool import SkillReadReferenceTool
from lca.layer0_infra.tools.skills.search_tool import SkillSearchTool


def build_operational_skill_tools(
    *,
    importer: HttpSkillImporter | None = None,
    store: SkillPackageStore | None = None,
    sandbox: Sandbox | None = None,
    file_store: FileStore | None = None,
) -> list[Tool]:
    resolved_importer = importer if importer is not None else resolve_skill_importer()
    resolved_store = store if store is not None else resolved_importer.store
    tools: list[Tool] = [
        SkillSearchTool(resolved_importer),
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
