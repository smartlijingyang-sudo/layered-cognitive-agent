"""Run-scoped assistant binding regression locks (``cbed37f30`` follow-up).

Historical defect (2026-10-03): a global ``LCA_ASSISTANT_ID`` env default
silently pointed every assistant's sandbox at the same workspace. The fix
added ``run_assistant_scope`` plus the ``assistant_id`` parameter on
``run_identity_scopes``, bound at the two carrier entries (initial execution
and HIL resume) — but no test pinned the binding itself: dropping the third
positional argument at either call site would silently re-introduce the
aliasing with zero red tests.

These nails lock:
1. ``run_identity_scopes``' third argument flows into ``run_assistant_scope``
   (visible via ``get_current_assistant_id()``), and resets after exit.
2. The HIL resume path binds the *session's* assistant id (drives the real
   ``RunLifecycleCoordinator.resume`` code path, mirroring the run_id nail).
3. End-to-end: inside resume, ``assistant_workspace_root()`` resolves to the
   run's assistant workspace, NOT the global ``LCA_ASSISTANT_ID`` default.

Honest boundary: the initial-execution entry
(``execution_environment.prepare()``) passes the same ``assistant_id`` into
the same helper, but driving ``prepare()`` needs full provider/binding fakes
and is out of scope here — its call site is not pinned by these tests.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.path.locator import assistant_workspace_root
from lca.infrastructure.tools.run.assistant_scope import get_current_assistant_id
from lca.plugins.transport.webserver.carrier.runs.run_scopes import (
    run_identity_scopes,
)

_SSOT_ENV_KEYS = (
    "LCA_WORKSPACE_ROOT",
    "LCA_LOCAL_SANDBOX_ROOT",
    "LCA_ASSISTANT_ID",
    "LCA_HOME",
)


def _expected_assistant_workspace(home: str, assistant_id: str) -> str:
    """Sync helper: mirrors assistant_workspace_root for a LCA_HOME root.

    Kept out of the async test body so no blocking pathlib call lands
    inside an async function (ASYNC240).
    """
    return str(Path(home).resolve() / "assistants" / assistant_id / "workspace")


class TestRunIdentityScopesAssistantBinding(unittest.TestCase):
    def test_third_arg_flows_into_assistant_scope(self) -> None:
        with run_identity_scopes("run_asst_bind", (), "asst_x"):
            self.assertEqual(get_current_assistant_id(), "asst_x")

    def test_default_assistant_id_is_empty_string(self) -> None:
        with run_identity_scopes("run_asst_default"):
            self.assertEqual(get_current_assistant_id(), "")

    def test_resets_assistant_id_after_exit(self) -> None:
        with run_identity_scopes("run_asst_reset", (), "asst_y"):
            pass
        self.assertEqual(get_current_assistant_id(), "")

    def test_none_assistant_id_treated_as_empty(self) -> None:
        with run_identity_scopes("run_asst_none", (), None):  # type: ignore[arg-type]
            self.assertEqual(get_current_assistant_id(), "")


class TestResumeBindsAssistantIdForWorkspaceSsot(unittest.IsolatedAsyncioTestCase):
    async def test_resume_binds_session_assistant_id(self) -> None:
        from lca.plugins.transport.webserver.carrier.runs.lifecycle.lifecycle import (
            RunLifecycleCoordinator,
        )
        from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
            RunSession,
        )

        seen: dict[str, str] = {}

        async def _resume_asserting_scope(snapshot: object, input: str) -> SimpleNamespace:
            del snapshot, input
            # 1) lifecycle 把 session.assistant_id 传入了 run_identity_scopes
            seen["assistant_id"] = get_current_assistant_id()
            # 2) SSOT 按 run 解析：run 的 assistant 赢过全局默认
            seen["workspace"] = str(assistant_workspace_root())
            return SimpleNamespace(status=TaskStatus.COMPLETED)

        session = RunSession(
            run_id="run_resume_asst",
            trace_id="trace_resume_asst",
            spine_path=Path("traces/resume_asst.spine.jsonl"),
            tail=MagicMock(name="tail"),
            question="q",
            user_text="q",
            mode="solo",
        )
        session.status = RunLifecycleStatus.WAITING_INPUT
        session.snapshot = object()
        session.assistant_id = "asst_resume"
        session.runnable = MagicMock(name="runnable")
        session.runnable.resume = AsyncMock(  # type: ignore[method-assign]
            side_effect=_resume_asserting_scope
        )

        registry = MagicMock(name="registry")
        coordinator = RunLifecycleCoordinator(registry)  # type: ignore[arg-type]
        coordinator._outcomes = MagicMock(name="outcomes")
        coordinator._outcomes.apply_resume.return_value = False
        coordinator._finish_or_pause = AsyncMock()  # type: ignore[method-assign]

        with tempfile.TemporaryDirectory() as home:
            expected = _expected_assistant_workspace(home, "asst_resume")
            env = {k: v for k, v in os.environ.items() if k not in _SSOT_ENV_KEYS}
            env["LCA_HOME"] = home
            env["LCA_ASSISTANT_ID"] = "asst_global_default"
            with patch.dict(os.environ, env, clear=True):
                await coordinator.resume(session, answer="ok")

        session.runnable.resume.assert_awaited_once()
        self.assertEqual(seen["assistant_id"], "asst_resume")
        self.assertEqual(seen["workspace"], str(expected))


if __name__ == "__main__":
    unittest.main()
