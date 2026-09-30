"""assistant.skill_overlay —— 0048 拉取 seam(URL / 本地目录)。

网络与本地源统一经 ``DiskSkillPackageStore.install_package`` 校验后落
staging;网络路径由 ``SkillImporter.import_from_url`` 治理(host
allowlist / 大小上限 / ZIP 安全解压)。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.protocols.memory.operational_skills import (
    SkillImporter,
    SkillImportError,
    SkillPackage,
)
from lca.infrastructure.skills.disk.store import (
    DiskSkillPackageStore,
    safe_rel_path,
    sanitize_skill_id,
)
from lca.infrastructure.skills.frontmatter.frontmatter import skill_title, split_frontmatter
from lca.infrastructure.skills.http.importer import HttpSkillImporter
from lca.infrastructure.skills.settings.settings import SkillSettings


def _default_url_importer(staging_root: Path) -> SkillImporter:
    """默认 URL 拉取器:0048 ``HttpSkillImporter`` 绑定 Home 内 staging store。

    ``cache_dir`` 显式注入 = 拉取产物只落 staging,不触达全局
    skills store(pydantic-settings 中 init 值优先于环境变量)。
    """
    return HttpSkillImporter(
        store=DiskSkillPackageStore(SkillSettings(cache_dir=staging_root)),
        settings=SkillSettings(cache_dir=staging_root),
    )


def _import_local_path(staging_root: Path, local_path: str) -> SkillPackage:
    """本地目录源:读 ``SKILL.md`` + 资源,经 0048 ``install_package`` 校验落 staging。

    校验(大小上限 / 资源路径安全 / skill_id 合法性)全部由
    ``DiskSkillPackageStore.install_package`` 执行,与 URL 路径同一入口。
    """
    src = Path(local_path)
    if not src.is_dir():
        raise SkillImportError(f"local_path 不是已存在目录: {local_path}")
    skill_md = next((p for p in (src / "SKILL.md", src / "skill.md") if p.is_file()), None)
    if skill_md is None:
        raise SkillImportError(f"local_path 缺 SKILL.md: {local_path}")
    text = skill_md.read_text(encoding="utf-8")
    resources: dict[str, bytes] = {}
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path == skill_md:
            continue
        rel = safe_rel_path(str(path.relative_to(src)))
        if rel:
            resources[rel] = path.read_bytes()
    meta, _ = split_frontmatter(text)
    skill_id = sanitize_skill_id(skill_title(meta, src.name))
    store = DiskSkillPackageStore(SkillSettings(cache_dir=staging_root))
    return store.install_package(
        skill_id=skill_id,
        skill_md_text=text,
        resource_files=resources,
        source_url=str(src),
    )
