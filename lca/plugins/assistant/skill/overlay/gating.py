"""assistant.skill_overlay —— 0067 三闸 + 落盘/摘要/修订辅助。

安装与编辑路径共用的纯校验/辅助函数与常量:

- 常量:``_STAGING_DIR_NAME`` / ``_SKILLS_DIGEST_PREFIX`` /
  ``_ACTIVATABLE_STATES``(ADR-0187 §3 D6);
- ``_gate_package`` —— ADR-0067 三闸 + ``DRAFT → VERIFIED`` 迁移;
- ``_place_package`` / ``_mark_local`` —— staging → Home skills 落盘;
- ``_package_digest`` / ``_revision_of`` —— manifest 摘要与修订读取。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.atoms.artifact.state import ArtifactState
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.journal.artifact import (
    CapabilityArtifact,
    make_capability_artifact,
    migrate_to_verified,
)
from lca.contracts.protocols.memory.operational_skills import (
    SKILL_MAX_CONTENT_CHARS,
    SKILL_MAX_RESOURCES,
    SkillImportError,
    SkillPackage,
)
from lca.infrastructure.skills.disk.store import safe_rel_path, sanitize_skill_id

_STAGING_DIR_NAME = ".staging"
"""Home 内 staging 子目录名(隐藏目录;``list_installed`` 跳过)。"""

_SKILLS_DIGEST_PREFIX = "skills/"
"""manifest ``digests`` 中 skills 索引条目的 key 前缀。"""

_ACTIVATABLE_STATES = frozenset({ArtifactState.VERIFIED.value, ArtifactState.ACTIVE.value})
"""``activate`` 接受的状态闭集(ADR-0187 §3 D6)。"""


def _gate_package(package: SkillPackage) -> CapabilityArtifact:
    """ADR-0067 三闸 + ``DRAFT → VERIFIED`` 迁移;任一失败抛 ``SkillImportError``。

    - identity —— skill_id 合法、内容 digest 固定、来源 provenance 非空;
    - invariant —— 0048 结构上限(内容长度 / 资源数 / 路径白名单)不破坏;
    - experiment —— 落点限助理域 scope,安装不携带任何 grant 扩张。

    状态机迁移经 ``migrate_to_verified``(0067 唯一提升入口);非法迁移
    抛 ``InvalidStateTransitionError``。
    """
    if not package.skill_id or sanitize_skill_id(package.skill_id) != package.skill_id:
        raise SkillImportError(f"identity 闸失败: skill_id 非法 {package.skill_id!r}")
    if not package.content_hash:
        raise SkillImportError("identity 闸失败: 包缺内容 digest")
    if not package.source_url:
        raise SkillImportError("identity 闸失败: 缺安装来源")
    if len(package.content) > SKILL_MAX_CONTENT_CHARS:
        raise SkillImportError("invariant 闸失败: SKILL.md 超过上限")
    if len(package.resource_paths) > SKILL_MAX_RESOURCES:
        raise SkillImportError("invariant 闸失败: 资源数超过上限")
    for rel in package.resource_paths:
        if not rel or safe_rel_path(rel) != rel:
            raise SkillImportError(f"invariant 闸失败: 资源路径非法 {rel!r}")

    artifact = make_capability_artifact(
        logical_id=f"assistant.skill:{package.skill_id}",
        content=package.content_hash,
        scope=Scope.AGENT,
        state=ArtifactState.DRAFT,
        grants=(),
        metadata={"source_url": package.source_url, "version": package.version},
    )
    return migrate_to_verified(artifact)


def _place_package(staging_root: Path, skills_root: Path, skill_id: str) -> Path:
    """把 staging 中的完整包移入 ``{home}/skills/<skill_id>/``(覆盖式重装)。"""
    src = staging_root / skill_id
    if not (src / "manifest.json").is_file() or not (src / "SKILL.md").is_file():
        raise SkillImportError(f"staging 包不完整: {src}")
    skills_root.mkdir(parents=True, exist_ok=True)
    dest = skills_root / skill_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))
    return dest


def _package_digest(package: SkillPackage) -> str:
    """``sha256:<hex>`` 形式的包内容摘要(manifest digests 条目同形)。"""
    digest = package.content_hash
    return digest if digest.startswith("sha256:") else f"sha256:{digest}"


def _mark_local(skill_dir: Path) -> None:
    """把落盘包的 ``manifest.json`` 标记为 ``source: "local"``（ADR-0243 D2）。

    ``global_link`` 包在编辑（COW）后变成独立副本，来源标记必须更新。
    """
    meta_path = skill_dir / "manifest.json"
    if not meta_path.is_file():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(meta, dict):
        meta["source"] = "local"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _revision_of(manifest: Mapping[str, Any]) -> int:
    raw = manifest.get("revision_seq", 0)
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return 0
