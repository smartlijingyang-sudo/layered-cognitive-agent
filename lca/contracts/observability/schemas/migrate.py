"""v1 → v2 envelope 迁移(ADR-0096 §5.1)。

字段映射:
- ``schema: lca.journal/1`` → ``schema_version: v2.0.0``
- ``event: {...}`` → ``payload: {...}``
- ``seq`` 保留(主键)
"""

from __future__ import annotations

from typing import Any


def migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") == "v2.0.0":
        return data  # idempotent
    if "event" in data:
        out = dict(data)
        out["payload"] = out.pop("event")
        out["schema_version"] = "v2.0.0"
        return out
    return data
