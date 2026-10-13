"""Regression tests for the thin legacy execution compatibility facade."""

from __future__ import annotations

import unittest
from importlib import import_module
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)


class _Coordinator:
    def __init__(self) -> None:
        self.execute_calls: list[dict[str, Any]] = []
        self.resume_calls: list[tuple[RunSession, str]] = []

    async def execute(self, **kwargs: Any) -> None:
        self.execute_calls.append(kwargs)

    async def resume(self, session: RunSession, *, answer: str) -> None:
        self.resume_calls.append((session, answer))


class TestRunExecutionFacade(unittest.IsolatedAsyncioTestCase):
    async def test_execute_delegates_full_request_to_lifecycle_coordinator(self) -> None:
        registry = RunRegistry()
        coordinator = _Coordinator()
        context = object()
        execution_module = import_module("lca.plugins.transport.webserver.carrier.runs.execute")

        with patch.object(
            execution_module,
            "RunLifecycleCoordinator",
            return_value=coordinator,
        ) as factory:
            await execution_module.execute_run(
                registry,
                run_id="run-1",
                question="请执行任务",
                mode="solo",
                ctx=context,
            )

        factory.assert_called_once_with(registry, machine_resolver=None)
        self.assertEqual(
            coordinator.execute_calls,
            [
                {
                    "run_id": "run-1",
                    "question": "请执行任务",
                    "mode": "solo",
                    "ctx": context,
                }
            ],
        )

    async def test_resume_delegates_answer_to_lifecycle_coordinator(self) -> None:
        from lca.infrastructure.runtime_plane.access.approved_tools import (
            get_approved_tool_names,
        )

        registry = RunRegistry()
        coordinator = _Coordinator()
        # 2e8264fb4 后 resume_run 读取 session.approved_tool_names 注入当前
        # context；裸 object() 已不满足接口，用满足新接口的最小 stand-in。
        session = cast(
            "RunSession",
            SimpleNamespace(event_session=None, approved_tool_names={"tool_fs.read"}),
        )
        execution_module = import_module("lca.plugins.transport.webserver.carrier.runs.execute")

        with patch.object(
            execution_module,
            "RunLifecycleCoordinator",
            return_value=coordinator,
        ) as factory:
            await execution_module.resume_run(session, registry, "批准")

        factory.assert_called_once_with(registry)
        self.assertEqual(coordinator.resume_calls, [(session, "批准")])
        self.assertEqual(get_approved_tool_names(), frozenset({"tool_fs.read"}))


if __name__ == "__main__":
    unittest.main()
