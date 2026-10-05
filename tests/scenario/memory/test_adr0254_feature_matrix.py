"""Feature matrix for the eleven ADR-0254 capabilities, through shipped code.

Each test drives the function that owns that capability. Prompt rules stand
in for model behavior: the retrieval tree, the anti-hallucination gate, and
the privacy firewall are the text the model is given.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.cognition.memory.acknowledgement import guard_reply
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.adapters.realtime import FaultInjectingWatcher
from lca.infrastructure.memory.contextfiles.domain.layout import validate_root_entries
from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing
from lca.infrastructure.memory.contextfiles.service.trail import (
    NarrowGateViolationError,
    TrailWriter,
)
from lca.infrastructure.memory.contextfiles.sync import (
    FileVersion,
    StaleSnapshotOperationError,
    require_fresh,
)
from lca.infrastructure.tools.assistant.memory_tools import MemoryAddTool, MemoryExplainTool
from lca.nodes.think.history.assemble import HistoryDeriveExecutor
from lca.plugins.prompts.sections.memory import MemoryRetrievalSection, PrivacyFirewallSection

_EIGHT = (
    "claim",
    "kind",
    "salience",
    "attribution",
    "quote",
    "timeline",
    "confidence",
    "supersession_chain",
)


def _role() -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "asst"},
    )


def test_f1_topology_rejects_unknown_root_md(tmp_path: Path) -> None:
    # IDENTITY.md used to be asserted as a violation here; commit 925a2e97f
    # promoted it into the 9-standing-file layout (layout.toml standing_files),
    # so it is whitelisted by design and no longer rejected.
    home = tmp_path / "asst"
    home.mkdir()
    for name in ("SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md", "IDENTITY.md"):
        (home / name).write_text("body\n", encoding="utf-8")
    (home / "NOT_A_STANDING.md").write_text("unknown root file\n", encoding="utf-8")
    violations = validate_root_entries(tuple(entry.name for entry in home.iterdir()))
    assert "NOT_A_STANDING.md" in violations
    assert "IDENTITY.md" not in violations
    assert "SOUL.md" not in violations


@pytest.mark.asyncio
async def test_f2_memory_explain_returns_eight_fields(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    added = await MemoryAddTool(memory=memory).execute(
        {"content": "架构遵循单向依赖", "category": "fact", "dedupe_key": "fact:layering"}
    )
    explained = await MemoryExplainTool(memory=memory).execute(
        {"record_id": added.payload["record_id"]}
    )
    assert explained.success is True
    for field in _EIGHT:
        assert field in explained.payload
    assert explained.payload["claim"] == "架构遵循单向依赖"
    assert explained.payload["kind"] == "fact"
    assert explained.payload["attribution"] == "user"
    assert explained.payload["confidence"] == 1.0
    assert explained.payload["supersession_chain"] == [added.payload["record_id"]]
    assert explained.payload["quote"] == ""


def test_f3_retrieval_tree_names_exemption_and_three_angles() -> None:
    text = (
        MemoryRetrievalSection()
        .render(
            role_profile=_role(),
            task="",
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )
    assert "豁免" in text
    assert "多角度" in text
    assert "memory_search" in text


@pytest.mark.asyncio
async def test_f4_acknowledgement_follows_a_committed_write(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    runtime = SimpleNamespace(memory=memory)
    assert guard_reply("已记下。", runtime) == "这条还没有写入记忆文件。我不能说已经记下。"
    obs = await MemoryAddTool(memory=memory).execute(
        {"content": "测试覆盖率必须达到 85%", "category": "fact"}
    )
    assert obs.success is True
    assert guard_reply("已记下。", runtime) == "已记下。"


def test_f5_stale_snapshot_is_rejected() -> None:
    with pytest.raises(StaleSnapshotOperationError):
        require_fresh(
            FileVersion(path="MEMORY.md", mtime_ns=1),
            FileVersion(path="MEMORY.md", mtime_ns=2),
        )


@pytest.mark.asyncio
async def test_f6_credential_write_fails_loud(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    obs = await MemoryAddTool(memory=memory).execute(
        {
            "content": "export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "category": "fact",
        }
    )
    assert obs.success is False
    assert obs.error == "credential_rejected"
    assert not (tmp_path / "asst" / "MEMORY.md").exists()


def test_f7_terminal_gate_forbids_invention() -> None:
    text = (
        MemoryRetrievalSection()
        .render(
            role_profile=_role(),
            task="",
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )
    assert "绝不编造" in text


def test_f8_privacy_firewall_renders_for_a_bound_home() -> None:
    text = (
        PrivacyFirewallSection()
        .render(
            role_profile=_role(),
            task="",
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )
    assert "检索到不等于可透露" in text
    assert "side-chats/<id>/MEMORY.md" in text


def test_f9_standing_snapshot_carries_the_parent_rule(tmp_path: Path) -> None:
    rule = "严禁未经基准测试擅自引入依赖"
    files = [
        ("SOUL.md", "我是助手。"),
        ("USER.md", "用户是架构师。"),
        ("MEMORY.md", "用户住在杭州。"),
        ("AGENTS.md", rule),
        ("TOOLS.md", "用 bash 执行。"),
    ]
    snapshot = assemble_standing(files, budget_chars=10_000)
    for name, _body in files:
        assert f"<!-- INJECTED FILE: {name} -->" in snapshot
    assert rule in snapshot


def test_f10_watcher_fault_leaves_assembly_intact(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    (home / "SOUL.md").write_text("人设\n", encoding="utf-8")
    watcher = FaultInjectingWatcher(home, interval_s=0.05)
    watcher.start()
    try:
        time.sleep(0.2)
        assert watcher.consume() == ""
        system = _assemble(home)
    finally:
        watcher.stop()
    assert "你是 LobeHub 助手。" in system


def test_f11_trail_overwrite_is_refused(tmp_path: Path) -> None:
    writer = TrailWriter(DiskFileStore(tmp_path))
    writer.append("2026-09-30", "原始流水")
    with pytest.raises(NarrowGateViolationError):
        writer.overwrite("2026-09-30", "篡改")
    text = (tmp_path / "memory" / "2026-09-30.md").read_text(encoding="utf-8")
    assert "原始流水" in text
    assert "篡改" not in text


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
    def __init__(self) -> None:
        self._header = _Header(system=None)

    def derive_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": "写一个快速排序"}]

    def request_header(self) -> _Header:
        return self._header


def _assemble(home: Path) -> str:
    out = asyncio.run(
        HistoryDeriveExecutor().node_execute(
            context=NodeContext(runtime={"home_path": str(home)}, budget={}, metadata={}),
            input=NodeInput(
                port_values={
                    "state": AgentState(trace_id="trace-matrix", task="", budget=Budget()),
                    "writer": _Writer(),
                    "turn_render": _Render(trace=_Trace(system_prompt_text="你是 LobeHub 助手。")),
                }
            ),
        )
    )
    return out.port_values["model_visible_request"].system
