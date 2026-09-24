"""Routine repository implementation (ADR-0248 §3.4 / s04)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.routine.models import RoutineSpec


class JsonRoutineRepository:
    """声明式例程 JSON 文件持久化仓储。

    持久化存储格式：~/.lca/routines/<routine_id>.json
    """

    def __init__(self, storage_dir: str | Path = "~/.lca/routines") -> None:
        self.storage_dir = Path(storage_dir).expanduser().resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, routine_id: str) -> Path:
        return self.storage_dir / f"{routine_id}.json"

    def save(self, spec: RoutineSpec) -> None:
        """保存或更新例程定义。"""
        target = self._file_path(spec.id)
        tmp = target.parent / f".tmp_{target.name}"
        data = spec.model_dump(mode="json")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(target)

    def get(self, routine_id: str) -> RoutineSpec | None:
        """根据 ID 加载例程定义。"""
        target = self._file_path(routine_id)
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return RoutineSpec.model_validate(data)

    def list_all(self) -> list[RoutineSpec]:
        """列出全部已持久化的例程定义。"""
        routines: list[RoutineSpec] = []
        for file in sorted(self.storage_dir.glob("*.json")):
            try:
                with file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                routines.append(RoutineSpec.model_validate(data))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return routines

    def delete(self, routine_id: str) -> bool:
        """删除指定例程。"""
        target = self._file_path(routine_id)
        if target.exists():
            target.unlink()
            return True
        return False


__all__ = ["JsonRoutineRepository"]
