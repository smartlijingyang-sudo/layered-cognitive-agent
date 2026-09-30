"""Scenario coverage for the curated memory projection.

The record store stays ``memory/semantic.json``. These tests walk the
observable flow: commit, project, supersede, reject a credential, fail a
disk write, refuse an unreceipted acknowledgement, re-read standing files
after compaction, and stamp the graph-node receipt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.cognition.memory.acknowledgement import guard_memory_claim
from lca.contracts.atoms.enums.enums import (
    ContentType,
    MemoryCategory,
    MemoryLayer,
    ReflectionVerdict,
)
from lca.contracts.models.cognition.boundary import MemoryReceipt
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.framework.graph.host_wiring import make_node_runtime_view_factory
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.domain.curated import (
    CuratedClaim,
    may_acknowledge_projection,
    render_curated_markdown,
)
from lca.infrastructure.memory.contextfiles.domain.standing import rehydrate_after_compaction
from lca.nodes.concept.memory_write.dispatch import MemoryWriteDispatchExecutor
from lca.nodes.think.decision.parse import DecisionParseExecutor
from lca.plugins.assistant.persona.persona import persona_from_home


def _record(
    *,
    record_id: str,
    content: str,
    category: MemoryCategory = MemoryCategory.FACT,
    importance: float = 0.5,
    source: str = "user",
    trigger: str = "用户要求记下",
    created_at_ms: int = 1_750_000_000_000,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=importance,
        category=category,
        dedupe_key=record_id,
        source_trace_id="trace-1",
        created_at_ms=created_at_ms,
        metadata={"source": source, "trigger": trigger},
    )


def _claim(
    *,
    claim_id: str,
    body: str,
    kind: str = "fact",
    importance: float = 0.5,
    source: str = "user",
    trigger: str = "用户要求记下",
    recorded_on: str = "2025-06-15",
) -> CuratedClaim:
    return CuratedClaim(
        claim_id=claim_id,
        kind=kind,
        body=body,
        importance=importance,
        source=source,
        trigger=trigger,
        recorded_on=recorded_on,
    )


def test_projection_renders_fact_provenance_and_skips_identity() -> None:
    text = render_curated_markdown(
        [
            _claim(claim_id="fact-1", body="用户住在上海"),
            _claim(claim_id="id-1", body="用户是架构师", kind="identity"),
            _claim(claim_id="pref-1", body="回答要短", kind="preference"),
        ]
    )
    assert "## Facts" in text
    assert "用户住在上海" in text
    assert "This came from user when 用户要求记下, recorded 2025-06-15." in text
    assert "## Preferences" in text
    assert "回答要短" in text
    assert "架构师" not in text
    assert "下次写入会重写本文件" in text


def test_projection_drops_lower_importance_when_budget_is_tight() -> None:
    claims = [
        _claim(claim_id="a", body="甲" * 80, importance=0.9),
        _claim(claim_id="b", body="乙" * 80, importance=0.1),
    ]
    text = render_curated_markdown(claims, char_budget=280)
    assert "甲" in text
    assert "乙" not in text


def test_commit_rewrites_projection_and_supersede_keeps_one_active_fact(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(_record(record_id="city-1", content="用户住在上海"))
    first = (memory.home_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "用户住在上海" in first
    assert "记录在 `memory/semantic.json`。" in first
    assert memory.last_curated_receipt is not None
    assert memory.last_curated_receipt.ok is True
    assert memory.last_curated_receipt.record_ids == ("city-1",)

    memory.upsert(_record(record_id="city-1", content="用户住在杭州"))
    second = (memory.home_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "用户住在杭州" in second
    assert "用户住在上海" not in second
    stored = memory.query(MemoryLayer.SEMANTIC)
    assert [row.content for row in stored] == ["用户住在杭州"]


def test_same_active_rows_render_the_same_markdown() -> None:
    rows = [_claim(claim_id="fact-1", body="用户住在上海")]
    assert render_curated_markdown(rows) == render_curated_markdown(list(rows))


def test_credential_shaped_content_is_not_stored(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(_record(record_id="secret", content="password: hunter2"))
    assert memory.last_curated_receipt is not None
    assert memory.last_curated_receipt.ok is False
    assert memory.last_curated_receipt.error == "credential_rejected"
    assert not (memory.home_path / "memory" / "semantic.json").exists()
    assert not (memory.home_path / "MEMORY.md").exists()
    assert may_acknowledge_projection(memory.last_curated_receipt) is False


def test_projection_write_failure_keeps_the_record_and_blocks_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = AssistantMemory(tmp_path / "asst")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("lca.infrastructure.memory.contextfiles.adapters.disk.os.replace", _boom)
    memory.upsert(_record(record_id="city-1", content="用户住在上海"))
    assert memory.last_curated_receipt is not None
    assert memory.last_curated_receipt.ok is False
    assert "disk full" in memory.last_curated_receipt.error
    assert (memory.home_path / "memory" / "semantic.json").is_file()
    assert may_acknowledge_projection(memory.last_curated_receipt) is False


def test_claim_guard_refuses_without_receipt_and_passes_with_one() -> None:
    assert (
        guard_memory_claim("好的，已记下。", allowed=False)
        == "这条还没有写入记忆文件。我不能说已经记下。"
    )
    assert guard_memory_claim("好的，已记下。", allowed=True) == "好的，已记下。"
    assert guard_memory_claim("今天上海有雨。", allowed=False) == "今天上海有雨。"


def test_compaction_rehydration_uses_fresh_standing_files_and_drops_old_history() -> None:
    history = (
        "很早的对话"
        + ("旧" * 2000)
        + "\n<!-- INJECTED FILE: MEMORY.md -->\n旧事实\n<!-- END INJECTED FILE: MEMORY.md -->\n"
        + "刚刚的问题"
    )
    files = (
        ("SOUL.md", "人设保持短句"),
        ("USER.md", ""),
        ("MEMORY.md", "用户住在杭州"),
        ("AGENTS.md", "手册" * 4000),
        ("TOOLS.md", ""),
    )
    text = rehydrate_after_compaction(history, files, budget_chars=700)
    assert "用户住在杭州" in text
    assert "旧事实" not in text
    assert "刚刚的问题" in text
    assert "很早的对话" not in text
    assert "<!-- INJECTED FILE: MEMORY.md -->" in text
    assert "<!-- INJECTED FILE: SOUL.md -->" in text


def test_persona_rereads_memory_even_when_agents_is_huge(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    (home / "profile.json").write_text(
        '{"name": "小研", "description": "深度研究"}',
        encoding="utf-8",
    )
    (home / "SOUL.md").write_text("人设正文", encoding="utf-8")
    (home / "USER.md").write_text("称呼小超", encoding="utf-8")
    (home / "MEMORY.md").write_text("用户住在杭州", encoding="utf-8")
    (home / "AGENTS.md").write_text("手册" * 5000, encoding="utf-8")
    persona = persona_from_home(str(home))
    assert "用户住在杭州" in persona.backstory
    assert "人设正文" in persona.backstory
    assert len(persona.backstory) <= 3000


@pytest.mark.asyncio
async def test_dispatch_stamps_acknowledgement_only_after_projection(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    state = AgentState(trace_id="trace-9", task="记住城市", budget=Budget())
    observation = Observation(
        observation_id="obs-1", success=True, payload={}, content_type=ContentType.TEXT
    )
    reflection = Reflection(
        reflection_id="ref-1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={
            "memory_candidates": [
                {
                    "content": "用户住在杭州",
                    "category": "fact",
                    "confidence": 0.95,
                    "source": "user",
                    "dedupe_key": "home.city",
                    "trigger": "用户说以后按这个来",
                }
            ]
        },
    )
    executor = MemoryWriteDispatchExecutor()
    output = await executor.node_execute(
        NodeContext(runtime={}, budget={}, metadata={}),
        NodeInput(
            {
                "memory_receipt": MemoryReceipt(admitted=True, reflection_id="ref-1"),
                "observation": observation,
                "reflection": reflection,
                "state": state,
                "memory": memory,
            }
        ),
    )
    stamped = output.port_values["memory_receipt"]
    assert stamped.may_acknowledge is True
    assert stamped.projection_bytes > 0
    projected = (memory.home_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "用户住在杭州" in projected
    assert "when 用户说以后按这个来" in projected
    assert guard_memory_claim("已记下。", allowed=stamped.may_acknowledge) == "已记下。"


@pytest.mark.asyncio
async def test_memory_claim_flow_write_receipt_reaches_decision(tmp_path: Path) -> None:
    """一条完整流程：写盘结果经运行时视图决定最终回复。"""
    memory = AssistantMemory(tmp_path / "asst")
    view = make_node_runtime_view_factory(
        base_scope={"memory": memory},
        effect_gateway=None,
    )(None)
    state = AgentState(trace_id="trace-flow", task="记住城市", budget=Budget())
    observation = Observation(
        observation_id="obs-1", success=True, payload={}, content_type=ContentType.TEXT
    )

    def _candidate(content: str, key: str) -> Reflection:
        return Reflection(
            reflection_id=f"ref-{key}",
            verdict=ReflectionVerdict.ON_TRACK,
            extra={
                "memory_candidates": [
                    {
                        "content": content,
                        "category": "fact",
                        "confidence": 0.95,
                        "source": "user",
                        "dedupe_key": key,
                        "trigger": "用户说以后按这个来",
                    }
                ]
            },
        )

    async def _dispatch(reflection: Reflection) -> MemoryReceipt:
        output = await MemoryWriteDispatchExecutor().node_execute(
            NodeContext(runtime=view, budget={}, metadata={}),
            NodeInput(
                {
                    "memory_receipt": MemoryReceipt(
                        admitted=True,
                        reflection_id=reflection.reflection_id,
                    ),
                    "observation": observation,
                    "reflection": reflection,
                    "state": state,
                    "memory": memory,
                }
            ),
        )
        return output.port_values["memory_receipt"]

    # 场景 A：合法写盘成功，回执允许认领，最终回复保留「已记下」。
    ok_receipt = await _dispatch(_candidate("用户住在杭州", "home.city"))
    assert ok_receipt.may_acknowledge is True
    decision_ok = await _parse_decision("好的，已记下。", may_acknowledge=None, memory=memory)
    assert decision_ok.response_text == "好的，已记下。"

    # 场景 B：凭证被拒，回执不允许认领，最终回复被替换为未写入说明。
    bad_receipt = await _dispatch(_candidate("password: hunter2", "secret"))
    assert bad_receipt.may_acknowledge is False
    decision_bad = await _parse_decision("好的，已记下。", may_acknowledge=None, memory=memory)
    assert decision_bad.response_text == "这条还没有写入记忆文件。我不能说已经记下。"


async def _parse_decision(
    text: str,
    *,
    may_acknowledge: bool | None,
    memory: AssistantMemory | None = None,
) -> Decision:
    if memory is None:
        if may_acknowledge is None:
            runtime: dict[str, object] = {}
        else:
            runtime = {
                "memory_receipt": MemoryReceipt(
                    admitted=True,
                    may_acknowledge=may_acknowledge,
                )
            }
    else:
        runtime = make_node_runtime_view_factory(
            base_scope={"memory": memory},
            effect_gateway=None,
        )(None)
    response = LLMResponse(text=text, tool_calls=(), model="test-model", finish_reason="stop")
    output = await DecisionParseExecutor().node_execute(
        NodeContext(runtime=runtime, budget={}, metadata={}),
        NodeInput(port_values={"state": runtime, "llm_response": response}),
    )
    decision = output.port_values["decision"]
    assert isinstance(decision, Decision)
    return decision


@pytest.mark.asyncio
async def test_decision_parse_drops_remembered_claim_without_receipt() -> None:
    decision = await _parse_decision("好的，已记下。", may_acknowledge=False)
    assert decision.response_text == "这条还没有写入记忆文件。我不能说已经记下。"


@pytest.mark.asyncio
async def test_decision_parse_keeps_remembered_claim_with_receipt() -> None:
    decision = await _parse_decision("好的，已记下。", may_acknowledge=True)
    assert decision.response_text == "好的，已记下。"


@pytest.mark.asyncio
async def test_decision_parse_without_memory_receipt_keeps_original_text() -> None:
    decision = await _parse_decision("好的，已记下。", may_acknowledge=None)
    assert decision.response_text == "好的，已记下。"


def test_runtime_view_exposes_memory_receipt_from_memory_seam(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    view = make_node_runtime_view_factory(
        base_scope={"memory": memory},
        effect_gateway=None,
    )(None)
    assert view.get("memory_receipt") is None
    memory.upsert(_record(record_id="city-1", content="用户住在上海"))
    receipt = view.get("memory_receipt")
    assert receipt is not None
    assert receipt.ok is True
    assert receipt.record_ids == ("city-1",)


@pytest.mark.asyncio
async def test_decision_parse_uses_live_memory_receipt(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    decision = await _parse_decision("好的，已记下。", may_acknowledge=None, memory=memory)
    assert decision.response_text == "好的，已记下。"

    memory.upsert(_record(record_id="city-1", content="用户住在上海"))
    decision = await _parse_decision("好的，已记下。", may_acknowledge=None, memory=memory)
    assert decision.response_text == "好的，已记下。"

    memory.upsert(_record(record_id="secret", content="password: hunter2"))
    decision = await _parse_decision("好的，已记下。", may_acknowledge=None, memory=memory)
    assert decision.response_text == "这条还没有写入记忆文件。我不能说已经记下。"
