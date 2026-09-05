"""Regression lock: HIL resume re-binds the run's ambient RunAmbit.

Before the fix, ``RunLifecycleCoordinator.resume`` only re-bound
``plane_bindings_scope``; the resumed think's prompt rendering then raised
``RuntimeError("no FileStore in ambient scope")`` because ``current_file_store()``
returned None. This test asserts the FileStore captured on the session's
``ambit`` at execute-prepare time is visible again inside ``runnable.resume``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

# isort: off
# Importing the terminal commands first initialises the execute package in the
# app's order and avoids the lifecycle<->execute circular import that occurs
# when lifecycle.lifecycle is the first module loaded.
from lca.plugins.transport.webserver.handlers.runs.terminal import registry_commands  # noqa: F401
from lca.infrastructure.observability.facade.run_ambit import RunAmbit, current_file_store
from lca.plugins.transport.webserver.handlers.runs.lifecycle.lifecycle import RunLifecycleCoordinator
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession, RunStatus
# isort: on


def _waiting_session() -> RunSession:
    session = RunSession(
        run_id="run-ambient-1",
        trace_id="trace-ambient-1",
        spine_path=Path("traces/ambient.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="q",
        user_text="q",
        mode="solo",
    )
    session.status = RunStatus.WAITING_INPUT
    session.snapshot = object()
    return session


class _RegistryStub:
    def __init__(self, session: RunSession) -> None:
        self._session = session

    def get(self, run_id: str) -> RunSession | None:
        return self._session if run_id == self._session.run_id else None

    def mark_paused(self, session: RunSession) -> None:  # pragma: no cover
        return None


def test_resume_rebinds_ambient_file_store(monkeypatch) -> None:
    store = MagicMock(name="file_store")
    session = _waiting_session()
    session.ambit = RunAmbit(
        run_id=session.run_id,
        trace_id=session.trace_id,
        file_store=store,
    )

    seen: dict[str, object] = {}

    class _Result:
        status = "completed"

    class _Runnable:
        async def resume(self, snapshot, *, input):
            seen["file_store"] = current_file_store()
            return _Result()

    session.runnable = _Runnable()

    # Avoid terminalization side effects; we only assert the ambient binding.
    async def _noop_finish(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(RunLifecycleCoordinator, "_finish_or_pause", staticmethod(_noop_finish))

    coordinator = RunLifecycleCoordinator(_RegistryStub(session))  # type: ignore[arg-type]

    async def _scenario() -> None:
        await coordinator.resume(session, answer="answer")

    asyncio.run(_scenario())

    assert seen.get("file_store") is store
