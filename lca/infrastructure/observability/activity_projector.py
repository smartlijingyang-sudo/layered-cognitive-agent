from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityItem,
    ActivityStatus,
)


def _determine_category(tool_name: str) -> ActivityCategory:
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


def _format_iso(val: Any) -> str:
    """Unix timestamp (float/int) -> ISO string; '' when unknown (honest)."""
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=UTC).isoformat()
    if isinstance(val, str) and val.strip():
        return val.strip()
    return ""


def _extract_inv_id(
    event: dict[str, Any], payload: dict[str, Any], tool_calling: dict[str, Any]
) -> str:
    return str(
        event.get("invocation_id")
        or payload.get("invocation_id")
        or tool_calling.get("id")
        or tool_calling.get("invocation_id")
        or payload.get("tool_call_id")
        or payload.get("call_id")
        or tool_calling.get("call_id")
        or event.get("id")
        or ""
    )


def _extract_tool_name(
    event: dict[str, Any], payload: dict[str, Any], tool_calling: dict[str, Any]
) -> str:
    return str(
        event.get("tool_name")
        or payload.get("tool_name")
        or tool_calling.get("apiName")
        or tool_calling.get("identifier")
        or tool_calling.get("name")
        or ""
    )


def _extract_arguments(
    event: dict[str, Any], payload: dict[str, Any], tool_calling: dict[str, Any]
) -> dict[str, Any]:
    args = event.get("arguments") or payload.get("arguments") or tool_calling.get("arguments") or {}
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"raw": args}
    return args if isinstance(args, dict) else {}


class ActivityProjector:
    """Pure-function projection engine folding Session/Spine facts into ActivityItem."""

    def __init__(
        self,
        cache_path: Path | str | None = None,
        seed_traces: bool = False,
    ) -> None:
        # In-memory projection store per assistant: {assistant_id: {item_id: ActivityItem}}
        self._items: dict[str, dict[str, ActivityItem]] = {}
        self._cache_path = Path(cache_path) if cache_path else None
        self._seed_traces = seed_traces
        self._seeded = False
        if self._cache_path and self._cache_path.is_file():
            self._load_cache()
        if not self._items and self._seed_traces:
            self.seed_from_traces()

    def feed_event(self, stamped: dict[str, Any]) -> ActivityItem | None:
        event = stamped.get("event") or stamped
        ep = event.get("execution_point")
        ev_type = str(event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
        tool_calling = (
            payload.get("toolCalling") if isinstance(payload.get("toolCalling"), dict) else payload
        )

        is_start = ep in ("phase.tool.call.start", "step.tool_call.record") or ev_type in (
            "ToolStarted",
            "tool.started.v1",
        )
        is_exec_start = ep == "body.tool.execute.start"
        is_end = ep == "body.tool.execute.end" or ev_type in (
            "ToolInvoked",
            "tool.invoked.v1",
            "ToolDenied",
            "tool.denied.v1",
        )

        # Handle Start: phase.tool.call.start / step.tool_call.record / ToolStarted
        if is_start:
            inv_id = _extract_inv_id(event, payload, tool_calling)
            if not inv_id:
                return None
            run_id = str(event.get("run_id") or payload.get("run_id") or "run_current")
            asst_id = str(event.get("assistant_id") or payload.get("assistant_id") or "default")
            tool_name = _extract_tool_name(event, payload, tool_calling)
            args = _extract_arguments(event, payload, tool_calling)
            title, summary, icon = ActivityIntentNamer.name(tool_name, args)
            category = _determine_category(tool_name)
            ts = _format_iso(
                event.get("timestamp") or payload.get("timestamp") or event.get("created_at")
            )

            item = ActivityItem(
                id=inv_id,
                run_id=run_id,
                assistant_id=asst_id,
                category=category,
                title=title,
                summary=summary,
                status=ActivityStatus.RUNNING,
                start_time=ts,
                icon=icon,
                tool_name=tool_name,
                params=args,
                tool_name=tool_name,
                current_step=ActivityIntentNamer.live_step(tool_name, args),
            )
            self._save(item)
            return item

        # Handle execute.start: body.tool.execute.start (refresh start_time to true execution moment)
        if is_exec_start:
            inv_id = _extract_inv_id(event, payload, tool_calling)
            if not inv_id:
                return None
            asst_id = str(event.get("assistant_id") or payload.get("assistant_id") or "default")
            existing = self._get(asst_id, inv_id) or self._get("default", inv_id)
            tool_name = _extract_tool_name(event, payload, tool_calling)
            args = _extract_arguments(event, payload, tool_calling)
            ts = _format_iso(event.get("timestamp") or payload.get("timestamp") or event.get("created_at"))
            if existing:
                refreshed = ActivityItem(
                    id=existing.id,
                    run_id=existing.run_id,
                    assistant_id=existing.assistant_id,
                    category=existing.category,
                    title=existing.title,
                    summary=existing.summary,
                    status=ActivityStatus.RUNNING,
                    start_time=ts or existing.start_time,
                    end_time=existing.end_time,
                    duration_ms=existing.duration_ms,
                    icon=existing.icon,
                    params=existing.params,
                    result_summary=existing.result_summary,
                    is_system=existing.is_system,
                    tool_name=existing.tool_name or tool_name,
                    current_step=existing.current_step or ActivityIntentNamer.live_step(existing.tool_name or tool_name, existing.params),
                )
                self._save(refreshed)
                return refreshed
            else:
                title, summary, icon = ActivityIntentNamer.name(tool_name, args)
                category = _determine_category(tool_name)
                item = ActivityItem(
                    id=inv_id,
                    run_id=str(event.get("run_id") or payload.get("run_id") or "run_current"),
                    assistant_id=asst_id,
                    category=category,
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

        # Handle End: body.tool.execute.end / ToolInvoked / ToolDenied
        if is_end:
            inv_id = _extract_inv_id(event, payload, tool_calling)
            if not inv_id:
                return None
            asst_id = str(event.get("assistant_id") or payload.get("assistant_id") or "default")

            existing = self._get(asst_id, inv_id) or self._get("default", inv_id)
            if not existing:
                for store in self._items.values():
                    if inv_id in store:
                        existing = store[inv_id]
                        break

            tool_name = _extract_tool_name(event, payload, tool_calling)
            args = _extract_arguments(event, payload, tool_calling)

            if not existing:
                # Synthesize fallback item if start was missed/dropped
                title, summary, icon = ActivityIntentNamer.name(tool_name, args)
                category = _determine_category(tool_name)
                ts = _format_iso(
                    event.get("timestamp") or payload.get("timestamp") or event.get("created_at")
                )
                existing = ActivityItem(
                    id=inv_id,
                    run_id=str(event.get("run_id") or payload.get("run_id") or "run_current"),
                    assistant_id=asst_id,
                    category=category,
                    title=title,
                    summary=summary,
                    status=ActivityStatus.RUNNING,
                    start_time=ts,
                    icon=icon,
                    tool_name=tool_name,
                    params=args,
                    tool_name=tool_name,
                    current_step=None,
                )

            # Determine success / status
            if ev_type in ("ToolDenied", "tool.denied.v1"):
                status = ActivityStatus.FAILED
                res_content = str(
                    event.get("reason") or payload.get("reason") or "Denied by policy"
                )
            else:
                ok = (
                    event.get("isSuccess")
                    if "isSuccess" in event
                    else (payload.get("ok") if "ok" in payload else event.get("ok"))
                )
                outcome = str(payload.get("outcome") or event.get("outcome") or "").lower()
                is_success = (
                    ok
                    if isinstance(ok, bool)
                    else outcome not in ("failure", "failed", "error", "cancelled")
                )
                status = (
                    ActivityStatus.CANCELLED
                    if outcome == "cancelled"
                    else (ActivityStatus.COMPLETED if is_success else ActivityStatus.FAILED)
                )
                res_content = ""
                res_raw = event.get("result") or payload.get("result")
                if isinstance(res_raw, dict):
                    state = res_raw.get("state")
                    if isinstance(state, dict):
                        res_content = str(state.get("summary") or state.get("content") or "")
                    if not res_content:
                        res_content = str(res_raw.get("content") or res_raw.get("error") or "")
                elif payload.get("message") and isinstance(payload.get("message"), dict):
                    res_content = str(payload["message"].get("content") or "")
                elif event.get("output_text"):
                    res_content = str(event.get("output_text"))
                if not res_content:
                    res_content = str(payload.get("error") or "")

            duration_ms = (
                event.get("executionTime")
                if event.get("executionTime") is not None
                else (payload.get("latency_ms") or payload.get("executionTime"))
            )
            end_time = _format_iso(event.get("timestamp") or payload.get("timestamp"))

            updated = ActivityItem(
                id=existing.id,
                run_id=existing.run_id,
                assistant_id=existing.assistant_id,
                category=existing.category,
                title=existing.title,
                summary=existing.summary,
                status=status,
                start_time=existing.start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                icon=existing.icon,
                tool_name=tool_name or existing.tool_name,
                params=existing.params or args,
                result_summary=(res_content[:100] + "...")
                if len(res_content) > 100
                else res_content,
                is_system=existing.is_system,
                tool_name=existing.tool_name or tool_name,
                current_step=None,
            )
            self._save(updated)
            return updated

        return None

    def cancel_activity(self, assistant_id: str, activity_id: str) -> ActivityItem | None:
        existing = self._get(assistant_id, activity_id)
        if not existing:
            return None
        # 诚实：end_time 不知道就不填，不写 "cancelled" 这种假时间戳
        cancelled = ActivityItem(
            id=existing.id,
            run_id=existing.run_id,
            assistant_id=existing.assistant_id,
            category=existing.category,
            title=existing.title,
            summary=existing.summary,
            status=ActivityStatus.CANCELLED,
            start_time=existing.start_time,
            end_time=None,
            duration_ms=existing.duration_ms,
            icon=existing.icon,
            tool_name=existing.tool_name,
            params=existing.params,
            result_summary="User cancelled operation",
            is_system=existing.is_system,
            tool_name=existing.tool_name,
            current_step=None,
        )
        self._save(cancelled)
        return cancelled

    def get_activities(self, assistant_id: str) -> list[ActivityItem]:
        store = self._items.get(assistant_id, {})
        # Gateway tool events historically do not stamp assistant_id, so
        # the projector stores them under "default". Surface those real
        # activities too — otherwise the status drawer stays empty after a
        # kernel restart even though runs executed through the gateway.
        default_store = self._items.get("default", {})
        merged = {**default_store, **store}
        if not merged and self._seed_traces and not self._seeded:
            self.seed_from_traces()
            store = self._items.get(assistant_id, {})
            default_store = self._items.get("default", {})
            merged = {**default_store, **store}
        # Return descending by start_time
        return sorted(merged.values(), key=lambda x: x.start_time, reverse=True)

    def seed_from_traces(self, root_dir: str | Path = "traces/runs", limit: int = 50) -> int:
        """Seed activities from recent disk trace journals on restart/cold start."""
        self._seeded = True
        root = Path(root_dir)
        if not root.is_dir():
            return 0

        run_to_asst: dict[str, str] = {}
        db_path = Path("traces/runtime/lca_running_operations.sqlite3")
        if db_path.is_file():
            with contextlib.suppress(Exception):
                import sqlite3

                conn = sqlite3.connect(str(db_path))
                for r in (
                    conn.cursor()
                    .execute("SELECT run_id, agent_id FROM lca_running_operations")
                    .fetchall()
                ):
                    if r[0] and r[1] and r[1] not in ("solo", "team"):
                        run_to_asst[r[0]] = r[1]

        added = 0
        try:
            run_dirs = sorted(
                [d for d in root.iterdir() if d.is_dir() and d.name.startswith("run_")],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
        except Exception:
            return 0

        for rdir in run_dirs:
            jp = rdir / "journal.json"
            if not jp.is_file():
                continue
            j = None
            with (
                contextlib.suppress(OSError, json.JSONDecodeError, UnicodeDecodeError),
                open(jp, encoding="utf-8") as f,
            ):
                j = json.load(f)
            if not isinstance(j, dict):
                continue

            run_id = str(j.get("run_id") or rdir.name)
            asst_id = run_to_asst.get(run_id, "default")
            steps = j.get("steps") or []
            for s in steps:
                if not isinstance(s, dict):
                    continue
                tcs = s.get("tool_calls") or []
                trs = {
                    tr.get("invocation_id"): tr
                    for tr in (s.get("tool_results") or [])
                    if isinstance(tr, dict) and tr.get("invocation_id")
                }
                step_entered = s.get("entered_at")
                # 诚实：缺 entered_at 就空着，不编造假时间戳
                start_time = _format_iso(step_entered)

                for tc in tcs:
                    if not isinstance(tc, dict):
                        continue
                    inv_id = str(tc.get("invocation_id") or "")
                    if not inv_id:
                        continue
                    tool_name = str(tc.get("name") or tc.get("tool_name") or "")
                    args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                    title, summary, icon = ActivityIntentNamer.name(tool_name, args)
                    category = _determine_category(tool_name)

                    status = ActivityStatus.COMPLETED
                    duration_ms = None
                    result_summary = None
                    tr = trs.get(inv_id)
                    if tr:
                        is_ok = tr.get("ok", True)
                        status = ActivityStatus.COMPLETED if is_ok else ActivityStatus.FAILED
                        duration_ms = tr.get("latency_ms")
                        res_content = str(
                            tr.get("delta_summary")
                            or tr.get("stdout_head")
                            or tr.get("error")
                            or ""
                        )
                        result_summary = (
                            (res_content[:100] + "...")
                            if len(res_content) > 100
                            else (res_content or None)
                        )

                    item = ActivityItem(
                        id=inv_id,
                        run_id=run_id,
                        assistant_id=asst_id,
                        category=category,
                        title=title,
                        summary=summary,
                        status=status,
                        start_time=start_time,
                        end_time=start_time,
                        duration_ms=duration_ms,
                        icon=icon,
                        tool_name=tool_name,
                        params=args,
                        result_summary=result_summary,
                        tool_name=tool_name,
                        current_step=None,
                    )
                    if asst_id not in self._items:
                        self._items[asst_id] = {}
                    if item.id not in self._items[asst_id]:
                        self._items[asst_id][item.id] = item
                        added += 1

        if added > 0:
            self._save_cache()
        return added

    def _save(self, item: ActivityItem) -> None:
        if item.assistant_id not in self._items:
            self._items[item.assistant_id] = {}
        self._items[item.assistant_id][item.id] = item
        self._save_cache()

    def _get(self, assistant_id: str, item_id: str) -> ActivityItem | None:
        return self._items.get(assistant_id, {}).get(item_id)

    def _load_cache(self) -> None:
        if not self._cache_path or not self._cache_path.is_file():
            return
        with (
            contextlib.suppress(OSError, json.JSONDecodeError, UnicodeDecodeError),
            open(self._cache_path, encoding="utf-8") as f,
        ):
            data = json.load(f)
            if isinstance(data, dict):
                for asst_id, items_dict in data.items():
                    if isinstance(items_dict, dict):
                        if asst_id not in self._items:
                            self._items[asst_id] = {}
                        for i_id, item_raw in items_dict.items():
                            if isinstance(item_raw, dict):
                                with contextlib.suppress(Exception):
                                    self._items[asst_id][i_id] = ActivityItem(**item_raw)

    def _save_cache(self) -> None:
        if not self._cache_path:
            return
        with contextlib.suppress(OSError, TypeError):
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            serializable = {
                asst_id: {i_id: item.model_dump() for i_id, item in items.items()}
                for asst_id, items in self._items.items()
            }
            tmp = self._cache_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            tmp.replace(self._cache_path)


_GLOBAL_PROJECTOR = ActivityProjector(
    cache_path=Path("traces/runtime/activity_cache.json"),
    seed_traces=True,
)


def get_global_activity_projector() -> ActivityProjector:
    """Return shared global activity projector."""
    return _GLOBAL_PROJECTOR


__all__ = (
    "ActivityProjector",
    "get_global_activity_projector",
)
