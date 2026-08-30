"""Dual-write result normalizer (spec §B.6)."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, cast

from lca.contracts.harness.state.projection import ProjectionSnapshot
from lca.contracts.harness.tasks.session import SessionEvent


def _hash(value: Any) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class NormalizedToolCall:
    tool_name: str
    arguments_hash: str
    success: bool
    result_hash: str | None


@dataclass(frozen=True)
class NormalizedResult:
    status: str
    answer: str | None
    tool_calls: tuple[NormalizedToolCall, ...]
    llm_calls: int
    error: str | None = None
    journal_event_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class DivergenceReport:
    session_id: str
    divergences: tuple[str, ...]
    legacy: NormalizedResult
    new: NormalizedResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "divergences": list(self.divergences),
            "legacy": asdict(self.legacy),
            "new": asdict(self.new),
        }


class ResultNormalizer:
    @staticmethod
    def from_task_result(result: Any) -> NormalizedResult:
        status = getattr(result, "status", None)
        status_value = (
            cast("Any", status).value if hasattr(status, "value") else str(status or "unknown")
        )
        if status_value == "input-required":
            status_value = "waiting_input"
        tool_calls = tuple(
            NormalizedToolCall(
                tool_name=getattr(tc, "name", ""),
                arguments_hash=_hash(getattr(tc, "arguments", None)),
                success=bool(getattr(tc, "success", True)),
                result_hash=_hash(getattr(tc, "result", None)),
            )
            for tc in getattr(result, "tool_calls", ()) or ()
        )
        journal = tuple(
            getattr(event, "type", type(event).__name__)
            for event in getattr(result, "journal_events", ()) or ()
        )
        return NormalizedResult(
            status=status_value,
            answer=getattr(result, "output", None) or getattr(result, "answer", None),
            tool_calls=tool_calls,
            llm_calls=int(getattr(result, "llm_calls", 0) or 0),
            error=getattr(result, "error", None),
            journal_event_types=journal,
        )

    @staticmethod
    def from_projection(
        snapshot: ProjectionSnapshot, journal: list[SessionEvent]
    ) -> NormalizedResult:
        conversation = snapshot.values.get("conversation") or {}
        activity = snapshot.values.get("activity") or {}
        tool_calls = tuple(_extract_tool_calls(journal))
        return NormalizedResult(
            status=str(activity.get("status") or "unknown"),
            answer=conversation.get("last_assistant_message"),
            tool_calls=tool_calls,
            llm_calls=sum(1 for event in journal if event.type == "model.completed.v1"),
            error=activity.get("error"),
            journal_event_types=tuple(event.type for event in journal),
        )


def compare_results(
    *,
    session_id: str,
    legacy: Any,
    snapshot: ProjectionSnapshot,
    journal: list[SessionEvent],
) -> DivergenceReport:
    norm_legacy = ResultNormalizer.from_task_result(legacy)
    norm_new = ResultNormalizer.from_projection(snapshot, journal)
    divergences: list[str] = []
    if _status_bucket(norm_legacy.status) != _status_bucket(norm_new.status):
        divergences.append(f"status: {norm_legacy.status} != {norm_new.status}")
    if norm_legacy.tool_calls != norm_new.tool_calls:
        divergences.append(
            f"tool_calls: {len(norm_legacy.tool_calls)} vs {len(norm_new.tool_calls)}"
        )
    if norm_legacy.llm_calls != norm_new.llm_calls:
        divergences.append(f"llm_calls: {norm_legacy.llm_calls} vs {norm_new.llm_calls}")
    return DivergenceReport(
        session_id=session_id,
        divergences=tuple(divergences),
        legacy=norm_legacy,
        new=norm_new,
    )


def _status_bucket(status: str) -> str:
    if status in {"completed", "idle"}:
        return "completed"
    if status in {"input-required", "waiting_input", "input_required"}:
        return "waiting_input"
    return status


def _extract_tool_calls(journal: list[SessionEvent]) -> list[NormalizedToolCall]:
    open_calls: dict[str, SessionEvent] = {}
    done: list[NormalizedToolCall] = []
    for event in journal:
        if event.type == "tool.called.v1":
            open_calls[str(event.data.get("call_id"))] = event
        elif event.type == "tool.completed.v1":
            call_id = str(event.data.get("call_id"))
            started = open_calls.pop(call_id, None)
            name = started.data.get("tool_name") if started else ""
            done.append(
                NormalizedToolCall(
                    tool_name=str(name),
                    arguments_hash=str(started.data.get("arguments_ref") if started else ""),
                    success=bool(event.data.get("success")),
                    result_hash=event.data.get("result_ref"),
                )
            )
    return done
