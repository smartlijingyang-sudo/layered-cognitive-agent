"""Regression coverage for the ordinary Session command execution seam."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.harness.agent import MessageReceipt
from lca.contracts.harness.command import CommandReceipt
from lca.harness.agent.live_command_executor import LiveCommandExecutor


@dataclass
class _Store:
    current_seq: int


@dataclass
class _Handle:
    agent: object


@dataclass
class _Entry:
    handle: _Handle
    store: _Store


class _Activator:
    def __init__(self, entry: _Entry | None) -> None:
        self.entry = entry
        self.recovered: list[str] = []

    async def entry_or_recover(self, session_id: str) -> _Entry | None:
        self.recovered.append(session_id)
        return self.entry


async def _reject(session_id: str, command_id: str, reason: str) -> CommandReceipt:
    return CommandReceipt(
        command_id=command_id,
        session_id=session_id,
        seq=-1,
        accepted=False,
        rejection_reason=reason,
    )


@pytest.mark.asyncio
async def test_executor_recovers_live_owner_and_uses_message_receipt_sequence() -> None:
    agent = object()
    activator = _Activator(_Entry(handle=_Handle(agent), store=_Store(current_seq=3)))
    executor = LiveCommandExecutor(activator=activator, reject=_reject)  # type: ignore[arg-type]

    async def _steer(actual_agent: object) -> MessageReceipt:
        assert actual_agent is agent
        return MessageReceipt(message_id="msg-1", session_id="ses-1", seq=7)

    receipt = await executor.execute(
        session_id="ses-1",
        command_id="cmd-1",
        command=_steer,  # type: ignore[arg-type]
    )

    assert activator.recovered == ["ses-1"]
    assert receipt == CommandReceipt(command_id="cmd-1", session_id="ses-1", seq=7, accepted=True)


@pytest.mark.asyncio
async def test_executor_projects_non_message_command_at_current_session_sequence() -> None:
    agent = object()
    entry = _Entry(handle=_Handle(agent), store=_Store(current_seq=3))
    activator = _Activator(entry)
    executor = LiveCommandExecutor(activator=activator, reject=_reject)  # type: ignore[arg-type]

    async def _cancel(actual_agent: object) -> None:
        assert actual_agent is agent
        entry.store.current_seq = 8

    receipt = await executor.execute(
        session_id="ses-1",
        command_id="cmd-2",
        command=_cancel,  # type: ignore[arg-type]
    )

    assert receipt == CommandReceipt(command_id="cmd-2", session_id="ses-1", seq=8, accepted=True)


@pytest.mark.asyncio
async def test_executor_rejects_unknown_session_without_invoking_command() -> None:
    executor = LiveCommandExecutor(activator=_Activator(None), reject=_reject)  # type: ignore[arg-type]
    invoked = False

    async def _command(_: object) -> MessageReceipt:
        nonlocal invoked
        invoked = True
        return MessageReceipt(message_id="unexpected", session_id="ses-missing", seq=0)

    receipt = await executor.execute(
        session_id="ses-missing",
        command_id="cmd-missing",
        command=_command,  # type: ignore[arg-type]
    )

    assert not invoked
    assert receipt == CommandReceipt(
        command_id="cmd-missing",
        session_id="ses-missing",
        seq=-1,
        accepted=False,
        rejection_reason="unknown session",
    )
