"""HIL resume 的并发语义回归锁:check-then-act 必须不可分割。

Two concurrent ``resume_approval`` calls carrying **different** idempotency keys
must never both flip ``WAITING_INPUT → RUNNING`` and both schedule ``resume_run``.
The existing replay dedup only covers the same key twice, so this file pins the
guard for competing answers.

The guard is not an explicit lock. ``RegistryRunCommands.resume_approval`` has no
suspension point anywhere in its body, so once the event loop starts it, the
dedup check, the status check, the status flip, the key recording and the
``create_task`` all run before any other task can be scheduled. That is enough for
the deployed topology: one uvicorn process on one event loop (``uvicorn.Config``
sets no ``workers`` and no carrier handler reaches the registry from a thread or a
second loop), and a process-local ``RunRegistry`` — a second process would not own
the session at all, so ``resume_approval`` there answers ``run not found``.

``test_resume_approval_critical_section_never_suspends`` enforces that structural
invariant (adding an ``await`` inside the section fails the test and then requires
a real per-session lock), ``test_no_peer_task_runs_during_resume_approval`` shows
the same on a live loop, and ``test_control_replica_with_await_double_resumes``
proves the concurrency assertions actually detect an interleaved check-then-act
rather than passing vacuously.
"""

from __future__ import annotations

import asyncio
import dis
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
    RunCommandReceipt,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.registry import (
    commands as registry_commands,
)

if TYPE_CHECKING:
    import pytest

_RUN_ID = "run-conc-1"
_APPROVAL_ID = "plan:think.main:1"


def _waiting_session() -> RunSession:
    session = RunSession(
        run_id=_RUN_ID,
        trace_id="trace-conc-1",
        spine_path=Path("traces/conc.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="q",
        user_text="q",
        mode="solo",
    )
    session.status = RunLifecycleStatus.WAITING_INPUT
    session.snapshot = object()
    session.runnable = object()
    session.approval_request = {
        "type": "ask_user_question",
        "approval_id": _APPROVAL_ID,
    }
    return session


def _commands_for(session: RunSession) -> registry_commands.RegistryRunCommands:
    class _RegistryStub:
        def get(self, run_id: str) -> RunSession | None:
            return session if run_id == _RUN_ID else None

    return registry_commands.RegistryRunCommands(_RegistryStub())  # type: ignore[arg-type]


def _install_counting_resume(
    monkeypatch: pytest.MonkeyPatch,
    scheduled: list[str],
) -> None:
    """Replace ``resume_run`` so a scheduled resume is observable."""

    async def _counting_resume(session: RunSession, registry: object, answer: str) -> None:
        scheduled.append(answer)

    monkeypatch.setattr(registry_commands, "resume_run", _counting_resume)


async def _resume(
    commands: registry_commands.RegistryRunCommands, payload: str, key: str
) -> RunCommandReceipt:
    return await commands.resume_approval(
        run_id=_RUN_ID,
        approval_id="askUserQuestion",
        payload=payload,
        idempotency_key=key,
    )


async def _drain(session: RunSession) -> None:
    """Let every task scheduled by ``resume_approval`` actually run."""
    for _ in range(4):
        await asyncio.sleep(0)
    if session.task is not None and not session.task.done():
        await session.task


# --------------------------------------------------------------------------- #
# concurrent different-key resumes
# --------------------------------------------------------------------------- #


def test_concurrent_distinct_keys_resume_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two answers racing on one pause: exactly one may resume the run."""
    scheduled: list[str] = []
    session = _waiting_session()
    commands = _commands_for(session)
    _install_counting_resume(monkeypatch, scheduled)

    async def _scenario() -> tuple[RunCommandReceipt, RunCommandReceipt]:
        first, second = await asyncio.gather(
            _resume(commands, "answer-1", "k-1"),
            _resume(commands, "answer-2", "k-2"),
        )
        await _drain(session)
        return first, second

    first, second = asyncio.run(_scenario())

    receipts = (first, second)
    winners = [r for r in receipts if r.accepted]
    losers = [r for r in receipts if not r.accepted]
    assert len(winners) == 1, f"exactly one resume may be accepted, got {receipts}"
    assert len(losers) == 1
    assert losers[0].error_status == 409
    assert losers[0].error == "run not waiting for input"
    assert scheduled == ["answer-1" if first.accepted else "answer-2"]
    assert session.status is RunLifecycleStatus.RUNNING
    # The loser must not leave its key behind, otherwise a later legitimate
    # answer carrying that key would be silently swallowed as a replay.
    assert session.accepted_answer_keys == ({"k-1"} if first.accepted else {"k-2"})


def test_concurrent_same_key_resumes_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same key racing itself keeps the cheap replay: one resume, two receipts."""
    scheduled: list[str] = []
    session = _waiting_session()
    commands = _commands_for(session)
    _install_counting_resume(monkeypatch, scheduled)

    async def _scenario() -> tuple[RunCommandReceipt, RunCommandReceipt]:
        first, second = await asyncio.gather(
            _resume(commands, "answer-1", "k-dup"),
            _resume(commands, "answer-1", "k-dup"),
        )
        await _drain(session)
        return first, second

    first, second = asyncio.run(_scenario())

    assert first.accepted and second.accepted
    assert first.status == second.status == "resumed"
    assert scheduled == ["answer-1"]
    assert session.accepted_answer_keys == {"k-dup"}


def test_concurrent_resume_after_cancel_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A resume arriving after cancel is a 409, never a second live owner."""
    scheduled: list[str] = []
    session = _waiting_session()
    commands = _commands_for(session)
    _install_counting_resume(monkeypatch, scheduled)

    class _NoopTerminalizer:
        def __init__(self, registry: object, **kwargs: object) -> None: ...

        async def terminalize(self, *args: object, **kwargs: object) -> None:
            session._closed = True

    monkeypatch.setattr(registry_commands, "RunTerminalizer", _NoopTerminalizer)

    async def _scenario() -> tuple[RunCommandReceipt, RunCommandReceipt]:
        receipts = await asyncio.gather(
            commands.cancel(_RUN_ID),
            _resume(commands, "answer-1", "k-1"),
        )
        await _drain(session)
        return receipts

    cancel_receipt, resume_receipt = asyncio.run(_scenario())

    assert cancel_receipt.accepted
    assert not resume_receipt.accepted
    assert resume_receipt.error_status == 409
    assert scheduled == []
    assert session.status is RunLifecycleStatus.CANCELLED


# --------------------------------------------------------------------------- #
# why no lock is needed: the critical section cannot yield
# --------------------------------------------------------------------------- #

# CPython 3.11–3.14 lower every ``await``/``async for``/``async with`` to members
# of this set; a coroutine function whose instruction stream contains none of them
# can never suspend, so no other task can interleave inside its critical section.
# ``cancel`` is the positive control — if a future interpreter stops emitting these
# opcodes, its assertion fails and this probe gets updated instead of going quiet.
_SUSPENSION_OPS = frozenset({"GET_AWAITABLE", "YIELD_VALUE", "SEND"})


def _suspension_ops(func: Callable[..., object]) -> frozenset[str]:
    return frozenset(
        instruction.opname
        for instruction in dis.get_instructions(func.__code__)
        if instruction.opname in _SUSPENSION_OPS
    )


def test_resume_approval_critical_section_never_suspends() -> None:
    """``resume_approval`` runs check-then-act without yielding to the loop."""
    # The probe itself must be sound: ``cancel`` awaits and has to register.
    assert _suspension_ops(registry_commands.RegistryRunCommands.cancel) <= _SUSPENSION_OPS
    assert _suspension_ops(registry_commands.RegistryRunCommands.cancel)

    assert _suspension_ops(registry_commands.RegistryRunCommands.resume_approval) == frozenset()


def test_no_peer_task_runs_during_resume_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Functional twin of the bytecode check: the loop cannot interleave here."""
    scheduled: list[str] = []
    session = _waiting_session()
    commands = _commands_for(session)
    _install_counting_resume(monkeypatch, scheduled)

    ticks = 0
    watching = True

    async def _canary() -> None:
        """Yield every loop pass; any suspension under test lets it tick."""
        nonlocal ticks
        while watching:
            ticks += 1
            await asyncio.sleep(0)

    async def _scenario() -> None:
        nonlocal watching
        canary_task = asyncio.create_task(_canary())
        for _ in range(5):
            await asyncio.sleep(0)
        ticks_at_check = ticks
        await _resume(commands, "answer-1", "k-1")
        assert ticks == ticks_at_check, "resume_approval yielded control to the event loop"
        watching = False
        await canary_task
        await _drain(session)

    asyncio.run(_scenario())
    assert scheduled == ["answer-1"]


def test_control_replica_with_await_double_resumes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: one suspension point in the section *does* resume twice.

    This is the shape ``resume_approval`` would have if an ``await`` were inserted
    between the status check and the status flip. If this test ever stops
    catching the double resume, the concurrency assertions above prove nothing.
    """
    scheduled: list[str] = []
    session = _waiting_session()
    _install_counting_resume(monkeypatch, scheduled)

    both_started = asyncio.Barrier(2)

    async def _replica_with_await(payload: str, key: str) -> RunCommandReceipt:
        # Same checks as the real command …
        assert key not in session.accepted_answer_keys
        assert session.status is RunLifecycleStatus.WAITING_INPUT
        # … then a yield before the mutation (the bug under audit).
        await both_started.wait()
        session.status = RunLifecycleStatus.RUNNING
        session.accepted_answer_keys.add(key)
        session.task = asyncio.create_task(
            registry_commands.resume_run(session, None, payload)  # type: ignore[arg-type]
        )
        return registry_commands.RunCommandReceipt(accepted=True, status="resumed")

    async def _scenario() -> None:
        await asyncio.gather(
            _replica_with_await("answer-1", "k-1"),
            _replica_with_await("answer-2", "k-2"),
        )
        await _drain(session)

    asyncio.run(_scenario())

    assert sorted(scheduled) == ["answer-1", "answer-2"], "control lost its detection power"
    assert session.accepted_answer_keys == {"k-1", "k-2"}


# --------------------------------------------------------------------------- #
# sequential cross-tab replay (the case the concurrent tests are paired with)
# --------------------------------------------------------------------------- #


def test_sequential_second_tab_replays_first_tab_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tab 2 submitting tab 1's key after it landed replays instead of resuming."""
    scheduled: list[str] = []
    session = _waiting_session()
    commands = _commands_for(session)
    _install_counting_resume(monkeypatch, scheduled)

    async def _scenario() -> tuple[RunCommandReceipt, RunCommandReceipt]:
        tab_1 = await _resume(commands, "answer-1", "run:msg-1:submit")
        await _drain(session)
        tab_2 = await _resume(commands, "answer-1", "run:msg-1:submit")
        await _drain(session)
        return tab_1, tab_2

    tab_1, tab_2 = asyncio.run(_scenario())

    assert tab_1.accepted and tab_2.accepted
    assert tab_2.status == "resumed"
    assert scheduled == ["answer-1"]
    assert session.accepted_answer_keys == {"run:msg-1:submit"}


def test_sequential_second_tab_with_new_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A different answer arriving after the run already resumed is a 409."""
    scheduled: list[str] = []
    session = _waiting_session()
    commands = _commands_for(session)
    _install_counting_resume(monkeypatch, scheduled)

    async def _scenario() -> tuple[RunCommandReceipt, RunCommandReceipt]:
        tab_1 = await _resume(commands, "answer-1", "k-1")
        await _drain(session)
        tab_2 = await _resume(commands, "answer-2", "k-2")
        await _drain(session)
        return tab_1, tab_2

    tab_1, tab_2 = asyncio.run(_scenario())

    assert tab_1.accepted
    assert not tab_2.accepted
    assert tab_2.error_status == 409
    assert scheduled == ["answer-1"]
    assert session.accepted_answer_keys == {"k-1"}
