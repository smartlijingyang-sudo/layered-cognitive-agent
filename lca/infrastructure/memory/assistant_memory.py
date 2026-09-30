"""AssistantMemory — persistent per-assistant MemorySystem (ADR-0242 D5).

A minimal ``MemorySystem`` implementation that persists memory records under
``{home}/memory/`` (one JSON file per ``MemoryLayer``).  The Home directory
is the isolation boundary: two assistants never share records.  Memory is
NOT part of the manifest digest (I-A13). After a semantic write this
module rewrites ``MEMORY.md`` as a projection of the active rows. The
JSON file remains the record store.

ADR-0246: records are typed knowledge entries. Semantic records carry
``category`` / ``dedupe_key`` / ``confidence`` / ``source``; a new record
with the same ``dedupe_key`` supersedes the previous active one
(``deleted=True`` + ``retired_at_ms`` on the old record, ``revision_of``
on the new). Superseded records stay on disk for audit and are excluded
from retrieval.
ADR-0247: 情景记忆（episodic.json 沉淀工具链自省记录，滚动容量 50）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id, utc_now_iso, utc_now_ms
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.memory.episode import canonical_dedupe_key
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.curated import (
    CuratedClaim,
    CuratedProjectionReceipt,
    contains_secret,
    may_acknowledge_projection,
    plan_curated_projection,
)
from lca.infrastructure.memory.contextfiles.domain.edit import StaleSnapshotOperationError
from lca.infrastructure.memory.contextfiles.domain.explain import (
    ClaimExplanation,
    ExplainableRecord,
    explain_record,
)
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.events.publisher import (
    ProjectionFailed,
    ProjectionWritten,
)
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.fingerprint import content_fingerprint
from lca.infrastructure.memory.retrieval.scoring import (
    apply_token_budget,
    is_expired,
    score_record,
)

logger = logging.getLogger(__name__)

_MEMORY_DIR = "memory"
_MAX_EPISODIC_RECORDS = 50
_LATCH_FILE = "claim-latch.json"

_ProfileBackfillCallback = Callable[[str, list[MemoryRecord]], Awaitable[None]]

__all__ = ["AssistantMemory"]


class AssistantMemory(MemorySystem):
    """``MemorySystem`` 实现：读写 ``{home}/memory/``，键按助理隔离。

    记录以 JSON 数组持久化在 ``{home}/memory/<layer>.json``；读取时惰性
    加载，写入时整层覆写（记录量级小，简单可审计）。不参与 manifest
    digest（I-A13）。语义层写入后，把活跃记录投影到 ``MEMORY.md``。

    ``profile_backfill`` 是 ADR-0246 PR-5 的可选回调：写入 identity/preference
    事实后以 ``(assistant_id, records)`` 触发 USER.md 回填（系统行为）。
    """

    def __init__(
        self,
        home_path: str | Path,
        *,
        profile_backfill: _ProfileBackfillCallback | None = None,
        event_publisher: DomainEventPublisher | None = None,
    ) -> None:
        self._root = Path(home_path) / _MEMORY_DIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._profile_backfill = profile_backfill
        self._event_publisher = event_publisher
        self._last_curated_receipt: CuratedProjectionReceipt | None = None
        self._open_claim: CuratedProjectionReceipt | None = self._load_latch()

    @property
    def last_curated_receipt(self) -> CuratedProjectionReceipt | None:
        return self._last_curated_receipt

    @last_curated_receipt.setter
    def last_curated_receipt(self, receipt: CuratedProjectionReceipt | None) -> None:
        # Receipt is write evidence; _open_claim is the one unused acknowledgement.
        self._last_curated_receipt = receipt
        self._open_claim = receipt if may_acknowledge_projection(receipt) else None
        self._persist_latch(self._open_claim)

    def take_claim_right(self) -> CuratedProjectionReceipt | None:
        receipt = self._open_claim
        self._open_claim = None
        self._persist_latch(None)
        return receipt

    def _latch_path(self) -> Path:
        return self._root / _LATCH_FILE

    def _load_latch(self) -> CuratedProjectionReceipt | None:
        path = self._latch_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        ids = data.get("record_ids") or ()
        receipt = CuratedProjectionReceipt(
            ok=bool(data.get("ok")),
            path=str(data.get("path") or ""),
            byte_count=int(data.get("byte_count") or 0),
            record_ids=tuple(str(item) for item in ids),
            error=str(data.get("error") or ""),
        )
        return receipt if may_acknowledge_projection(receipt) else None

    def _persist_latch(self, receipt: CuratedProjectionReceipt | None) -> None:
        path = self._latch_path()
        if receipt is None:
            path.unlink(missing_ok=True)
            return
        path.write_text(
            json.dumps(
                {
                    "ok": receipt.ok,
                    "path": receipt.path,
                    "byte_count": receipt.byte_count,
                    "record_ids": list(receipt.record_ids),
                    "error": receipt.error,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @property
    def home_path(self) -> Path:
        """Reflect resolves the episode directory from the bound memory without reading ``_root``."""
        return self._root.parent

    def _layer_path(self, layer: MemoryLayer) -> Path:
        return self._root / f"{layer.value}.json"

    def _load(self, layer: MemoryLayer) -> list[dict[str, Any]]:
        _text, records = self._load_with_text(layer)
        return records

    def _read_layer_text(self, layer: MemoryLayer) -> str:
        path = self._layer_path(layer)
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _load_with_text(self, layer: MemoryLayer) -> tuple[str, list[dict[str, Any]]]:
        text = self._read_layer_text(layer)
        if not text:
            return "", []
        try:
            data = json.loads(text)
        except ValueError:
            return text, []
        return text, data if isinstance(data, list) else []

    def _save(
        self,
        layer: MemoryLayer,
        records: list[dict[str, Any]],
        *,
        committed_ids: tuple[str, ...] = (),
        base_text: str | None = None,
    ) -> None:
        path = self._layer_path(layer)
        if layer is MemoryLayer.SEMANTIC and base_text is not None:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != base_text:
                raise StaleSnapshotOperationError(f"{path.name} changed during edit")
        previous = path.read_text(encoding="utf-8") if path.is_file() else ""
        path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if layer is MemoryLayer.SEMANTIC:
            self._project_curated(committed_ids)
            receipt = self.last_curated_receipt
            if receipt is not None and not receipt.ok:
                if previous:
                    path.write_text(previous, encoding="utf-8")
                elif path.is_file():
                    path.unlink()

    def _projection_relative(self) -> str:
        """Relative path of the curated projection. The layout file names it."""

        return layout_for_home(self.home_path).projection_file

    def _project_curated(self, committed_ids: tuple[str, ...]) -> None:
        """Rewrite the curated projection from the active semantic rows."""

        relative = self._projection_relative()
        path = self.home_path / relative
        omitted: tuple[CuratedClaim, ...] = ()
        try:
            text, omitted = plan_curated_projection(
                _claims_from_records(self.query(MemoryLayer.SEMANTIC)),
                source_note="记录在 `memory/semantic.json`。",
            )
            DiskFileStore(self.home_path).atomic_replace(relative, text)
        except OSError as exc:
            logger.warning("memory projection write failed: %s", exc)
            self.last_curated_receipt = CuratedProjectionReceipt(
                ok=False,
                path=str(path),
                byte_count=0,
                record_ids=committed_ids,
                error=str(exc),
            )
            if self._event_publisher is not None:
                self._event_publisher.publish(
                    ProjectionFailed(
                        path=str(path),
                        error=str(exc),
                        record_ids=committed_ids,
                    )
                )
            return
        self.last_curated_receipt = CuratedProjectionReceipt(
            ok=True,
            path=str(path),
            byte_count=len(text.encode("utf-8")),
            record_ids=committed_ids,
        )
        logger.info(
            "memory projection wrote path=%s bytes=%s committed=%s",
            path,
            self.last_curated_receipt.byte_count,
            len(committed_ids),
        )
        if self._event_publisher is not None:
            self._event_publisher.publish(
                ProjectionWritten(
                    path=str(path),
                    byte_count=self.last_curated_receipt.byte_count,
                    record_ids=committed_ids,
                )
            )
        try:
            self._archive_omitted(omitted)
        except OSError as exc:
            logger.warning("memory projection archive failed: %s", exc)

    def _archive_omitted(self, omitted: tuple[CuratedClaim, ...]) -> None:
        """Append claims dropped from the projection for budget into revisions/."""

        if not omitted:
            return
        date = datetime.now(UTC).strftime("%Y%m%d")
        relative = f"revisions/archive_{date}.md"
        store = DiskFileStore(self.home_path)
        try:
            existing = store.read_text(relative)
        except OSError:
            existing = ""
        lines = []
        for claim in omitted:
            marker = f"{claim.claim_id}:"
            if marker in existing:
                continue
            lines.append(f"- {claim.claim_id}: {claim.body}")
        if not lines:
            return
        body = existing if existing.endswith("\n") or not existing else f"{existing}\n"
        store.atomic_replace(relative, body + "\n".join(lines) + "\n")

    async def perceive(self, state: AgentState) -> AgentState:
        """返回原状态；检索注入由后续 memory.retrieve 节点负责（ADR-0242 D11）。"""
        return state

    async def retrieve(
        self,
        manifest: ContextManifest | None = None,
        *,
        query: str = "",
        token_budget: int | None = None,
    ) -> list[MemoryRecord]:
        """返回持久化的事实记忆（semantic + episodic），供 ``memory_retrieve`` 注入。

        ADR-0246 PR-4 / ADR-0247：按 query 相关性、时效 recency 与重要性排序，
        受 ``token_budget`` 约束截断。最相关的记录排在最前，淘汰不相关的历史事实。
        排序公式与 ``LayeredRetrievalPolicy`` 共用 ``retrieval.scoring``，避免
        两套检索语义漂移。
        """
        del manifest
        all_records = self.query(MemoryLayer.SEMANTIC) + self.query(MemoryLayer.EPISODIC)
        active = [r for r in all_records if not r.deleted and not is_expired(r)]
        if not active:
            return []

        now_ms = utc_now_ms()
        scored = sorted(
            active,
            key=lambda r: score_record(r, query, now_ms=now_ms),
            reverse=True,
        )
        return apply_token_budget(scored, token_budget=token_budget)

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
                    trigger = cand.get("trigger")
                    self._append_semantic(
                        content=content,
                        category=cand.get("category", MemoryCategory.FACT.value),
                        confidence=cand.get("confidence"),
                        source=str(cand.get("source") or "user"),
                        dedupe_key=cand.get("dedupe_key"),
                        source_trace_id=str(getattr(state, "trace_id", "") or ""),
                        metadata={"trigger": str(trigger)} if trigger else None,
                    )
            # ADR-0246 PR-5：身份/偏好事实落盘后触发 USER.md 系统回填。
            await self.refresh_user_profile()
            if not self._is_tool_execution_observation(observation, state):
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
        # ADR-0247: 情景自知记忆 —— 当发生具体工具调用或步骤交付时沉淀为情景记录
        if self._is_tool_execution_observation(observation, state):
            task_str = str(getattr(state, "task", "") or "").strip()[:60]
            tool_desc = self._summarize_tool_execution(observation)
            content = f"在任务「{task_str}」中执行了 {tool_desc}"
            self._append(
                MemoryLayer.EPISODIC,
                content=content,
                state=state,
                observation=observation,
                reflection=reflection,
                importance=0.7,
                metadata={"step": getattr(state, "step", 0)},
            )

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
    def _is_tool_execution_observation(
        observation: Observation | None, state: AgentState | None
    ) -> bool:
        if observation is None:
            return False
        payload = getattr(observation, "payload", None)
        if isinstance(payload, dict):
            if any(
                k in payload
                for k in (
                    "tool",
                    "tool_name",
                    "tool_calls",
                    "tool_results",
                    "command",
                    "invocation_id",
                )
            ):
                return True
        elif isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict) and any(
                k in first for k in ("tool", "tool_name", "output", "invocation_id")
            ):
                return True
        return False

    @staticmethod
    def _summarize_tool_execution(observation: Observation) -> str:
        payload = getattr(observation, "payload", None)
        if isinstance(payload, dict):
            tool = payload.get("tool") or payload.get("tool_name") or "tool"
            output = str(payload.get("output") or payload.get("result") or "").strip()
            if output:
                out_snippet = output[:80] + ("..." if len(output) > 80 else "")
                return f"{tool} 工具，产出: {out_snippet}"
            return f"{tool} 工具"
        return "工具交互"

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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """追加一条 typed semantic 记录；同 ``dedupe_key`` 旧记录被 supersede。

        ADR-0247 回归：除 ``dedupe_key`` 幂等外，再按 ``category + 内容指纹``
        做内容级去重。模型经 ``memory_add`` 写入的 dedupe_key 可能与自动提取
        的 canonical key 不同，但同一事实必须收敛为一条活跃记录。
        """
        if contains_secret(content):
            logger.warning("memory projection rejected credential-shaped content")
            self.last_curated_receipt = CuratedProjectionReceipt(
                ok=False,
                path=str(self.home_path / self._projection_relative()),
                byte_count=0,
                error="credential_rejected",
            )
            return
        layer = MemoryLayer.SEMANTIC
        base_text, records = self._load_with_text(layer)
        now_ms = utc_now_ms()
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
        dedupe_key_value = canonical_dedupe_key(
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
            fingerprint = content_fingerprint(content)
            if fingerprint:
                for entry in records:
                    if entry.get("category") != category_value or entry.get("deleted", False):
                        continue
                    if content_fingerprint(str(entry.get("content") or "")) == fingerprint:
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
                "created_at": utc_now_iso(),
                "metadata": _stored_metadata(source, metadata),
            }
        )
        self._save(layer, records, committed_ids=(new_id_value,), base_text=base_text)

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
            metadata=record.metadata if isinstance(record.metadata, dict) else None,
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
        if contains_secret(replacement.content):
            self.last_curated_receipt = CuratedProjectionReceipt(
                ok=False,
                path=str(self.home_path / self._projection_relative()),
                byte_count=0,
                error="credential_rejected",
            )
            return replacement
        layer = MemoryLayer.SEMANTIC
        base_text, records = self._load_with_text(layer)
        now_ms = utc_now_ms()
        old_dedupe_key: str | None = None
        for entry in records:
            if entry.get("record_id") == record_id and not entry.get("deleted", False):
                entry["deleted"] = True
                entry["retired_at_ms"] = now_ms
                entry.setdefault("metadata", {})["superseded_reason"] = reason
                old_dedupe_key = str(entry.get("dedupe_key") or "").strip() or None
        self._save(layer, records, base_text=base_text)
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
        base_text, records = self._load_with_text(layer)
        now_ms = utc_now_ms()
        for entry in records:
            if entry.get("record_id") == record_id and not entry.get("deleted", False):
                entry["deleted"] = True
                entry["retired_at_ms"] = now_ms
        self._save(layer, records, base_text=base_text)

    def _append(
        self,
        layer: MemoryLayer,
        *,
        content: str,
        state: AgentState,
        observation: Observation,
        reflection: Reflection,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append one record to ``<layer>.json`` and persist the layer."""
        base_text, records = self._load_with_text(layer)
        records.append(
            {
                "record_id": new_id("mem"),
                "layer": layer.value,
                "content": content,
                "importance": importance,
                "source_trace_id": str(getattr(state, "trace_id", "") or ""),
                "created_at": utc_now_iso(),
                "created_at_ms": utc_now_ms(),
                "metadata": metadata or {},
            }
        )
        if layer == MemoryLayer.EPISODIC and len(records) > _MAX_EPISODIC_RECORDS:
            records = records[-_MAX_EPISODIC_RECORDS:]
        self._save(
            layer,
            records,
            base_text=base_text if layer is MemoryLayer.SEMANTIC else None,
        )

    def explain(self, record_id: str) -> ClaimExplanation | None:
        """Return the eight audit fields for one semantic record, including retired rows."""

        records = [
            _explainable(entry)
            for entry in self._load(MemoryLayer.SEMANTIC)
            if str(entry.get("record_id") or "")
        ]
        target = next((record for record in records if record.record_id == record_id), None)
        if target is None:
            return None
        return explain_record(target, records)

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


def _explainable(entry: dict[str, Any]) -> ExplainableRecord:
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    confidence = entry.get("confidence")
    created = entry.get("created_at_ms")
    revision = entry.get("revision_of")
    return ExplainableRecord(
        record_id=str(entry.get("record_id") or ""),
        body=str(entry.get("content") or ""),
        kind=str(entry.get("category") or "fact"),
        importance=float(entry.get("importance") or 0.5),
        confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        source=str(metadata.get("source") or "").strip(),
        trigger=str(metadata.get("trigger") or "").strip(),
        recorded_on=_recorded_on(created if isinstance(created, int) else None),
        quote=str(metadata.get("quote") or "").strip(),
        revision_of=str(revision) if isinstance(revision, str) and revision else None,
    )


def _claims_from_records(records: list[MemoryRecord]) -> list[CuratedClaim]:
    """Map host records into the portable projection input."""

    claims: list[CuratedClaim] = []
    for record in records:
        if record.deleted:
            continue
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        source = str(metadata.get("source") or "").strip()
        trigger = str(metadata.get("trigger") or "").strip() or str(record.source_trace_id or "")
        claims.append(
            CuratedClaim(
                claim_id=record.record_id,
                kind=record.category.value,
                body=record.content,
                importance=record.importance,
                source=source,
                trigger=trigger.strip(),
                recorded_on=_recorded_on(record.created_at_ms),
            )
        )
    return claims


def _recorded_on(created_at_ms: int | None) -> str:
    if created_at_ms is None:
        return ""
    return datetime.fromtimestamp(created_at_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _stored_metadata(source: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    stored = {"source": source}
    if not metadata:
        return stored
    for key, value in metadata.items():
        if key != "source":
            stored[key] = value
    return stored


def _as_category(value: object) -> MemoryCategory:
    try:
        return MemoryCategory(str(value)) if value else MemoryCategory.FACT
    except ValueError:
        return MemoryCategory.FACT
