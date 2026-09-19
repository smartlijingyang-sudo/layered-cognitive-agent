"""AssistantMemory — persistent per-assistant MemorySystem (ADR-0242 D5).

A minimal ``MemorySystem`` implementation that persists memory records under
``{home}/memory/`` (one JSON file per ``MemoryLayer``).  The Home directory
is the isolation boundary: two assistants never share records.  Memory is
NOT part of the manifest digest (I-A13), so this module never touches
``MEMORY.md`` or any config-face file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.memory.memory import MemorySystem

_MEMORY_DIR = "memory"

__all__ = ["AssistantMemory"]


class AssistantMemory(MemorySystem):
    """``MemorySystem`` 实现：读写 ``{home}/memory/``，键按助理隔离。

    记录以 JSON 数组持久化在 ``{home}/memory/<layer>.json``；读取时惰性
    加载，写入时整层覆写（记录量级小，简单可审计）。不参与 manifest
    digest（I-A13），不触碰 ``MEMORY.md`` / 配置面文件。
    """

    def __init__(self, home_path: str | Path) -> None:
        self._root = Path(home_path) / _MEMORY_DIR
        self._root.mkdir(parents=True, exist_ok=True)

    def _layer_path(self, layer: MemoryLayer) -> Path:
        return self._root / f"{layer.value}.json"

    def _load(self, layer: MemoryLayer) -> list[dict[str, Any]]:
        path = self._layer_path(layer)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, layer: MemoryLayer, records: list[dict[str, Any]]) -> None:
        self._layer_path(layer).write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    async def perceive(self, state: AgentState) -> AgentState:
        """返回原状态；检索注入由后续 memory.retrieve 节点负责（ADR-0242 D11）。"""
        return state

    async def retrieve(self, manifest: ContextManifest) -> list[MemoryRecord]:
        """返回持久化的事实记忆（semantic + episodic），供 ``memory_retrieve`` 注入。"""
        del manifest
        return self.query(MemoryLayer.SEMANTIC) + self.query(MemoryLayer.EPISODIC)

    async def update(
        self,
        state: AgentState,
        observation: Observation,
        reflection: Reflection,
    ) -> None:
        """Persist admitted memory candidates into the right layer.

        User-confirmed semantic directives go to ``semantic.json``;
        procedural SOP candidates go to ``procedural.json``. The generic
        step record stays in ``working.json`` for observability.
        """
        extra = getattr(reflection, "extra", {}) or {}
        semantic = extra.get("memory_candidate")
        if isinstance(semantic, dict):
            content = str(semantic.get("content") or "").strip()
            if content:
                self._append(
                    MemoryLayer.SEMANTIC,
                    content=content,
                    state=state,
                    observation=observation,
                    reflection=reflection,
                    metadata={"source": str(semantic.get("source") or "user")},
                )
                return
        procedural = extra.get("procedural_candidate")
        if procedural is not None:
            content = str(getattr(procedural, "workflow_summary", "") or "").strip()
            if content:
                self._append(
                    MemoryLayer.PROCEDURAL,
                    content=content,
                    state=state,
                    observation=observation,
                    reflection=reflection,
                    metadata={"candidate_id": str(getattr(procedural, "candidate_id", "") or "")},
                )
                return
        self._append(
            MemoryLayer.WORKING,
            content=(
                f"step={state.step} success={observation.success} verdict={reflection.verdict}"
            ),
            state=state,
            observation=observation,
            reflection=reflection,
        )

    def _append(
        self,
        layer: MemoryLayer,
        *,
        content: str,
        state: AgentState,
        observation: Observation,
        reflection: Reflection,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append one record to ``<layer>.json`` and persist the layer."""
        records = self._load(layer)
        records.append(
            {
                "record_id": new_id("mem"),
                "layer": layer.value,
                "content": content,
                "importance": 0.5,
                "source_trace_id": str(getattr(state, "trace_id", "") or ""),
                "created_at": _utc_now_iso(),
                "metadata": metadata or {},
            }
        )
        self._save(layer, records)

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        """返回指定层的持久化记录（按写入顺序）。"""
        return [
            MemoryRecord(
                record_id=str(entry.get("record_id") or ""),
                content=str(entry.get("content") or ""),
                memory_type=MemoryLayer(str(entry.get("layer") or layer.value)),
                importance=float(entry.get("importance") or 0.5),
                source_trace_id=str(entry.get("source_trace_id") or ""),
                created_at_ms=entry.get("created_at_ms"),
                metadata=entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
            )
            for entry in self._load(layer)
        ]


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
