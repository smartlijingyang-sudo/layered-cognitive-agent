"""Assemble default operational skill tools for gateway agents."""

from __future__ import annotations

from lca.contracts.protocols import Sandbox, Tool
from lca.contracts.protocols.memory.operational_skills import (
    SkillImporter,
    SkillPackageInstaller,
    SkillPackageStore,
)
from lca.infrastructure.file.store import FileStore, LocalFileStore
from lca.infrastructure.skills.factory.factory import (
    resolve_skill_importer,
    resolve_skill_store,
)
from lca.infrastructure.tools.skills.activate.tool import SkillActivateTool
from lca.infrastructure.tools.skills.exec.tool import SkillExecTool
from lca.infrastructure.tools.skills.importer.import_tool import SkillImportTool
from lca.infrastructure.tools.skills.read.reference_tool import SkillReadReferenceOnceTool
from lca.infrastructure.tools.skills.search.tool import SkillSearchTool


def build_operational_skill_tools(
    *,
    importer: SkillImporter | None = None,
    store: SkillPackageStore | None = None,
    installer: SkillPackageInstaller | None = None,
    sandbox: Sandbox | None = None,
    file_store: FileStore | None = None,
) -> list[Tool]:
    """Assemble operational skill tools.

    ``store`` is the read view used by search / activate / read / exec tools;
    it may be an assistant-merged read-through store. ``installer`` is the
    write seam for ``import_skill``; it defaults to the global disk store so
    imports never write through a read-only view.
    """
    if importer is None:
        resolved_installer = installer if installer is not None else resolve_skill_store()
        resolved_importer: SkillImporter = resolve_skill_importer(store=resolved_installer)
        resolved_store = store if store is not None else resolved_installer
    elif store is not None:
        resolved_importer = importer
        resolved_store = store
    else:
        raise ValueError("自定义 SkillImporter 必须同时注入 SkillPackageInstaller")
    tools: list[Tool] = [
        SkillSearchTool(resolved_importer, resolved_store),
        SkillImportTool(resolved_importer),
        SkillActivateTool(resolved_store),
        SkillReadReferenceOnceTool(resolved_store),
    ]
    if sandbox is not None:
        tools.append(
            SkillExecTool(
                sandbox=sandbox,
                store=resolved_store,
                file_store=file_store if file_store is not None else LocalFileStore(),
            )
        )
    return tools
