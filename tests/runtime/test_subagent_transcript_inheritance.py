"""INV-SUBAGENT-TRANSCRIPT-INHERITANCE — the standing snapshot a subagent inherits.

A derived agent inherits a bounded standing snapshot assembled from the same
five files the parent sees. This test drives the shipped assembly and
re-injection functions that produce that snapshot.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from lca.contracts.harness.collaboration.agent import AgentIdentity, AgentOptions
from lca.contracts.harness.collaboration.subagent import SubagentRequest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.harness.subagents import SubagentActivationCoordinator, SubagentRegistry
from lca.infrastructure.memory.contextfiles.domain.standing import (
    assemble_standing,
    refresh_injected,
)
from lca.infrastructure.memory.contextfiles.service.assembly import refresh_standing_backstory
from lca.nodes.think.history.assemble import HistoryDeriveExecutor


def _files(tmp_path: Path) -> list[tuple[str, str]]:
    bodies = {
        "SOUL.md": "我是 LobeHub 助手。",
        "USER.md": "用户是系统架构师。",
        "MEMORY.md": "用户住在杭州。",
        "AGENTS.md": "回复要简洁。",
        "TOOLS.md": "用 bash 执行。",
    }
    for name, body in bodies.items():
        (tmp_path / name).write_text(body + "\n", encoding="utf-8")
    return list(bodies.items())


def test_assemble_standing_packs_all_five_files(tmp_path: Path) -> None:
    files = _files(tmp_path)
    snapshot = assemble_standing(files, budget_chars=10_000)
    for name, _body in files:
        assert f"<!-- INJECTED FILE: {name} -->" in snapshot
        assert f"<!-- END INJECTED FILE: {name} -->" in snapshot


def test_assemble_standing_respects_budget(tmp_path: Path) -> None:
    files = _files(tmp_path)
    snapshot = assemble_standing(files, budget_chars=200)
    assert len(snapshot) <= 200
    assert "<!-- INJECTED FILE: SOUL.md -->" in snapshot


def test_refresh_injected_rebuilds_the_snapshot_from_disk(tmp_path: Path) -> None:
    files = _files(tmp_path)
    snapshot = assemble_standing(files, budget_chars=10_000)
    # The disk changes; the inherited snapshot must be refreshed, not kept stale.
    (tmp_path / "MEMORY.md").write_text("用户搬到北京。\n", encoding="utf-8")
    refreshed = refresh_injected(
        snapshot,
        [("MEMORY.md", "用户搬到北京。\n")],
        order=("SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md"),
    )
    assert "用户搬到北京" in refreshed
    assert "用户住在杭州" not in refreshed


@dataclass
class _Trace:
    system_prompt_text: str = ""


@dataclass
class _Render:
    trace: _Trace | None = None


@dataclass
class _Header:
    system: str | None


class _Writer:
    def derive_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": "调研"}]

    def request_header(self) -> _Header:
        return _Header(system=None)


def test_home_bound_assembly_injects_standing_files_without_markers(tmp_path: Path) -> None:
    files = _files(tmp_path)
    (tmp_path / "AGENTS.md").write_text("严禁未经基准测试擅自引入依赖\n", encoding="utf-8")
    out = asyncio.run(
        HistoryDeriveExecutor().node_execute(
            context=NodeContext(runtime={"home_path": str(tmp_path)}, budget={}, metadata={}),
            input=NodeInput(
                port_values={
                    "state": AgentState(trace_id="trace-child", task="", budget=Budget()),
                    "writer": _Writer(),
                    "turn_render": _Render(trace=_Trace(system_prompt_text="你是研究员。")),
                }
            ),
        )
    )
    system = out.port_values["model_visible_request"].system
    assert "严禁未经基准测试擅自引入依赖" in system
    for name, _body in files:
        assert f"<!-- INJECTED FILE: {name} -->" in system


def test_spawn_forwards_the_parent_standing_snapshot(tmp_path: Path) -> None:
    _files(tmp_path)
    snapshot = refresh_standing_backstory(str(tmp_path), "")
    created: list[AgentOptions] = []

    async def _activate(_spec, _identity, options: AgentOptions):
        created.append(options)

        class _Handle:
            async def dispose(self, _reason: str) -> None:
                return None

        return _Handle()

    from lca.contracts.harness.collaboration.subagent import SubagentCapabilities, SubagentSpec

    registry = SubagentRegistry()
    registry.register(
        SubagentSpec(
            "researcher",
            SubagentCapabilities(capabilities=frozenset({"research"})),
        )
    )
    coordinator = SubagentActivationCoordinator(registry, _activate)
    asyncio.run(
        coordinator.activate(
            SubagentRequest(
                "researcher",
                AgentIdentity("parent"),
                options=AgentOptions(standing_snapshot=snapshot),
            )
        )
    )
    assert "<!-- INJECTED FILE: SOUL.md -->" in created[0].standing_snapshot
    assert "我是 LobeHub 助手。" in created[0].standing_snapshot
