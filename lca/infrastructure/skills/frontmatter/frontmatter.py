"""Minimal YAML frontmatter parser for SKILL.md (no PyYAML runtime dep)."""

from __future__ import annotations

import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_BLOCK_SCALAR_RE = re.compile(r"\A[>|][-\+\d]*\Z")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _read_block_scalar(lines: list[str], start: int, parent_indent: int) -> tuple[list[str], int]:
    """Collect a block scalar body, stopping at the next key on the parent indent."""
    block: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() and _indent(line) <= parent_indent:
            break
        block.append(line)
        i += 1
    return block, i


def _read_list_items(
    lines: list[str], start: int, parent_indent: int
) -> tuple[list[str] | None, int]:
    """Collect a YAML block-sequence body for a key with an empty value.

    Returns ``(items, next_i)``; ``(None, start)`` when no ``- item`` lines
    follow (caller then falls back to the legacy ``""`` scalar).
    """
    items: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped.startswith("- ") or _indent(line) <= parent_indent:
            break
        piece = stripped[2:].strip().strip('"').strip("'")
        if piece:
            items.append(piece)
        i += 1
    if not items:
        return None, start
    return items, i


def _parse_inline_list(value: str) -> list[str]:
    """Parse ``[a, b]`` (quotes optional, empties dropped)."""
    inner = value[1:-1].strip()
    out: list[str] = []
    if inner:
        for piece in inner.split(","):
            piece = piece.strip().strip('"').strip("'")
            if piece:
                out.append(piece)
    return out


def _fold_block(block: list[str], *, folded: bool) -> str:
    """Dedent a block scalar body. ``>`` folds lines, ``|`` keeps them."""
    indents = [_indent(line) for line in block if line.strip()]
    pad = min(indents) if indents else 0
    lines = [line[pad:] if line.strip() else "" for line in block]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    if not folded:
        return "\n".join(lines)
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def split_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Return (frontmatter dict, body). Empty dict when no frontmatter.

    Single pass yields the complete dict: block sequences and inline lists
    become ``list[str]``; everything else stays a string. Block scalar
    bodies are consumed by :func:`_read_block_scalar` and never re-scanned
    for keys.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}, text.strip()
    raw_meta, body = match.group(1), match.group(2)
    lines = raw_meta.splitlines()
    meta: dict[str, str | list[str]] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        # 跳过列表子项("  - foo") — 它们已在所属 key 的前瞻里消费
        if stripped.startswith("- ") or ":" not in line:
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        i += 1
        if not key:
            continue
        if _BLOCK_SCALAR_RE.fullmatch(value):
            block, i = _read_block_scalar(lines, i, _indent(line))
            meta[key] = _fold_block(block, folded=value.startswith(">"))
            continue
        if not value:
            # 空值 key: 前瞻收集 "- item" 列表;没有则沿用旧行为 ""
            items, i = _read_list_items(lines, i, _indent(line))
            meta[key] = items if items is not None else ""
            continue
        if value.startswith("[") and value.endswith("]"):
            meta[key] = _parse_inline_list(value)
            continue
        meta[key] = value.strip('"').strip("'")
    return meta, body.strip()


def skill_title(meta: dict[str, str | list[str]], fallback: str) -> str:
    name = meta.get("name", "")
    if not isinstance(name, str):
        name = ""
    return name.strip() or fallback


def parse_references_field(text: str) -> list[str]:
    """从 SKILL.md 文本里解析 ``references`` 字段(ADR-0214 §7)。

    薄封装:实际解析走 :func:`split_frontmatter`(单次扫描),只取 list 型值;
    标量写法沿用旧行为(视为未声明 → ``[]``)。

    支持两种 YAML 写法:
    - 内联: ``references: [references/REFERENCE.md, references/SCHEMAS.md]``
    - 多行:
      ::
          references:
            - references/REFERENCE.md
            - references/SCHEMAS.md

    返回顺序按声明顺序。空列表 / 缺失字段 / 标量 → 返回 ``[]``。
    """
    meta, _ = split_frontmatter(text)
    refs = meta.get("references", [])
    return refs if isinstance(refs, list) else []
