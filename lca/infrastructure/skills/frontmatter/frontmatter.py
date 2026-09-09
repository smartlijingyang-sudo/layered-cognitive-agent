"""Minimal YAML frontmatter parser for SKILL.md (no PyYAML runtime dep)."""

from __future__ import annotations

import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter dict, body). Empty dict when no frontmatter.

    Note: 列表型字段(``references: [...]`` 或多行 list)不解析进 dict;
    调用方需要时用 :func:`parse_references_field` 单独取。
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}, text.strip()
    raw_meta, body = match.group(1), match.group(2)
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        stripped = line.lstrip()
        # 跳过列表子项("  - foo") — 它们属于上一行的列表
        if stripped.startswith("- "):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        # 列表型行 ``references:`` 后续值若是 ``[]`` 或 ``[a, b]`` — 跳过,
        # 调用方通过 parse_references_field 解析。
        value = value.strip().strip('"').strip("'")
        if key:
            meta[key] = value
    return meta, body.strip()


def skill_title(meta: dict[str, str], fallback: str) -> str:
    name = meta.get("name", "").strip()
    return name or fallback


def parse_references_field(text: str) -> list[str]:
    """从 SKILL.md 文本里解析 ``references`` 字段(ADR-0214 §7)。

    支持两种 YAML 写法:
    - 内联: ``references: [references/REFERENCE.md, references/SCHEMAS.md]``
    - 多行:
      ::
          references:
            - references/REFERENCE.md
            - references/SCHEMAS.md

    返回顺序按声明顺序。空列表 / 缺失字段 → 返回 ``[]``。
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return []
    raw_meta = match.group(1)
    lines = raw_meta.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("references:"):
            _, _, value = line.partition(":")
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                if inner:
                    for piece in inner.split(","):
                        piece = piece.strip().strip('"').strip("'")
                        if piece:
                            out.append(piece)
                i += 1
                continue
            # 多行 list: 读后续的 "  - xxx" 行
            i += 1
            while i < len(lines):
                sub = lines[i].lstrip()
                if sub.startswith("- "):
                    piece = sub[2:].strip().strip('"').strip("'")
                    if piece:
                        out.append(piece)
                    i += 1
                    continue
                break
            continue
        i += 1
    return out
