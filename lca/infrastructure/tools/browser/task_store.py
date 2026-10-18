"""Task store and lifecycle management for Muse Browser tasks (ADR-0280 / Muse Spec)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserTaskRecord:
    """Record of an asynchronous browser task."""

    task_id: str
    task_description: str
    session_id: str
    status: str = "running"  # running, parked, succeeded, failed, blocked, closed, human_takeover
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    timeline: list[dict[str, Any]] = field(default_factory=list)
    initial_url: str | None = None
    current_url: str | None = None
    title: str | None = None
    payment_approved: bool = False
    captcha_preference: str = "solve"

    def to_dict(self) -> dict[str, Any]:
        return {
            "browser_task_id": self.task_id,
            "session_id": self.session_id,
            "status": self.status,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "step_count": len(self.timeline),
            "initial_url": self.initial_url,
            "current_url": self.current_url or self.initial_url,
            "title": self.title,
            "payment_approved": self.payment_approved,
        }


class BrowserTaskStore:
    """In-memory task store for active, parked, and historical browser tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, BrowserTaskRecord] = {}
        # CAPTCHA preferences: "all_tasks" -> choice, "site:<domain>" -> choice, "task:<id>" -> choice
        self._captcha_preferences: dict[str, dict[str, Any]] = {}

    def register_task(self, task: BrowserTaskRecord) -> None:
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> BrowserTaskRecord | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None) -> list[BrowserTaskRecord]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        # Sort so running/parked tasks come first, newest first
        status_priority = {"running": 0, "parked": 1, "human_takeover": 2, "succeeded": 3, "failed": 4, "blocked": 5, "closed": 6}
        return sorted(tasks, key=lambda t: (status_priority.get(t.status, 9), -t.updated_at_ms))

    def update_task(self, task_id: str, **kwargs: Any) -> BrowserTaskRecord | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.updated_at_ms = int(time.time() * 1000)
        return task

    def add_timeline_step(self, task_id: str, action: str, detail: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        step = {
            "step_index": len(task.timeline) + 1,
            "action": action,
            "detail": detail,
            "timestamp_ms": int(time.time() * 1000),
        }
        task.timeline.append(step)
        task.updated_at_ms = step["timestamp_ms"]

    def close_task(self, task_id: str, reason: str | None = None) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = "closed"
        task.updated_at_ms = int(time.time() * 1000)
        self.add_timeline_step(task_id, "close", reason or "Task terminated by user/agent")
        return True

    def set_captcha_preference(
        self,
        choice: str,
        scope_kind: str = "all_tasks",
        scope_value: str | None = None,
        statement: str = "",
    ) -> None:
        key = "all_tasks"
        if scope_kind == "site" and scope_value:
            key = f"site:{scope_value}"
        elif scope_kind == "task" and scope_value:
            key = f"task:{scope_value}"
        self._captcha_preferences[key] = {
            "choice": choice,
            "scope_kind": scope_kind,
            "scope_value": scope_value,
            "statement": statement,
            "timestamp_ms": int(time.time() * 1000),
        }

    def get_captcha_preference(self, site: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        if task_id and f"task:{task_id}" in self._captcha_preferences:
            return self._captcha_preferences[f"task:{task_id}"]
        if site and f"site:{site}" in self._captcha_preferences:
            return self._captcha_preferences[f"site:{site}"]
        if "all_tasks" in self._captcha_preferences:
            return self._captcha_preferences["all_tasks"]
        return {"choice": "solve", "scope_kind": "all_tasks", "scope_value": None, "statement": "default"}


_SHARED_TASK_STORE = BrowserTaskStore()


def get_shared_task_store() -> BrowserTaskStore:
    """SSOT singleton accessor for browser task store."""
    return _SHARED_TASK_STORE
