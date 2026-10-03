from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityItem,
    ActivityStatus,
)

# --- Event vocabulary -------------------------------------------------------
# Spine execution points.
_START_POINTS = ("phase.tool.call.start", "step.tool_call.record")
_EXECUTE_START_POINTS = ("body.tool.execute.start",)
_END_POINTS = ("body.tool.execute.end", "phase.tool.call.end")
# Gateway catalog events (spec §5.3.1: ToolInvoked carries ``result.state`` natively).
_CATALOG_START_POINTS = ("ToolStarted", "tool.started.v1")
_CATALOG_END_POINTS = ("ToolInvoked", "tool.invoked.v1", "ToolDenied", "tool.denied.v1")

_FAILURE_OUTCOMES = ("failure", "failed", "error", "denied")


def _category_for(tool_name: str) -> ActivityCategory:
    lowered = tool_name.lower()
    if "shell" in lowered or "exec" in lowered:
        return ActivityCategory.COMMAND
    if "subagent" in lowered:
        return ActivityCategory.SUBAGENT
    if "browser" in lowered:
        return ActivityCategory.BROWSER
    if "cron" in lowered:
        return ActivityCategory.CRON
    return ActivityCategory.TOOL


def _iso_ts(ts: Any) -> str:
    """Unix timestamp (float/int) -> ISO string; '' when unknown (honest)."""
    try:
        if ts is None or ts == "":
            return ""
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _seed_result_summary(tr: dict[str, Any], status: ActivityStatus) -> str:
    if status == ActivityStatus.FAILED:
        err = str(tr.get("error") or "").strip()
        return f"失败：{err[:120]}" if err else "执行失败（无错误详情）"
    out = str(tr.get("stdout_head") or tr.get("delta_summary") or "").strip()
    return (out[:100] + "...") if len(out) > 100 else out


def _inv_id(payload: dict[str, Any]) -> str:
    return str(payload.get("invocation_id") or payload.get("tool_call_id") or payload.get("call_id") or "")


def _tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "")


def _arguments(payload: dict[str, Any]) -> dict[str, Any]:
    args = payload.get("arguments")
    if isinstance(args, dict):
        return args
    args = payload.get("args")
    if isinstance(args, dict):
        return args
    params = payload.get("params")
    if isinstance(params, dict):
        return params
    return {}


class ActivityProjector:
    """Pure-function projection engine folding Session/Spine facts into ActivityItem.

    Muse 思想：动态是"活"的——start 拍的是意图，execute.start 修正为真实
    开始时间，end 落的是结果；running 的每一刻都有 current_step 可看。
    """

    def __init__(self, trace_root: str | Path | None = None) -> None:
        # In-memory projection store per assistant: {assistant_id: {item_id: ActivityItem}}
        self._items: dict[str, dict[str, ActivityItem]] = {}
        # Kernel restarts wipe memory; reseed recent activities from persisted
        # run journals so the drawer's 「动态」 tab is not empty after a restart.
        self._trace_root = Path(trace_root) if trace_root else None
        self._seeded = False

    # ------------------------------------------------------------------ feed
    def feed_event(self, stamped: dict[str, Any]) -> ActivityItem | None:
        event = stamped.get("event") or stamped
        ep = str(event.get("execution_point") or "")
        # Catalog (gateway) events carry their name in ``type``, not
        # ``execution_point`` — this is the wire that was dead before.
        etype = str(event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event

        if ep in _START_POINTS or etype in _CATALOG_START_POINTS:
            return self._on_start(payload)
        if ep in _EXECUTE_START_POINTS:
            return self._on_execute_start(payload)
        if ep in _END_POINTS or etype in _CATALOG_END_POINTS:
            return self._on_end(etype or ep, payload)
        return None

    # ------------------------------------------------------------------ start
    def _on_start(self, payload: dict[str, Any]) -> ActivityItem | None:
        inv_id = _inv_id(payload)
        if not inv_id:
            return None
        tool_name = _tool_name(payload)
        args = _arguments(payload)
        title, summary, icon = ActivityIntentNamer.name(tool_name, args)

        item = ActivityItem(
            id=inv_id,
            run_id=str(payload.get("run_id") or "run_current"),
            assistant_id=str(payload.get("assistant_id") or "default"),
            category=_category_for(tool_name),
            title=title,
            summary=summary,
            status=ActivityStatus.RUNNING,
            # 诚实：没有时间戳就空着，不编造 "2026-10-02T00:00:00Z" 这种假时间
            start_time=str(payload.get("timestamp") or ""),
            icon=icon,
            params=args,
            tool_name=tool_name,
            current_step=ActivityIntentNamer.live_step(tool_name, args),
        )
        self._save(item)
        return item

    # ---------------------------------------------------------- execute start
    def _on_execute_start(self, payload: dict[str, Any]) -> ActivityItem | None:
        """body.tool.execute.start: the tool REALLY started executing now.

        Refresh start_time to the true execution moment and set the live step.
        If the start event was missed (gateway restart), synthesize the item so
        the drawer never shows a dangling end without a row.
        """
        inv_id = _inv_id(payload)
        if not inv_id:
            return None
        asst_id = str(payload.get("assistant_id") or "default")
        ts = str(payload.get("timestamp") or "")
        existing = self._get(asst_id, inv_id)
        if existing is None:
            tool_name = _tool_name(payload)
            args = _arguments(payload)
            title, summary, icon = ActivityIntentNamer.name(tool_name, args)
            item = ActivityItem(
                id=inv_id,
                run_id=str(payload.get("run_id") or "run_current"),
                assistant_id=asst_id,
                category=_category_for(tool_name),
                title=title,
                summary=summary,
                status=ActivityStatus.RUNNING,
                start_time=ts,
                icon=icon,
                params=args,
                tool_name=tool_name,
                current_step=ActivityIntentNamer.live_step(tool_name, args),
            )
            self._save(item)
            return item
        updated = self._evolve(
            existing,
            start_time=ts or existing.start_time,
            current_step=ActivityIntentNamer.live_step(existing.tool_name, existing.params),
        )
        self._save(updated)
        return updated

    # -------------------------------------------------------------------- end
    def _on_end(self, ep: str, payload: dict[str, Any]) -> ActivityItem | None:
        inv_id = _inv_id(payload)
        if not inv_id:
            return None
        asst_id = str(payload.get("assistant_id") or "default")
        existing = self._get(asst_id, inv_id)
        if existing is None:
            return None

        denied = ep in ("ToolDenied", "tool.denied.v1")
        outcome = str(payload.get("outcome") or "").lower()
        ok = payload.get("ok")

        if denied:
            status = ActivityStatus.FAILED
        elif outcome == "cancelled":
            status = ActivityStatus.CANCELLED
        elif isinstance(ok, bool):
            status = ActivityStatus.COMPLETED if ok else ActivityStatus.FAILED
        else:
            status = (
                ActivityStatus.COMPLETED
                if outcome not in _FAILURE_OUTCOMES
                else ActivityStatus.FAILED
            )

        result_summary = self._result_summary(ep, payload, status)
        updated = self._evolve(
            existing,
            status=status,
            end_time=str(payload.get("timestamp") or ""),
            duration_ms=payload.get("latency_ms"),
            result_summary=result_summary,
            current_step=ActivityProjector._CLEAR,  # 落盘了，不再有"正在干什么"
        )
        self._save(updated)
        return updated

    @staticmethod
    def _result_summary(ep: str, payload: dict[str, Any], status: ActivityStatus) -> str:
        if ep in ("ToolDenied", "tool.denied.v1"):
            reason = str(payload.get("reason") or "denied")
            return f"调用被拒绝：{reason}"
        if status == ActivityStatus.CANCELLED:
            return "用户取消了该操作"
        if status == ActivityStatus.FAILED:
            err = payload.get("error") or payload.get("message")
            if isinstance(err, dict):
                err = err.get("content") or err.get("text") or ""
            err = str(err or "").strip()
            return f"失败：{err[:120]}" if err else "执行失败（无错误详情）"
        # spec §5.3.1: ToolInvoked carries result.state natively
        result = payload.get("result")
        state = result.get("state") if isinstance(result, dict) else None
        content = ""
        if isinstance(state, dict):
            content = str(state.get("summary") or state.get("content") or "")
        if not content:
            msg = payload.get("message")
            if isinstance(msg, dict):
                content = str(msg.get("content") or "")
            elif msg:
                content = str(msg)
        content = content.strip()
        return (content[:100] + "...") if len(content) > 100 else content

    # ------------------------------------------------------------------ cancel
    def cancel_activity(self, assistant_id: str, activity_id: str) -> ActivityItem | None:
        existing = self._get(assistant_id, activity_id)
        if not existing:
            return None
        # 诚实：end_time 不知道就不填，不写 "cancelled" 这种假时间戳
        cancelled = self._evolve(
            existing,
            status=ActivityStatus.CANCELLED,
            result_summary="用户取消了该操作",
            current_step=ActivityProjector._CLEAR,
        )
        self._save(cancelled)
        return cancelled

    def seed_from_traces(self, root_dir: str | Path | None = None, limit: int = 50) -> int:
        """Rehydrate recent activities from persisted run journals.

        Muse 思想：kernel 重启后动态栏不能是空的——从 trace 里把最近的
        真实活动捞回来。只取已落盘的 completed/failed；重启时刻"running"
        的已经死了，显示成 running 就是撒谎，所以不取。
        Returns the number of activities seeded.
        """
        self._seeded = True
        root = Path(root_dir) if root_dir else self._trace_root
        if root is None:
            root = Path("traces/runs")
        if not root.is_dir():
            return 0

        try:
            run_dirs = sorted(
                [d for d in root.iterdir() if d.is_dir() and d.name.startswith("run_")],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )[:limit]
        except OSError:
            return 0

        added = 0
        for rdir in run_dirs:
            jp = rdir / "journal.json"
            if not jp.is_file():
                continue
            try:
                with open(jp, encoding="utf-8") as f:
                    j = json.load(f)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
                continue
            if not isinstance(j, dict):
                continue
            run_id = str(j.get("run_id") or rdir.name)
            for si, step in enumerate(j.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                calls = step.get("tool_calls") or []
                results = step.get("tool_results") or []
                entered = step.get("entered_at")
                exited = step.get("exited_at")
                for ci, tc in enumerate(calls):
                    if not isinstance(tc, dict):
                        continue
                    tool_name = str(tc.get("name") or "")
                    if not tool_name:
                        continue
                    tr = results[ci] if ci < len(results) and isinstance(results[ci], dict) else {}
                    ok = tr.get("ok")
                    status = (
                        ActivityStatus.COMPLETED if ok is not False
                        else ActivityStatus.FAILED
                    )
                    args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                    title, summary, icon = ActivityIntentNamer.name(tool_name, args)
                    item = ActivityItem(
                        id=f"seed:{run_id}:{si}:{ci}",
                        run_id=run_id,
                        assistant_id="default",
                        category=_category_for(tool_name),
                        title=title,
                        summary=summary,
                        status=status,
                        start_time=_iso_ts(entered),
                        end_time=_iso_ts(exited),
                        duration_ms=tr.get("latency_ms"),
                        icon=icon,
                        params=args,
                        result_summary=_seed_result_summary(tr, status),
                        tool_name=tool_name,
                        current_step=None,
                    )
                    self._save(item)
                    added += 1
        return added

    # ------------------------------------------------------------------- query
    def get_activities(self, assistant_id: str) -> list[ActivityItem]:
        # Cold start after a kernel restart: pull recent real activities back
        # from disk once, so the drawer is not empty.
        if not self._seeded and not self._items:
            self.seed_from_traces()
        store = self._items.get(assistant_id, {})
        # Gateway tool events historically do not stamp assistant_id, so
        # the projector stores them under "default". Surface those real
        # activities too — otherwise the status drawer stays empty after a
        # kernel restart even though runs executed through the gateway.
        default_store = self._items.get("default", {})
        merged = {**default_store, **store}
        # Return descending by start_time
        return sorted(merged.values(), key=lambda x: x.start_time, reverse=True)

    # ------------------------------------------------------------------ internals
    # Sentinel: pass _CLEAR to explicitly reset a field to None.
    _CLEAR: Any = object()

    def _evolve(self, item: ActivityItem, **changes: Any) -> ActivityItem:
        """Rebuild a frozen ActivityItem with changed fields.

        Pass ``ActivityProjector._CLEAR`` as a value to explicitly reset
        that field to None (plain None means "keep the old value").
        """
        data = item.model_dump()
        for key, value in changes.items():
            if value is None:
                continue
            data[key] = None if value is self._CLEAR else value
        return ActivityItem(**data)

    def _save(self, item: ActivityItem) -> None:
        if item.assistant_id not in self._items:
            self._items[item.assistant_id] = {}
        self._items[item.assistant_id][item.id] = item

    def _get(self, assistant_id: str, item_id: str) -> ActivityItem | None:
        # Gateway events historically do not stamp assistant_id: fall back to
        # the "default" bucket so an end event can always find its start.
        item = self._items.get(assistant_id, {}).get(item_id)
        if item is None and assistant_id != "default":
            item = self._items.get("default", {}).get(item_id)
        return item


_GLOBAL_PROJECTOR = ActivityProjector()


def get_global_activity_projector() -> ActivityProjector:
    """Return shared global activity projector."""
    return _GLOBAL_PROJECTOR


__all__ = (
    "ActivityProjector",
    "get_global_activity_projector",
)
