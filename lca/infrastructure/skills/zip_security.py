"""Safe ZIP extraction with zip-slip guards and size caps."""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath

from lca.contracts.protocols.memory.operational_skills import (
    SKILL_MAX_RESOURCE_BYTES,
    SKILL_MAX_RESOURCES,
    SKILL_MAX_ZIP_BYTES,
    SkillImportError,
)


def _safe_rel_path(name: str) -> str:
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return "/".join(parts)


def extract_zip_bytes(
    data: bytes,
    *,
    max_zip_bytes: int = SKILL_MAX_ZIP_BYTES,
    max_file_bytes: int = SKILL_MAX_RESOURCE_BYTES,
    max_files: int = SKILL_MAX_RESOURCES,
) -> dict[str, bytes]:
    """Extract ZIP to relative-path → bytes map."""
    if len(data) > max_zip_bytes:
        raise SkillImportError(f"ZIP 超过上限 {max_zip_bytes} 字节")
    out: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if ".." in info.filename.replace("\\", "/"):
                    raise SkillImportError(f"ZIP 路径非法（zip-slip）: {info.filename!r}")
                rel = _safe_rel_path(info.filename)
                if not rel or rel.startswith(".") or "/." in f"/{rel}/":
                    continue
                if len(out) >= max_files:
                    raise SkillImportError(f"ZIP 内文件数超过上限 {max_files}")
                if info.file_size > max_file_bytes:
                    raise SkillImportError(
                        f"ZIP 内文件 {rel!r} 超过单文件上限 {max_file_bytes} 字节"
                    )
                payload = zf.read(info)
                if len(payload) > max_file_bytes:
                    raise SkillImportError(
                        f"ZIP 内文件 {rel!r} 实际大小超过上限 {max_file_bytes} 字节"
                    )
                out[rel] = payload
    except zipfile.BadZipFile as exc:
        raise SkillImportError(f"无效 ZIP: {exc}") from exc
    if not out:
        raise SkillImportError("ZIP 为空或无可读文件")
    return out


def find_skill_markdown(files: dict[str, bytes]) -> tuple[str, bytes]:
    """Locate SKILL.md (case-insensitive) in extracted map."""
    for key, value in files.items():
        if PurePosixPath(key).name.lower() == "skill.md":
            return key, value
    raise SkillImportError("ZIP 内未找到 SKILL.md")


def list_resource_paths(files: dict[str, bytes], skill_md_key: str) -> tuple[str, ...]:
    """All paths except the main SKILL.md, sorted."""
    skill_prefix = str(PurePosixPath(skill_md_key).parent)
    if skill_prefix == ".":
        skill_prefix = ""
    paths: list[str] = []
    for key in sorted(files):
        if key == skill_md_key:
            continue
        if skill_prefix and not key.startswith(f"{skill_prefix}/") and skill_prefix != "":
            # Keep files under skill directory only when SKILL.md is nested.
            parent = str(PurePosixPath(skill_md_key).parent)
            if parent and parent != "." and not key.startswith(f"{parent}/"):
                continue
        paths.append(key)
    return tuple(paths)
