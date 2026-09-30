"""INV-FS-WATCHER-FAULT-TOLERANCE — a watcher fault never blocks assembly."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.memory.contextfiles.adapters.realtime import FaultInjectingWatcher
from lca.nodes.think.history.assemble import HistoryDeriveExecutor


@dataclass
class _StubPromptTrace:
    system_prompt_text: str = ""


@dataclass
class _StubReasonerTurnRender:
    trace: _StubPromptTrace | None = None


@dataclass
class _StoredHeader:
    system: str | None


class _FakeWriter:
    def __init__(self, messages: list[dict], system: str | None = None) -> None:
        self._messages = messages
        self._header = _StoredHeader(system=system)

    def derive_messages(self) -> list[dict]:
        return list(self._messages)

    def request_header(self) -> _StoredHeader | None:
        return self._header


def _render(system_text: str) -> _StubReasonerTurnRender:
    return _StubReasonerTurnRender(trace=_StubPromptTrace(system_prompt_text=system_text))


def _state() -> AgentState:
    return AgentState(trace_id="trace-fault", task="", budget=Budget())


def _assemble(home: Path) -> str:
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system=None)
    out = asyncio.run(
        HistoryDeriveExecutor().node_execute(
            context=NodeContext(runtime={"home_path": str(home)}, budget={}, metadata={}),
            input=NodeInput(
                port_values={
                    "state": _state(),
                    "writer": writer,
                    "turn_render": _render("你是 LobeHub 助手。"),
                }
            ),
        )
    )
    return out.port_values["model_visible_request"].system


def test_faulty_watcher_does_not_block_assembly(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("人设\n", encoding="utf-8")
    watcher = FaultInjectingWatcher(str(tmp_path), interval_s=0.05)
    watcher.start()
    try:
        time.sleep(0.2)  # let the faulting loop run a few times
        system = _assemble(tmp_path)
        assert "你是 LobeHub 助手。" in system
        assert "常驻文件有更新" not in system
        assert any(line.startswith("WATCHER_FAULT") for line in watcher.faults)
    finally:
        watcher.stop()
