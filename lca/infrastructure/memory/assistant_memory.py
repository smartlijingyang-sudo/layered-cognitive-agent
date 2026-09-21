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
import re
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


def _canonical_dedupe_key(dedupe_key: str | None, category: str | None = None) -> str | None:
    """通用规范化 dedupe_key（去除空白、转小写、连字符转下划线、补全 category 命名空间）。

    保证同语义事实的幂等键格式一致（ADR-0247 §3.3），保持领域无关，不硬编码具体业务实体。
    """
    if not dedupe_key:
        return None
    key = str(dedupe_key).strip().lower().replace("-", "_")
    if ":" not in key and category:
        cat = str(category).strip().lower()
        if cat:
            key = f"{cat}:{key}"
    return key


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
                        source_trace_id=str(getattr(state, "trace_id", "") or ""),
                    )
            # ADR-0246 PR-5：身份/偏好事实落盘后触发 USER.md 系统回填。
            await self.refresh_user_profile()
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
        source_trace_id: str,
        record_id: str | None = None,
        revision_of: str | None = None,
    ) -> None:
        """追加一条 typed semantic 记录；同 ``dedupe_key`` 旧记录被 supersede。

        ADR-0247 回归：除 ``dedupe_key`` 幂等外，再按 ``category + 内容指纹``
        做内容级去重。模型经 ``memory_add`` 写入的 dedupe_key 可能与自动提取
        的 canonical key 不同，但同一事实必须收敛为一条活跃记录。
        """
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
        dedupe_key_value = _canonical_dedupe_key(
            str(dedupe_key).strip() if dedupe_key else None, category=category_value
        )

        new_id_value = record_id or new_id("mem")
        superseded_id: str | None = revision_of

        def _retire(entry: dict[str, Any]) -> None:
            nonlocal superseded_id
            entry["deleted"] = True
            entry["retired_at_ms"] = now_ms
            entry.setdefault("metadata", {})["superseded_by"] = new_id_value
            superseded_id = str(entry.get("record_id") or "")

        # 1) 同 dedupe_key：canonical 幂等键（ADR-0246 语义）。
        if dedupe_key_value:
            for entry in records:
                if entry.get("dedupe_key") == dedupe_key_value and not entry.get("deleted", False):
                    _retire(entry)

        # 2) 同 category + 内容指纹：跨写入路径（memory_add vs 自动提取）去重。
        if superseded_id is None:
            fingerprint = _content_fingerprint(content)
            if fingerprint:
                for entry in records:
                    if entry.get("category") != category_value or entry.get("deleted", False):
                        continue
                    if _content_fingerprint(str(entry.get("content") or "")) == fingerprint:
                        _retire(entry)

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
                "source_trace_id": source_trace_id,
                "created_at_ms": now_ms,
                "created_at": _utc_now_iso(),
                "metadata": {"source": source},
            }
        )
        self._save(layer, records)

    async def refresh_user_profile(self) -> None:
        """身份/偏好事实变化后，从活跃记录全量重建 USER.md（系统回填）。

        任何写路径（图节点 ``update`` 与受治理工具 ``memory_add`` /
        ``memory_update`` / ``memory_remove``）写入后都必须调用，保证 USER.md
        始终是活跃 identity/preference 记录的投影，不残留 superseded 旧事实。
        """
        if self._profile_backfill is None:
            return
        assistant_id = self._root.parent.name
        identity_pref = [
            r
            for r in self.query(MemoryLayer.SEMANTIC)
            if r.category in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
        ]
        # 即使身份/偏好为空也回填，清掉 USER.md 中已删除事实的残留条目。
        await self._profile_backfill(assistant_id, identity_pref)

    def upsert(self, record: MemoryRecord) -> MemoryRecord:
        """按 ``dedupe_key`` 幂等写入 typed 记录（ADR-0246 ``MemoryStore`` 语义）。

        同 ``dedupe_key`` 的旧活跃记录被标记 superseded；返回的 ``record``
        与落盘条目共享 ``record_id``。
        """
        self._append_semantic(
            record_id=record.record_id,
            content=record.content,
            category=record.category.value,
            confidence=record.confidence,
            source=(
                str(record.metadata.get("source") or "user")
                if isinstance(record.metadata, dict)
                else "user"
            ),
            dedupe_key=record.dedupe_key,
            source_trace_id=record.source_trace_id or "",
            revision_of=record.revision_of,
        )
        return record

    def supersede(
        self,
        record_id: str,
        replacement: MemoryRecord,
        *,
        reason: str = "superseded",
    ) -> MemoryRecord:
        """退役旧记录并写入替代记录，建立 ``revision_of`` 血缘。"""
        layer = MemoryLayer.SEMANTIC
        records = self._load(layer)
        now_ms = _utc_now_ms()
        old_dedupe_key: str | None = None
        for entry in records:
            if entry.get("record_id") == record_id and not entry.get("deleted", False):
                entry["deleted"] = True
                entry["retired_at_ms"] = now_ms
                entry.setdefault("metadata", {})["superseded_reason"] = reason
                old_dedupe_key = str(entry.get("dedupe_key") or "").strip() or None
        self._save(layer, records)
        # 继承被替换记录的维度键与血缘，保持事实维度稳定延续
        replacement = MemoryRecord(
            record_id=replacement.record_id,
            content=replacement.content,
            memory_type=replacement.memory_type,
            importance=replacement.importance,
            category=replacement.category,
            dedupe_key=replacement.dedupe_key or old_dedupe_key,
            confidence=replacement.confidence,
            source_trace_id=replacement.source_trace_id,
            metadata=replacement.metadata,
            revision_of=record_id,
        )
        return self.upsert(replacement)

    def remove(self, record_id: str) -> None:
        """把指定记录标记为已删除（保留审计，不再参与检索）。"""
        layer = MemoryLayer.SEMANTIC
        records = self._load(layer)
        now_ms = _utc_now_ms()
        for entry in records:
            if entry.get("record_id") == record_id and not entry.get("deleted", False):
                entry["deleted"] = True
                entry["retired_at_ms"] = now_ms
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


# 内容指纹前缀标签：这些标签后的剩余部分是事实核心，跨路径去重时忽略。
_FINGERPRINT_LABELS: frozenset[str] = frozenset(
    {
        "用户身份",
        "用户偏好",
        "用户称呼偏好",
        "称呼偏好",
        "称呼",
        "身份",
        "偏好",
        "事实",
    }
)

# 称呼类变体：不同措辞表达同一语义（叫他X / 叫我X / 称呼用户为X / 希望被称呼为X），
# 归一到 ``称呼X``，让跨写入路径（memory_add vs 自动提取）能收敛。
_ADDRESS_VARIANTS_RE = re.compile(r"^(?:叫他|叫我|称呼用户为|希望被称呼为|称呼我为|称呼为)")


def _content_fingerprint(content: str) -> str:
    """结构化事实的内容指纹：去引号、去常见标签前缀、称呼变体归一、去空白。

    用于 store 边界的内容级幂等（ADR-0247 回归）。例如：
    - ``称呼偏好：称呼用户为"老板"`` 与 ``用户偏好：称呼用户为老板``
      都收敛为 ``称呼老板``。
    - ``用户称呼偏好：叫他「老板」`` 与 ``用户偏好：希望被称呼为老板``
      都收敛为 ``称呼老板``。
    """
    normalized = content
    for ch in "\"'「」『』“”‘’":
        normalized = normalized.replace(ch, "")
    if "：" in normalized:
        label, _, rest = normalized.partition("：")
        if label.strip() in _FINGERPRINT_LABELS:
            normalized = rest
    normalized = _ADDRESS_VARIANTS_RE.sub("称呼", normalized)
    return "".join(normalized.split())


def _utc_now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
