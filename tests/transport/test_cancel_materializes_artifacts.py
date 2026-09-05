"""取消与暂停路径的派生产物回归锁。

历史缺陷:run 在 WAITING_INPUT 被取消时,``cancel()`` 只翻转状态,
终态物化(``RunTerminalizer.terminalize`` → journal.json / narrative.md /
manifest.json)从不执行,被取消的 run 只剩原始流。

本文件锁定三条不变量:

1. 暂停态被取消 → 命令路径补齐终态物化,派生产物落盘。
2. 运行中被取消 → 命令路径不重复物化(生命周期 ``finally`` 负责)。
3. 暂停本身是增量派生点 → 等待输入期间 journal.json 已可读(outcome=paused)。

决策记录:[增量派生与取消闭环](../../docs/notes/implemented/seam/2026-09-05-incremental-journal-derive.md)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.plugins.observability.run_ledger_seam import _StepTreeBundle
from lca.plugins.session.derivers.step_tree import StepTreeFoldDeriver
from lca.plugins.transport.webserver.handlers.runs.observability.identity import (
    parse_agent_ref,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import (
    RunSession,
    RunStatus,
)

# registry_commands 必须先于 lifecycle 子模块被进程导入:它拉动 execute 包链,
# lifecycle 包的懒加载 __getattr__ 依赖该顺序打破循环。因此
# ``RunLifecycleCoordinator`` 在用例内局部导入(此时 execute 链已加载)。
from lca.plugins.transport.webserver.handlers.runs.terminal import registry_commands

if TYPE_CHECKING:
    import pytest


class _RegistryStub:
    """get / mark_paused / clear_inflight / prune —— cancel 与 lifecycle 所需最小面。"""

    def __init__(self, session: RunSession) -> None:
        self._session = session
        self.paused: list[str] = []
        self.cleared: list[str] = []
        self.pruned = 0

    def get(self, run_id: str) -> RunSession | None:
        return self._session if run_id == self._session.run_id else None

    def mark_paused(self, session: RunSession) -> None:
        self.paused.append(session.run_id)

    def clear_inflight(self, session_or_id: Any) -> None:
        run_id = session_or_id.run_id if isinstance(session_or_id, RunSession) else session_or_id
        self.cleared.append(run_id)

    def prune(self, now: float | None = None) -> int:
        self.pruned += 1
        return 0


def _paused_session(tmp_path: Path, run_id: str) -> tuple[RunSession, Path]:
    """带真实 step-tree bundle 的暂停态 session;返回 (session, run_dir)。"""
    locator = FilesystemRunLocator(root=tmp_path)
    run_dir = locator.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    spine_path = locator.events_path(run_id)
    session = RunSession(
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        spine_path=spine_path,
        tail=LiveTail(),
        question="q",
        user_text="q",
        mode="solo",
        agent=parse_agent_ref({"id": "solo", "name": "助手"}),
        status=RunStatus.WAITING_INPUT,
        started_at=1000.0,
        locator=locator,
    )
    session.step_tree_bundle = _StepTreeBundle(
        deriver=StepTreeFoldDeriver(
            run_id=run_id,
            run_dir=run_dir,
            spine_path=spine_path,
        ),
        narrative_writer=StepNarrativeWriter(run_dir / "journal.narrative.md"),
    )
    return session, run_dir


def _journal_outcome(run_dir: Path) -> str:
    payload = json.loads((run_dir / "journal.json").read_text(encoding="utf-8"))
    return str(payload["metadata"]["outcome"])


def test_cancel_paused_run_materializes_derived_artifacts(tmp_path: Path) -> None:
    """暂停态被取消 → journal.json / narrative.md / manifest.json 全部落盘。"""
    session, run_dir = _paused_session(tmp_path, "run_cancel_paused")
    commands = registry_commands.RegistryRunCommands(_RegistryStub(session))  # type: ignore[arg-type]

    receipt = asyncio.run(commands.cancel(session.run_id))

    assert receipt.accepted
    assert session.status is RunStatus.CANCELED
    assert session.closed, "cancel 必须走 terminalize 的 close 钩子"
    assert (run_dir / "journal.json").exists()
    assert (run_dir / "journal.narrative.md").exists()
    assert (run_dir / "manifest.json").exists()
    assert _journal_outcome(run_dir) == "stopped"


def test_cancel_paused_run_with_done_task_materializes(tmp_path: Path) -> None:
    """task 已完成(暂停后 task.done())的形态同样补齐终态物化。"""
    session, run_dir = _paused_session(tmp_path, "run_cancel_done_task")

    async def _finished() -> None:
        return None

    loop = asyncio.new_event_loop()
    task = loop.create_task(_finished())
    loop.run_until_complete(task)
    session.task = task

    commands = registry_commands.RegistryRunCommands(_RegistryStub(session))  # type: ignore[arg-type]
    receipt = loop.run_until_complete(commands.cancel(session.run_id))
    loop.close()

    assert receipt.accepted
    assert (run_dir / "journal.json").exists()
    assert (run_dir / "manifest.json").exists()


def test_cancel_running_task_leaves_terminalize_to_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行中取消 → 命令路径不物化;生命周期 finally 是唯一终态收口。"""
    session, _ = _paused_session(tmp_path, "run_cancel_running")
    session.status = RunStatus.RUNNING

    async def _long_running() -> None:
        await asyncio.sleep(30)

    async def _scenario() -> None:
        task = asyncio.create_task(_long_running())
        session.task = task
        constructed: list[Any] = []

        class _Recorder:
            def __init__(self, registry: Any, **kwargs: Any) -> None:
                constructed.append(self)

            async def terminalize(self, *args: Any, **kwargs: Any) -> None:
                raise AssertionError("cancel 命令路径不得对运行中 task 二次物化")

        monkeypatch.setattr(registry_commands, "RunTerminalizer", _Recorder)
        commands = registry_commands.RegistryRunCommands(_RegistryStub(session))  # type: ignore[arg-type]
        receipt = await commands.cancel(session.run_id)
        assert receipt.accepted
        assert task.cancelled()
        assert constructed == []

    asyncio.run(_scenario())


def test_cancel_already_closed_session_skips_terminalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close 钩子已跑过(生命周期已终态收口)→ exactly-once 守卫生效。"""
    session, _ = _paused_session(tmp_path, "run_cancel_closed")
    session.closed_at = 1100.0
    session.close("completed")
    constructed: list[Any] = []

    class _Recorder:
        def __init__(self, registry: Any, **kwargs: Any) -> None:
            constructed.append(self)

        async def terminalize(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("已 close 的 session 不得再次终态物化")

    monkeypatch.setattr(registry_commands, "RunTerminalizer", _Recorder)
    commands = registry_commands.RegistryRunCommands(_RegistryStub(session))  # type: ignore[arg-type]

    receipt = asyncio.run(commands.cancel(session.run_id))

    assert receipt.accepted
    assert constructed == []


def test_second_cancel_is_noop(tmp_path: Path) -> None:
    session, _ = _paused_session(tmp_path, "run_cancel_twice")
    commands = registry_commands.RegistryRunCommands(_RegistryStub(session))  # type: ignore[arg-type]

    first = asyncio.run(commands.cancel(session.run_id))
    second = asyncio.run(commands.cancel(session.run_id))

    assert first.accepted
    assert second.accepted
    assert second.status == RunStatus.CANCELED.value


def test_pause_flushes_journal_incrementally(tmp_path: Path) -> None:
    """WAITING_INPUT 是增量派生点:不等终态,暂停即写 journal.json。"""
    from lca.plugins.transport.webserver.handlers.runs.lifecycle import (
        RunLifecycleCoordinator,
    )

    session, run_dir = _paused_session(tmp_path, "run_pause_flush")
    registry = _RegistryStub(session)
    coordinator = RunLifecycleCoordinator(registry)  # type: ignore[arg-type]

    asyncio.run(coordinator._finish_or_pause(session, workspace=None, success=False))

    assert registry.paused == [session.run_id]
    assert (run_dir / "journal.json").exists()
    assert _journal_outcome(run_dir) == "paused"
    assert not session.closed, "暂停不得触发终态 close"


def test_pause_flush_failure_does_not_block_pause(tmp_path: Path) -> None:
    """派生失败只留痕,不阻塞暂停(控制面 / 观察面分离)。"""
    from lca.plugins.transport.webserver.handlers.runs.lifecycle import (
        RunLifecycleCoordinator,
    )

    session, _ = _paused_session(tmp_path, "run_pause_flush_fail")

    class _BrokenBundle:
        def flush(self, *, outcome: str = "stopped") -> None:
            raise OSError("disk full")

    session.step_tree_bundle = _BrokenBundle()
    registry = _RegistryStub(session)
    coordinator = RunLifecycleCoordinator(registry)  # type: ignore[arg-type]

    asyncio.run(coordinator._finish_or_pause(session, workspace=None, success=False))

    assert registry.paused == [session.run_id]


def test_flush_step_tree_artifacts_contains_errors(tmp_path: Path) -> None:
    from lca.plugins.transport.webserver.handlers.runs.observability.step_tree_flush import (
        flush_step_tree_artifacts,
        journal_outcome_from_session,
    )

    session, _ = _paused_session(tmp_path, "run_flush_errors")

    class _BrokenBundle:
        def flush(self, *, outcome: str = "stopped") -> None:
            raise OSError("disk full")

    session.step_tree_bundle = _BrokenBundle()

    errors = flush_step_tree_artifacts(session)

    assert len(errors) == 1
    assert errors[0]["operation"] == "step_tree.flush"
    assert errors[0]["error_type"] == "OSError"
    assert journal_outcome_from_session(session) == "paused"
