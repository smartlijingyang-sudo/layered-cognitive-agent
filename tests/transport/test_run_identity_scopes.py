"""HIL resume 与初始执行共享的 run 环境 scope（回归锁）。

历史缺陷：resume 路径漏绑 ``run_id_scope``，导致 resume 期间 sandbox 工具报
``sandbox runtime requires an active run_id scope``。本测试锁定共享 helper
必须同时绑定 run_id / attachment / search 三个环境变量，并驱动真实 resume
代码路径验证 resume 期间 run_id 可见。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.search.scope.scope import get_search_run_state
from lca.infrastructure.tools.run.attachment_scope import get_current_run_attachment_ids
from lca.infrastructure.tools.run.finalizer import get_current_run_id
from lca.plugins.transport.webserver.carrier.runs.run_scopes import run_identity_scopes


class TestRunIdentityScopes(unittest.TestCase):
    def test_binds_run_attachment_and_search_ambits(self) -> None:
        with run_identity_scopes("run_scope_test", ("att-1", "att-2")):
            self.assertEqual(get_current_run_id(), "run_scope_test")
            self.assertEqual(get_current_run_attachment_ids(), ("att-1", "att-2"))
            self.assertIsNotNone(get_search_run_state())

    def test_resets_after_exit(self) -> None:
        with run_identity_scopes("run_scope_test"):
            pass
        self.assertEqual(get_current_run_id(), "")
        self.assertEqual(get_current_run_attachment_ids(), ())


class TestResumeEntersRunIdentityScopes(unittest.IsolatedAsyncioTestCase):
    async def test_resume_binds_run_id_for_sandbox_tools(self) -> None:
        from lca.plugins.transport.webserver.carrier.runs.lifecycle.lifecycle import (
            RunLifecycleCoordinator,
        )
        from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
            RunSession,
        )

        async def _resume_asserting_scope(snapshot: object, input: str) -> SimpleNamespace:
            del snapshot, input
            self.assertEqual(get_current_run_id(), "run_resume_scope")
            return SimpleNamespace(status=TaskStatus.COMPLETED)

        session = RunSession(
            run_id="run_resume_scope",
            trace_id="trace_resume_scope",
            spine_path=Path("traces/resume_scope.spine.jsonl"),
            tail=MagicMock(name="tail"),
            question="q",
            user_text="q",
            mode="solo",
        )
        session.status = RunLifecycleStatus.WAITING_INPUT
        session.snapshot = object()
        session.runnable = MagicMock(name="runnable")
        session.runnable.resume = AsyncMock(side_effect=_resume_asserting_scope)  # type: ignore[method-assign]

        registry = MagicMock(name="registry")
        coordinator = RunLifecycleCoordinator(registry)  # type: ignore[arg-type]
        coordinator._outcomes = MagicMock(name="outcomes")
        coordinator._outcomes.apply_resume.return_value = False
        coordinator._finish_or_pause = AsyncMock()  # type: ignore[method-assign]

        await coordinator.resume(session, answer="ok")

        session.runnable.resume.assert_awaited_once()
        coordinator._outcomes.apply_resume.assert_called_once()


if __name__ == "__main__":
    unittest.main()
