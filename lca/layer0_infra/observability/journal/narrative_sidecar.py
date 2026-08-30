"""NarrativeSidecar —— 与 ``journal.jsonl`` 同目录写一份 ``journal.narrative.md``。

目的:不打开 JSON 也能用 ``cat`` / 任何编辑器查看这次 run 的来龙去脉。
- 每次 ``on_event`` 追加一行人类叙述;
- run 结束 ``finalize`` 时写摘要 + glossary(所有事件类型的中文说明)。

实现要点:
- 完全独立于 ``JsonlJournalProjector``;后者通过 ``SidecarHook`` protocol
  接收 (stamped, record) 对。
- 文本来源 = ``event_doc.doc_for(type).summary`` + record 的关键字段;
  不读 evidence,只读 record dict。
- sidecar 是 best-effort:写失败不阻塞落盘。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, TextIO, runtime_checkable


@runtime_checkable
class SidecarHook(Protocol):
    """``JsonlJournalProjector`` 在每条事件 / 收尾时回调。"""

    name: str

    def on_event(self, stamped: Any, record: dict[str, Any]) -> None: ...

    def finalize(self) -> None: ...


def _short(value: Any, limit: int = 80) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", "⏎").replace("\t", "⇥")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _section_for(event_type: str) -> str:
    if event_type in {
        "TeamRunStarted",
        "TeamRunFinished",
        "TaskCreated",
        "InboxFollowupCreated",
    }:
        return "🏁 Run 边界"
    if event_type.startswith("Casting"):
        return "🎭 选角"
    if event_type.startswith("Delegation") or event_type == "TeamMessagePublished":
        return "🤝 协作"
    if event_type in {
        "DecisionMade",
        "StepCompleted",
        "ActionDegraded",
        "GateDecided",
        "RunPaused",
        "RunResumed",
        "ApprovalRequested",
        "ApprovalResolved",
    }:
        return "🧠 认知控制"
    if event_type.startswith("LlmCall") or event_type in {
        "StepTextDelta",
        "ReasoningDelta",
        "ReasoningCompleted",
    }:
        return "🤖 LLM 资源"
    if event_type.startswith("Tool") or event_type == "SandboxOutputDelta":
        return "🔧 工具执行"
    if event_type.startswith("Attachment"):
        return "📎 附件"
    if event_type.startswith("Context") or event_type in {
        "PerceptionMerged",
        "MemoryCommitted",
    }:
        return "🧮 上下文 / 记忆"
    if event_type.startswith("Plugin") or event_type == "PresetPublished":
        return "🧩 插件生命周期"
    if event_type == "RuntimeObserved":
        return "🛠️ 反射诊断"
    return "📦 其他"


class NarrativeSidecar:
    """把 journal 事件流写一份 markdown 叙事。"""

    name = "narrative"

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self._path.open("w", encoding="utf-8")
        self._fh.write("# Journal Narrative\n\n")
        self._fh.write("> 每次 run 自动同步;来源:同目录 `journal.jsonl`。\n\n")
        self._last_section: str | None = None
        self._summary_counts: dict[str, int] = {}
        self._first_ts: float | None = None
        self._last_ts: float | None = None

    def on_event(self, stamped: Any, record: dict[str, Any]) -> None:
        descriptor = record.get("descriptor") or {}
        event_type = str(descriptor.get("type", ""))
        if not event_type:
            return
        self._summary_counts[event_type] = self._summary_counts.get(event_type, 0) + 1
        occurred = record.get("occurred_at")
        if isinstance(occurred, (int, float)):
            if self._first_ts is None:
                self._first_ts = float(occurred)
            self._last_ts = float(occurred)
        section = _section_for(event_type)
        if section != self._last_section:
            self._fh.write(f"\n## {section}\n\n")
            self._last_section = section
        try:
            from lca.layer0_infra.observability.event_doc import doc_for

            doc = doc_for(event_type)
        except Exception:
            doc = None
        summary = doc.summary if doc else "(未登记)"
        scope = record.get("scope") or {}
        role = scope.get("agent_role") or "-"
        step = scope.get("step", 0)
        elapsed = record.get("elapsed_ms")
        elapsed_part = f"+{elapsed}ms " if isinstance(elapsed, int) else ""
        ts_iso = record.get("occurred_at_iso", "")
        line = f"- `{ts_iso}` {elapsed_part}**{event_type}** (role=`{role}`, step=`{step}`) — {summary}"
        data = record.get("data") or {}
        if isinstance(data, Mapping):
            interesting = {
                k: data[k]
                for k in (
                    "agent_role",
                    "caller_role",
                    "callee_role",
                    "action_type",
                    "tool_name",
                    "model",
                    "status",
                    "latency_ms",
                    "text_delta",
                    "rationale_preview",
                    "delegation_id",
                    "objective",
                )
                if k in data and data[k] not in (None, "")
            }
            if interesting:
                items = ", ".join(f"{k}={_short(v)}" for k, v in interesting.items())
                line += f"\n  - {items}"
        self._fh.write(line + "\n")
        self._fh.flush()

    def finalize(self) -> None:
        try:
            self._fh.write("\n## 📊 事件类型分布\n\n")
            for event_type, count in sorted(
                self._summary_counts.items(), key=lambda kv: (-kv[1], kv[0])
            ):
                try:
                    from lca.layer0_infra.observability.event_doc import doc_for

                    doc = doc_for(event_type)
                except Exception:
                    doc = None
                layer = doc.layer if doc else "-"
                summary = doc.summary if doc else "(未登记)"
                self._fh.write(f"- `{event_type}` ×{count} ({layer}) — {summary}\n")
            if self._first_ts is not None and self._last_ts is not None:
                dur = self._last_ts - self._first_ts
                self._fh.write(
                    f"\n总耗时约 {dur:.2f}s;事件类型去重 {len(self._summary_counts)} 种,"
                    f"共 {sum(self._summary_counts.values())} 条。\n"
                )
            self._fh.flush()
        finally:
            self._fh.close()

    def close(self) -> None:
        self.finalize()


__all__ = ["NarrativeSidecar", "SidecarHook"]
