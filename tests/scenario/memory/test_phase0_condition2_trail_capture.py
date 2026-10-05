"""Phase 0 条件二的验收：判据句从真实 turn 走到语义记忆。

这条测试就是 note §交付门禁 Phase 0 条件二与 ADR-0287 §4 的判据本身，走
`phase.perceive.observe` 真实节点而不是手写流水文件。

日期不写死。`observe` 调 `record_turn_trail` 时不传 `now_ms`，流水文件名取自
墙钟，所以断言按 glob 找当天文件，第二天用一个保证不同的固定日期，跨午夜不会
让本测试变红。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.cli.commands.ops.memory import _dream_callbacks
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.domain.trail import is_preference_statement
from lca.infrastructure.memory.dream import run_dream
from lca.infrastructure.tools.assistant.memory_tools import MemorySearchTool
from lca.nodes.perceive.observe.observe import PerceiveObserveExecutor

_CRITERION = "还是简洁一点好"
_OTHER_DAY = "2020-01-01"
_NOW_MS = 1_759_200_000_000


class _Hub:
    async def perceive(self, state: object) -> ContextManifest:
        del state
        return ContextManifest(items=())


class _Memory:
    def __init__(self, home: Path) -> None:
        self.home_path = home


async def _turn(home: Path, task: str) -> None:
    await PerceiveObserveExecutor().node_execute(
        NodeContext(
            runtime={
                "perceive_hub": _Hub(),
                "memory": _Memory(home),
                "agent_state": AgentState(trace_id="trace_c2", task=task, budget=Budget()),
            },
            metadata={},
            budget=None,
        ),
        NodeInput(port_values={}),
    )


def _dream(home: Path) -> None:
    render, backfill = _dream_callbacks(home)
    run_dream(home, now_ms=_NOW_MS, backfill=backfill, render=render)


def _second_day(home: Path) -> str:
    """A trail date guaranteed to differ from the one the wall clock produced."""
    written = sorted((home / "memory").glob("20*.md"))
    assert len(written) == 1
    return _OTHER_DAY if written[0].stem != _OTHER_DAY else "2020-01-02"


def _write_second_day(home: Path) -> None:
    date = _second_day(home)
    (home / "memory" / f"{date}.md").write_text(f"# {date}\n\n- {_CRITERION}\n", encoding="utf-8")


def _semantic_rows(home: Path) -> tuple[int, int]:
    path = home / "memory" / "semantic.json"
    if not path.is_file():
        return (0, 0)
    rows = json.loads(path.read_text(encoding="utf-8"))
    return (len(rows), sum(1 for row in rows if row.get("deleted")))


def _rows(payload: dict | None) -> list[dict]:
    return list((payload or {}).get("records") or [])


def _is_curated(row: dict) -> bool:
    """True for a row backed by a memory record rather than a trail document."""
    return not str(row.get("record_id") or "").startswith("trail-")


@pytest.mark.asyncio
async def test_phase0_condition2_end_to_end(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)
    search = MemorySearchTool(memory=AssistantMemory(home))

    # 捕获。判据句不含记忆动词，govern() 返回 None，episode 不落盘，流水照写。
    # 这是条件二取的路线 b。
    await _turn(home, _CRITERION)

    written = sorted((home / "memory").glob("20*.md"))
    assert len(written) == 1
    assert _CRITERION in written[0].read_text(encoding="utf-8")
    assert not (home / "memory" / "episodes").exists()
    assert is_preference_statement(_CRITERION) is True

    # D6 前提。24 小时调度上界成立的条件是捕获当轮即可被 C2 的强制检索命中。
    same_turn = await search.execute({"query": "简洁", "limit": 10})
    assert same_turn.success is True
    assert any(_CRITERION in str(r.get("content") or "") for r in _rows(same_turn.payload))

    # 单次提及不提升。授权收窄到「显式指令且命中维度」，判据句只有后者。
    _dream(home)
    assert AssistantMemory(home).query(MemoryLayer.SEMANTIC) == []

    # 跨天复现才提升，且落到共享维度键。
    _write_second_day(home)
    _dream(home)

    records = AssistantMemory(home).query(MemoryLayer.SEMANTIC)
    assert [r.dedupe_key for r in records] == ["preference:verbosity"]
    assert records[0].content == _CRITERION

    # 幂等。_already_active 的 NOOP 生效，行数与退役行数都不增长。
    before = _semantic_rows(home)
    _dream(home)
    assert _semantic_rows(home) == before
    assert before == (1, 0)


@pytest.mark.asyncio
async def test_promoted_record_survives_the_full_index_rebuild(tmp_path: Path) -> None:
    """dream 重建全量索引后，提升出来的记录仍然可检索。

    按 `record_id` 前缀区分来源，不按 `category`。索引命中把 `category` 填成
    index kind（`semantic` / `trail`），实时存储命中填成记忆类目（`preference`），
    同一条记录经两个来源会给出不同的 `category`，这个字段当前不可用于判别来源。
    """
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    await _turn(home, _CRITERION)
    _write_second_day(home)
    _dream(home)

    search = MemorySearchTool(memory=AssistantMemory(home))
    observation = await search.execute({"query": "简洁", "limit": 10})

    curated = [row for row in _rows(observation.payload) if _is_curated(row)]
    assert [row.get("content") for row in curated] == [_CRITERION]


@pytest.mark.asyncio
async def test_a_trail_row_carries_one_line_not_a_whole_day(tmp_path: Path) -> None:
    """行粒度的核心：命中只带回它自己那一行，不拖进同一天的其他话轮。"""
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    await _turn(home, _CRITERION)
    await _turn(home, "帮我查一下明天天气")

    search = MemorySearchTool(memory=AssistantMemory(home))
    observation = await search.execute({"query": "简洁", "limit": 10})
    rows = _rows(observation.payload)

    assert [row.get("content") for row in rows] == [_CRITERION]
    assert not any(_is_curated(row) for row in rows)


@pytest.mark.asyncio
async def test_one_fact_returns_one_row(tmp_path: Path) -> None:
    """提升后的记录与它所来自的流水行文本相同，合并去重后只剩 curated 那条。"""
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)

    await _turn(home, _CRITERION)
    _write_second_day(home)
    _dream(home)

    search = MemorySearchTool(memory=AssistantMemory(home))
    observation = await search.execute({"query": "简洁", "limit": 10})
    rows = _rows(observation.payload)

    assert len(rows) == 1
    assert rows[0].get("content") == _CRITERION
    assert _is_curated(rows[0])
