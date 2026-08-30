"""Regression tests for the thin legacy execution compatibility facade."""

from __future__ import annotations

import unittest
from importlib import import_module
from typing import Any, cast
from unittest.mock import patch

from gateway.runs.session.session import RunRegistry, RunSession


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
        execution_module = import_module("gateway.runs.execute")

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
        registry = RunRegistry()
        coordinator = _Coordinator()
        session = cast("RunSession", object())
        execution_module = import_module("gateway.runs.execute")

        with patch.object(
            execution_module,
            "RunLifecycleCoordinator",
            return_value=coordinator,
        ) as factory:
            await execution_module.resume_run(session, registry, "批准")

        factory.assert_called_once_with(registry)
        self.assertEqual(coordinator.resume_calls, [(session, "批准")])


if __name__ == "__main__":
    unittest.main()
