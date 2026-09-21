"""旧记忆数据迁移（ADR-0246 PR-9）。

把 ADR-0246 之前的关键词原文存档（``{home}/memory/semantic.json`` 中缺少
``category`` 字段的记录）标记为 ``deleted=True`` / ``retired_at_ms``，保留
审计但不再参与检索。同时清理测试/历史 assistant home 中的小写 ``user.md``
（不在 ``CONFIG_FACE_FILES``，永不加载），把有效身份信息回填到 ``USER.md``。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["clean_lowercase_user_md", "migrate_semantic_memory"]


def _utc_now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def migrate_semantic_memory(home_path: str | Path) -> int:
    """把旧格式 ``semantic.json`` 原文记录标记为 superseded；返回变更条数。

    判定：缺少 ``category`` 字段且未标记 ``deleted`` 的记录视为旧格式原文
    存档。只标记不删除（可审计），迁移后可被 ``AssistantMemory.query``
    排除（``query`` 过滤 ``deleted=True``）。
    """
    home = Path(home_path)
    path = home / "memory" / "semantic.json"
    if not path.is_file():
        return 0
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(records, list):
        return 0
    now_ms = _utc_now_ms()
    changed = 0
    for entry in records:
        if not isinstance(entry, dict):
            continue
        if "category" not in entry and not entry.get("deleted", False):
            entry["deleted"] = True
            entry["retired_at_ms"] = entry.get("retired_at_ms") or now_ms
            entry.setdefault("metadata", {})["migrated"] = "superseded_raw_text"
            changed += 1
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return changed


def clean_lowercase_user_md(home_path: str | Path) -> bool:
    """清理小写 ``user.md`` 并把内容回填到 ``USER.md``；返回是否处理。"""
    home = Path(home_path)
    lower = home / "user.md"
    upper = home / "USER.md"
    if not lower.is_file():
        return False
    content = lower.read_text(encoding="utf-8").strip()
    if content and (not upper.is_file() or not upper.read_text(encoding="utf-8").strip()):
        upper.write_text(content + "\n", encoding="utf-8")
    lower.unlink()
    return True


def dedupe_semantic_memory(home_path: str | Path) -> int:
    """把同一事实的重复活跃记忆记录标记为 superseded；返回变更条数。

    分组规则：
    - 有 canonical dedupe_key 的记录按 ``(category, canonical_key)`` 分组；
    - 无 dedupe_key 的记录按 ``(category, content_fingerprint)`` 分组。
    组内保留权威度最高的一条（source user > model > tool，其次 confidence，
    再次最新 created_at_ms），其余标记 ``deleted=True`` + ``superseded_reason="deduped"``。
    同时把保留记录的 ``dedupe_key`` 重写为 canonical key，防止复发。
    """
    from lca.infrastructure.memory.assistant_memory import (
        _canonical_dedupe_key,
        _content_fingerprint,
    )

    home = Path(home_path)
    path = home / "memory" / "semantic.json"
    if not path.is_file():
        return 0
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(records, list):
        return 0

    now_ms = _utc_now_ms()
    active = [r for r in records if isinstance(r, dict) and not r.get("deleted", False)]

    # 先把所有活跃记录的 dedupe_key 重写为 canonical key，防止未来写入复发。
    key_rewritten = False
    for entry in active:
        canonical = _canonical_dedupe_key(str(entry.get("dedupe_key") or "").strip() or None)
        if canonical and entry.get("dedupe_key") != canonical:
            entry["dedupe_key"] = canonical
            key_rewritten = True

    def _group_key(entry: dict[str, object]) -> tuple[object, ...]:
        canonical = str(entry.get("dedupe_key") or "").strip() or None
        if canonical:
            return (entry.get("category"), canonical)
        return (entry.get("category"), _content_fingerprint(str(entry.get("content") or "")))

    def _authority(entry: dict[str, object]) -> tuple[int, float, int]:
        source = str(entry.get("source") or "model")
        # user 陈述 > tool 观察 > model 推断；权威度越高越靠前。
        source_rank = {"user": 3, "tool": 2, "model": 1}.get(source, 0)
        confidence = float(entry.get("confidence") or 0.0)
        created = int(entry.get("created_at_ms") or 0)
        return (source_rank, confidence, created)

    groups: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for entry in active:
        groups.setdefault(_group_key(entry), []).append(entry)

    changed = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=_authority, reverse=True)
        keeper = group[0]
        canonical = _canonical_dedupe_key(str(keeper.get("dedupe_key") or "").strip() or None)
        if canonical:
            keeper["dedupe_key"] = canonical
        for entry in group[1:]:
            entry["deleted"] = True
            entry["retired_at_ms"] = entry.get("retired_at_ms") or now_ms
            entry.setdefault("metadata", {})["superseded_reason"] = "deduped"
            changed += 1

    if changed or key_rewritten:
        path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return changed
