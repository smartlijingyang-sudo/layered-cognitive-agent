"""Disk-backed SkillPackageInstaller — content-addressed install tree."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from lca.contracts.protocols.memory.operational_skills import (
    SKILL_MAX_CONTENT_CHARS,
    SKILL_MAX_RESOURCE_BYTES,
    SkillContractError,
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageInstaller,
    SkillPackageStore,
)
from lca.infrastructure.path import expand_user_path
from lca.infrastructure.skills.frontmatter.frontmatter import (
    parse_references_field,
    skill_title,
    split_frontmatter,
)
from lca.infrastructure.skills.settings.settings import SkillSettings, get_skill_settings

_MANIFEST = "manifest.json"
_SKILL_MD = "SKILL.md"
_RESOURCES = "resources"
_SKILL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def sanitize_skill_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw.strip()).strip("-")
    if not cleaned or not _SKILL_ID_RE.match(cleaned):
        raise ValueError(f"非法 skill_id: {raw!r}")
    return cleaned


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DiskSkillPackageStore(SkillPackageInstaller, SkillPackageStore):
    """实现完整安装接缝，并持久化技能包到 ``settings.cache_dir/<skill_id>/``。"""

    def __init__(self, settings: SkillSettings | None = None) -> None:
        self._settings = settings if settings is not None else get_skill_settings()
        self._root: Path = expand_user_path(self._settings.cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        entries: list[SkillIndexEntry] = []
        if not self._root.is_dir():
            return ()
        for child in sorted(self._root.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / _MANIFEST
            if not manifest_path.is_file():
                continue
            try:
                meta = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            skill_id = str(meta.get("skill_id") or child.name)
            entries.append(
                SkillIndexEntry(
                    skill_id=skill_id,
                    name=str(meta.get("name") or skill_id),
                    summary=str(meta.get("summary") or ""),
                    source_url=str(meta.get("source_url") or ""),
                    version=str(meta.get("version") or ""),
                )
            )
        return tuple(entries)

    def get(self, skill_id: str) -> SkillPackage:
        sid = sanitize_skill_id(skill_id)
        manifest_path = self._root / sid / _MANIFEST
        skill_md_path = self._root / sid / _SKILL_MD
        if not manifest_path.is_file() or not skill_md_path.is_file():
            raise SkillNotFoundError(f"技能库中不存在 skill_id：{sid}")
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        body = skill_md_path.read_text(encoding="utf-8")
        raw_paths = meta.get("resource_paths")
        resource_paths = tuple(str(p) for p in raw_paths) if isinstance(raw_paths, list) else ()
        raw_refs = meta.get("references")
        references = tuple(str(p) for p in raw_refs) if isinstance(raw_refs, list) else ()
        return SkillPackage(
            skill_id=sid,
            name=str(meta.get("name") or sid),
            summary=str(meta.get("summary") or ""),
            content=body,
            resource_paths=resource_paths,
            source_url=str(meta.get("source_url") or ""),
            content_hash=str(meta.get("content_hash") or ""),
            version=str(meta.get("version") or ""),
            references=references,
        )

    def read_resource(self, skill_id: str, rel_path: str) -> str:
        package = self.get(skill_id)
        # resource_paths 存 ``resources/`` 前缀的 skill 根相对路径；
        # 调用方可能传扁平名或带前缀名，统一归一化后检查。
        normalized = _to_resource_rel(safe_rel_path(rel_path))
        if normalized not in package.resource_paths:
            raise SkillNotFoundError(
                f"技能 {skill_id!r} 中不存在资源路径 {rel_path!r}（不在白名单内）"
            )
        data = self._read_resource_bytes(skill_id, normalized)
        return data.decode("utf-8", errors="replace")

    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        package = self.get(skill_id)
        out: dict[str, bytes] = {}
        for rel in package.resource_paths:
            # 挂载键带 ``resources/`` 前缀，与 SKILL.md references 声明一致，
            # 使 run_skill_script 在 skill 根目录执行 ``resources/<file>`` 可达。
            out[rel] = self._read_resource_bytes(skill_id, rel)
        return out

    def _read_resource_bytes(self, skill_id: str, rel_path: str) -> bytes:
        # 物理布局: resources/<flat>；resource_paths 的 ``resources/`` 前缀在此剥离。
        storage_rel = _strip_resources_prefix(safe_rel_path(rel_path))
        path = self._root / sanitize_skill_id(skill_id) / _RESOURCES / storage_rel
        if not path.is_file():
            raise SkillNotFoundError(f"资源文件不存在: {rel_path}")
        data = path.read_bytes()
        if len(data) > SKILL_MAX_RESOURCE_BYTES:
            raise SkillNotFoundError(f"资源文件过大: {rel_path}")
        return data

    def install_package(
        self,
        *,
        skill_id: str,
        skill_md_text: str,
        resource_files: dict[str, bytes],
        source_url: str,
        version: str = "",
    ) -> SkillPackage:
        sid = sanitize_skill_id(skill_id)
        if len(skill_md_text) > SKILL_MAX_CONTENT_CHARS:
            raise ValueError(f"SKILL.md 超过上限 {SKILL_MAX_CONTENT_CHARS} 字符")

        meta_front, body = split_frontmatter(skill_md_text)
        # ADR-0214 §7: SKILL.md frontmatter 必须声明 references(可空)。
        # split_frontmatter 跳过列表值,二次检查 parse_references_field;
        # 两份都缺失才 fail-loud。
        if "references" not in meta_front and not parse_references_field(skill_md_text):
            raise SkillContractError(
                f"SKILL.md frontmatter 缺 'references' 字段: {sid!r}"
                " — 在 frontmatter 里加 'references: []' 声明打包清单。"
            )
        name = skill_title(meta_front, sid)
        summary = meta_front.get("description", "").strip()
        digest = content_hash(skill_md_text.encode("utf-8"))

        dest = self._root / sid
        resources_dir = dest / _RESOURCES
        if dest.exists():
            for sub in dest.iterdir():
                if sub.is_file():
                    sub.unlink()
                elif sub.is_dir():
                    _rmtree(sub)
        resources_dir.mkdir(parents=True, exist_ok=True)

        normalized_resources: list[str] = []
        for rel, data in sorted(resource_files.items()):
            clean = safe_rel_path(rel)
            if not clean:
                continue
            if len(data) > SKILL_MAX_RESOURCE_BYTES:
                raise ValueError(f"资源 {clean} 超过单文件上限")
            # 落盘用扁平相对路径；manifest 记录 ``resources/`` 前缀的声明路径。
            storage_rel = _strip_resources_prefix(clean)
            out_path = resources_dir / storage_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            normalized_resources.append(_to_resource_rel(clean))

        # ADR-0214 §7: 校验 references 列表里的所有路径必须落到 _root/<sid>/_RESOURCES
        # 或 _root/<sid>/(SKILL.md 同级) — 不存在就 fail-loud。
        declared_refs = parse_references_field(skill_md_text)
        for ref in declared_refs:
            candidate = (dest / ref).resolve()
            if not candidate.is_relative_to(dest.resolve()):
                raise SkillContractError(
                    f"SKILL.md references[{ref!r}] 越界 — 必须落在 {sid!r} 包内"
                )
            if not candidate.is_file():
                raise SkillContractError(f"SKILL.md references[{ref!r}] 指向缺失文件: {candidate}")

        (dest / _SKILL_MD).write_text(body, encoding="utf-8")
        manifest = {
            "skill_id": sid,
            "name": name,
            "summary": summary,
            "source_url": source_url,
            "content_hash": digest,
            "version": version,
            "resource_paths": normalized_resources,
            "references": list(declared_refs),
            "imported_at": datetime.now(tz=UTC).isoformat(),
        }
        (dest / _MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return SkillPackage(
            skill_id=sid,
            name=name,
            summary=summary,
            content=body,
            resource_paths=tuple(normalized_resources),
            source_url=source_url,
            content_hash=digest,
            version=version,
            references=tuple(declared_refs),
        )


def _rmtree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink()
    path.rmdir()


def safe_rel_path(name: str) -> str:
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return "/".join(parts)


def _strip_resources_prefix(path: str) -> str:
    """Strip a leading ``resources/`` prefix from a declared reference path."""
    prefix = f"{_RESOURCES}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _to_resource_rel(path: str) -> str:
    """Normalize a path to the ``resources/``-prefixed skill-relative form."""
    prefix = f"{_RESOURCES}/"
    return path if path.startswith(prefix) else f"{prefix}{path}"
