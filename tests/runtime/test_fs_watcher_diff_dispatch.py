"""INV-FS-WATCHER-DIFF-DISPATCH — a standing-file edit reaches the next assembly."""

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
from lca.infrastructure.memory.contextfiles.adapters.polling import (
    ensure_standing_watcher,
    reset_standing_cursors,
)
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
    return AgentState(trace_id="trace-watch", task="", budget=Budget())


def _executor() -> HistoryDeriveExecutor:
    return HistoryDeriveExecutor()


def _assemble(home: Path) -> str:
    writer = _FakeWriter(messages=[{"role": "user", "content": "hi"}], system=None)
    out = asyncio.run(
        _executor().node_execute(
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


def test_edit_reaches_next_assembly_within_watch_interval(tmp_path: Path) -> None:
    reset_standing_cursors()
    try:
        (tmp_path / "SOUL.md").write_text("旧人设\n", encoding="utf-8")
        watcher = ensure_standing_watcher(str(tmp_path), interval_s=0.05)
        time.sleep(0.2)  # let the watcher establish its baseline
        first = _assemble(tmp_path)
        assert "常驻文件有更新" not in first
        assert "你是 LobeHub 助手。" in first

        (tmp_path / "SOUL.md").write_text("新人设\n", encoding="utf-8")
        deadline = time.monotonic() + 1.0
        second = ""
        while time.monotonic() < deadline:
            second = _assemble(tmp_path)
            if "常驻文件有更新" in second:
                break
            time.sleep(0.05)
        assert "常驻文件有更新" in second
        assert "旧人设" in second
        assert "新人设" in second
        assert watcher.consume() == ""
    finally:
        reset_standing_cursors()
