"""AssistantMemory — persistent per-assistant MemorySystem (ADR-0242 D5).

A minimal ``MemorySystem`` implementation that persists memory records under
``{home}/memory/`` (one JSON file per ``MemoryLayer``).  The Home directory
is the isolation boundary: two assistants never share records.  Memory is
NOT part of the manifest digest (I-A13), so this module never touches
``MEMORY.md`` or any config-face file.

ADR-0246: records are typed knowledge entries. Semantic records carry
``category`` / ``dedupe_key`` / ``confidence`` / ``source``; a new record
with the same ``dedupe_key`` supersedes the previous active one
(``deleted=True`` + ``retired_at_ms`` on the old record, ``revision_of``
on the new). Superseded records stay on disk for audit and are excluded
from retrieval.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.memory.memory import MemorySystem

_MEMORY_DIR = "memory"

_ProfileBackfillCallback = Callable[[str, list[MemoryRecord]], Awaitable[None]]

__all__ = ["AssistantMemory"]


class AssistantMemory(MemorySystem):
    """``MemorySystem`` 实现：读写 ``{home}/memory/``，键按助理隔离。

    记录以 JSON 数组持久化在 ``{home}/memory/<layer>.json``；读取时惰性
    加载，写入时整层覆写（记录量级小，简单可审计）。不参与 manifest
    digest（I-A13），不触碰 ``MEMORY.md`` / 配置面文件。

    ``profile_backfill`` 是 ADR-0246 PR-5 的可选回调：写入 identity/preference
    事实后以 ``(assistant_id, records)`` 触发 USER.md 回填（系统行为）。
    """

    def __init__(
        self,
        home_path: str | Path,
        *,
        profile_backfill: _ProfileBackfillCallback | None = None,
    ) -> None:
        self._root = Path(home_path) / _MEMORY_DIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._profile_backfill = profile_backfill

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

    async def retrieve(
        self,
        manifest: ContextManifest,
        *,
        query: str = "",
        token_budget: int | None = None,
    ) -> list[MemoryRecord]:
        """返回持久化的事实记忆（semantic + episodic），供 ``memory_retrieve`` 注入。

        ADR-0246 PR-4：按 ``token_budget`` 做字符级截断，默认不截断。
        """
        del manifest, query
        records = self.query(MemoryLayer.SEMANTIC) + self.query(MemoryLayer.EPISODIC)
        if token_budget is None or token_budget <= 0:
            return records
        from lca.cognition.memory.layered.retrieval_policy import estimate_tokens

        kept: list[MemoryRecord] = []
        used = 0
        for record in records:
            estimated = estimate_tokens(record.content)
            if used + estimated > token_budget:
                break
            kept.append(record)
            used += estimated
        return kept

    async def update(
        self,
        state: AgentState,
        observation: Observation,
        reflection: Reflection,
    ) -> None:
        """Persist admitted memory candidates into the right layer.

        ADR-0246 semantic candidates (``memory_candidates`` list) persist as
        typed semantic records with ``category`` / ``dedupe_key`` and
        supersede previous records with the same dedupe_key. Procedural SOP
        candidates go to ``procedural.json``. The generic step record stays
        in ``working.json`` for observability.
        """
        extra = getattr(reflection, "extra", {}) or {}
        candidates = self._semantic_candidates(extra)
        if candidates:
            for cand in candidates:
                content = str(cand.get("content") or "").strip()
                if content:
                    self._append_semantic(
                        content=content,
                        category=cand.get("category", MemoryCategory.FACT.value),
                        confidence=cand.get("confidence"),
                        source=str(cand.get("source") or "user"),
                        dedupe_key=cand.get("dedupe_key"),
                        state=state,
                        observation=observation,
                        reflection=reflection,
                    )
            if self._profile_backfill is not None:
                # ADR-0246 PR-5：身份/偏好事实落盘后触发 USER.md 系统回填。
                assistant_id = self._root.parent.name
                identity_pref = [
                    r
                    for r in self.query(MemoryLayer.SEMANTIC)
                    if r.category in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
                ]
                if identity_pref:
                    await self._profile_backfill(assistant_id, identity_pref)
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

    @staticmethod
    def _semantic_candidates(extra: dict[str, Any]) -> list[dict[str, Any]]:
        """读取 ADR-0246 结构化候选列表；兼容旧的单候选 ``memory_candidate``。"""
        candidates = extra.get("memory_candidates")
        if isinstance(candidates, list):
            return [c for c in candidates if isinstance(c, dict)]
        single = extra.get("memory_candidate")
        if isinstance(single, dict):
            return [single]
        return []

    def _append_semantic(
        self,
        *,
        content: str,
        category: object,
        confidence: object,
        source: str,
        dedupe_key: object,
        state: AgentState,
        observation: Observation,
        reflection: Reflection,
    ) -> None:
        """追加一条 typed semantic 记录；同 ``dedupe_key`` 旧记录被 supersede。"""
        layer = MemoryLayer.SEMANTIC
        records = self._load(layer)
        now_ms = _utc_now_ms()
        try:
            category_value = (
                MemoryCategory(str(category)).value if category else MemoryCategory.FACT.value
            )
        except ValueError:
            category_value = MemoryCategory.FACT.value
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        dedupe_key_value = str(dedupe_key).strip() if dedupe_key else None

        new_id_value = new_id("mem")
        superseded_id: str | None = None
        if dedupe_key_value:
            for entry in records:
                if entry.get("dedupe_key") == dedupe_key_value and not entry.get("deleted", False):
                    entry["deleted"] = True
                    entry["retired_at_ms"] = now_ms
                    entry.setdefault("metadata", {})["superseded_by"] = new_id_value
                    superseded_id = str(entry.get("record_id") or "")

        records.append(
            {
                "record_id": new_id_value,
                "layer": layer.value,
                "category": category_value,
                "content": content,
                "importance": 0.9
                if confidence_value is not None and confidence_value >= 0.8
                else 0.5,
                "confidence": confidence_value,
                "source": source,
                "dedupe_key": dedupe_key_value,
                "revision_of": superseded_id,
                "deleted": False,
                "retired_at_ms": None,
                "source_trace_id": str(getattr(state, "trace_id", "") or ""),
                "created_at_ms": now_ms,
                "created_at": _utc_now_iso(),
                "metadata": {"source": source},
            }
        )
        self._save(layer, records)

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
                "created_at_ms": _utc_now_ms(),
                "metadata": metadata or {},
            }
        )
        self._save(layer, records)

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        """返回指定层的活跃记录（默认排除被 supersede 的旧记录）。"""
        return [
            MemoryRecord(
                record_id=str(entry.get("record_id") or ""),
                content=str(entry.get("content") or ""),
                memory_type=MemoryLayer(str(entry.get("layer") or layer.value)),
                importance=float(entry.get("importance") or 0.5),
                category=_as_category(entry.get("category")),
                dedupe_key=entry.get("dedupe_key")
                if isinstance(entry.get("dedupe_key"), str)
                else None,
                confidence=entry.get("confidence")
                if isinstance(entry.get("confidence"), (int, float))
                else None,
                source_trace_id=str(entry.get("source_trace_id") or ""),
                created_at_ms=entry.get("created_at_ms")
                if isinstance(entry.get("created_at_ms"), int)
                else None,
                revision_of=entry.get("revision_of")
                if isinstance(entry.get("revision_of"), str)
                else None,
                deleted=bool(entry.get("deleted", False)),
                retired_at_ms=entry.get("retired_at_ms")
                if isinstance(entry.get("retired_at_ms"), int)
                else None,
                metadata=entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
            )
            for entry in self._load(layer)
            if not entry.get("deleted", False)
        ]


def _as_category(value: object) -> MemoryCategory:
    try:
        return MemoryCategory(str(value)) if value else MemoryCategory.FACT
    except ValueError:
        return MemoryCategory.FACT


def _utc_now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
