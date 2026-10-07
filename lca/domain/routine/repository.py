"""Routine repository implementation (ADR-0248 §3.4 / s04)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.routine.models import RoutineSpec, RoutineTrigger


class JsonRoutineRepository:
    """声明式例程 JSON 文件持久化仓储。

    持久化存储格式：~/.lca/routines/<routine_id>.json
    触发记录（运行时状态，非定义）：~/.lca/routines/triggers/<routine_id>.json
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
            except (OSError, ValueError):
                continue
        return routines

    def delete(self, routine_id: str) -> bool:
        """删除指定例程。"""
        target = self._file_path(routine_id)
        if target.exists():
            target.unlink()
            return True
        return False

    def _trigger_path(self, routine_id: str) -> Path:
        return self.storage_dir / "triggers" / f"{routine_id}.json"

    def save_trigger(self, trigger: RoutineTrigger) -> None:
        """持久化一条触发记录（ADR-0263 C4：_last_triggered 下沉到这里）。

        运行时状态与例程定义分离存放（``triggers/`` 子目录），``list_all()``
        只 glob 存储根的 ``*.json``，永远不会把触发记录误当成例程定义。
        last-write-wins；连续记录两次天然幂等。
        """
        target = self._trigger_path(trigger.routine_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.parent / f".tmp_{target.name}"
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(trigger.model_dump(mode="json"), fh, indent=2, ensure_ascii=False)
        tmp.replace(target)

    def get_last_trigger(self, routine_id: str) -> RoutineTrigger | None:
        """读取持久化的触发记录；从未触发过返回 None。"""
        target = self._trigger_path(routine_id)
        if not target.exists():
            return None
        try:
            with target.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return RoutineTrigger.model_validate(data)
        except (OSError, ValueError):
            return None


__all__ = ["JsonRoutineRepository"]
