"""assistant.skill_overlay —— 0067 三闸 + 落盘/摘要/修订辅助。

安装与编辑路径共用的纯校验/辅助函数与常量:

- 常量:``_STAGING_DIR_NAME`` / ``_SKILLS_DIGEST_PREFIX`` /
  ``_ACTIVATABLE_STATES``(ADR-0187 §3 D6)/ ``_GLOBAL_LINK_SOURCE``(ADR-0243 D2);
- ``_gate_package`` —— ADR-0067 三闸 + ``DRAFT → VERIFIED`` 迁移;
- ``_place_package`` / ``_mark_local`` —— staging → Home skills 落盘;
- ``_link_global_package`` / ``_mark_global_link`` / ``_is_global_link`` ——
  全局库 → staging 硬链接物化(ADR-0243 D1 re-link);
- ``_package_digest`` / ``_revision_of`` —— manifest 摘要与修订读取。
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.atoms.artifact.state import ACTIVATABLE_STATES, ArtifactState
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

_GLOBAL_LINK_SOURCE = "global_link"
"""``source`` 标记值:包是全局库的硬链接视图(ADR-0243 D2)。"""

_ACTIVATABLE_STATES = ACTIVATABLE_STATES  # RA-055: 共享谓词的别名（overlay/__init__ 重导出保持兼容）
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


def _is_global_link(entry: Any) -> bool:
    """Home manifest ``skills`` 索引条目是否为全局库硬链接（ADR-0243 D2）。"""
    return isinstance(entry, dict) and entry.get("source") == _GLOBAL_LINK_SOURCE


def _link_global_package(global_root: Path, staging_root: Path, skill_id: str) -> Path:
    """把全局包硬链接进 staging（与 ``_copy_inherited_snapshot`` 同一物化惯用法）。

    链接而非复制 = ADR-0243 D1 的空间不膨胀前提;落盘由 ``_place_package`` 完成，
    使全局包在整个 re-link 过程中始终不被触碰。
    """
    dest = staging_root / skill_id
    shutil.copytree(
        global_root / skill_id,
        dest,
        dirs_exist_ok=True,
        copy_function=os.link,
    )
    _mark_global_link(dest)
    return dest


def _mark_global_link(skill_dir: Path) -> None:
    """把落盘包的 ``manifest.json`` 标为 ``source: "global_link"``（ADR-0243 D2）。

    先 unlink 再写:``manifest.json`` 此刻仍是全局包的硬链接,原地写会穿到全局
    inode（``_mark_local`` 的调用点是 COW 之后的私有目录,无此约束）。
    """
    meta_path = skill_dir / "manifest.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["source"] = _GLOBAL_LINK_SOURCE
    meta_path.unlink()
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
