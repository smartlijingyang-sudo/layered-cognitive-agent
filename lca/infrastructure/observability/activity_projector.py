from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityItem,
    ActivityStatus,
)


class ActivityProjector:
    """Pure-function projection engine folding Session/Spine facts into ActivityItem."""

    def __init__(self) -> None:
        # In-memory projection store per assistant: {assistant_id: {item_id: ActivityItem}}
        self._items: dict[str, dict[str, ActivityItem]] = {}

    def feed_event(self, stamped: dict[str, Any]) -> ActivityItem | None:
        event = stamped.get("event") or stamped
        ep = event.get("execution_point")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event

        # Handle Start: phase.tool.call.start / step.tool_call.record
        if ep in ("phase.tool.call.start", "step.tool_call.record"):
            inv_id = str(payload.get("invocation_id") or payload.get("tool_call_id") or "")
            if not inv_id:
                return None
            run_id = str(payload.get("run_id") or "run_current")
            asst_id = str(payload.get("assistant_id") or "default")
            tool_name = str(payload.get("tool_name") or "")
            args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
            title, summary, icon = ActivityIntentNamer.name(tool_name, args)

            category = ActivityCategory.TOOL
            lowered = tool_name.lower()
            if "shell" in lowered or "exec" in lowered:
                category = ActivityCategory.COMMAND
            elif "subagent" in lowered:
                category = ActivityCategory.SUBAGENT
            elif "browser" in lowered:
                category = ActivityCategory.BROWSER
            elif "cron" in lowered:
                category = ActivityCategory.CRON

            item = ActivityItem(
                id=inv_id,
                run_id=run_id,
                assistant_id=asst_id,
                category=category,
                title=title,
                summary=summary,
                status=ActivityStatus.RUNNING,
                start_time=str(payload.get("timestamp") or "2026-10-02T00:00:00Z"),
                icon=icon,
                params=args,
            )
            self._save(item)
            return item

        # Handle End: body.tool.execute.end
        if ep == "body.tool.execute.end":
            inv_id = str(payload.get("invocation_id") or payload.get("tool_call_id") or "")
            asst_id = str(payload.get("assistant_id") or "default")
            existing = self._get(asst_id, inv_id)
            if not existing:
                return None
            ok = payload.get("ok")
            outcome = str(payload.get("outcome") or "").lower()
            is_success = ok if isinstance(ok, bool) else outcome not in ("failure", "failed", "error", "cancelled")

            status = ActivityStatus.CANCELLED if outcome == "cancelled" else (
                ActivityStatus.COMPLETED if is_success else ActivityStatus.FAILED
            )
            res_content = ""
            msg = payload.get("message")
            if isinstance(msg, dict):
                res_content = str(msg.get("content") or "")

            updated = ActivityItem(
                id=existing.id,
                run_id=existing.run_id,
                assistant_id=existing.assistant_id,
                category=existing.category,
                title=existing.title,
                summary=existing.summary,
                status=status,
                start_time=existing.start_time,
                end_time=str(payload.get("timestamp") or ""),
                duration_ms=payload.get("latency_ms"),
                icon=existing.icon,
                params=existing.params,
                result_summary=(res_content[:100] + "...") if len(res_content) > 100 else res_content,
                is_system=existing.is_system,
            )
            self._save(updated)
            return updated

        return None

    def cancel_activity(self, assistant_id: str, activity_id: str) -> ActivityItem | None:
        existing = self._get(assistant_id, activity_id)
        if not existing:
            return None
        cancelled = ActivityItem(
            id=existing.id,
            run_id=existing.run_id,
            assistant_id=existing.assistant_id,
            category=existing.category,
            title=existing.title,
            summary=existing.summary,
            status=ActivityStatus.CANCELLED,
            start_time=existing.start_time,
            end_time="cancelled",
            duration_ms=existing.duration_ms,
            icon=existing.icon,
            params=existing.params,
            result_summary="User cancelled operation",
            is_system=existing.is_system,
        )
        self._save(cancelled)
        return cancelled

    def get_activities(self, assistant_id: str) -> list[ActivityItem]:
        store = self._items.get(assistant_id, {})
        # Return descending by start_time
        return sorted(store.values(), key=lambda x: x.start_time, reverse=True)

    def _save(self, item: ActivityItem) -> None:
        if item.assistant_id not in self._items:
            self._items[item.assistant_id] = {}
        self._items[item.assistant_id][item.id] = item

    def _get(self, assistant_id: str, item_id: str) -> ActivityItem | None:
        return self._items.get(assistant_id, {}).get(item_id)


_GLOBAL_PROJECTOR = ActivityProjector()


def get_global_activity_projector() -> ActivityProjector:
    """Return shared global activity projector."""
    return _GLOBAL_PROJECTOR


__all__ = (
    "ActivityProjector",
    "get_global_activity_projector",
)
