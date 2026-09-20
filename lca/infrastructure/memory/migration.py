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
