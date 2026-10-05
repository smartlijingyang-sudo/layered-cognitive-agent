"""在线流水写入方。

trail 是原始交互证据，因此不受 ``govern()`` 闭合模板门控，模板不命中的话轮
照样落盘，由 ``run_dream`` 决定它值不值得提升。凭证在写入前拒绝（ADR-0260
C3-3），私人信息不在写入侧过滤，读侧由 ``memory_search`` 负责。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.cognition.memory.daytime import record_turn_trail
from lca.contracts.models.core.state.state import AgentState, Budget

_NOW_MS = 1_759_200_000_000
_TRAIL_DATE = "2025-09-30"


def _runtime(home: Path | None) -> dict[str, object]:
    runtime: dict[str, object] = {}
    if home is not None:
        runtime["assistant_home_path"] = str(home)
    return runtime


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_trail", task=task, budget=Budget())


def _trail(home: Path, date: str = _TRAIL_DATE) -> str:
    path = home / "memory" / f"{date}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def test_utterance_no_template_matches_still_lands(tmp_path: Path) -> None:
    """条件二的核心：判据句在 govern() 返回 None，流水仍然写。"""
    home = tmp_path / "asst"

    assert record_turn_trail(_runtime(home), _state("还是简洁一点好"), now_ms=_NOW_MS) is True
    assert "还是简洁一点好" in _trail(home)


def test_date_comes_from_the_injected_clock(tmp_path: Path) -> None:
    """C8 确定性：日期由 now_ms 派生，不读墙钟。"""
    home = tmp_path / "asst"

    record_turn_trail(_runtime(home), _state("今天聊点别的"), now_ms=_NOW_MS)

    assert (home / "memory" / f"{_TRAIL_DATE}.md").is_file()


def test_two_turns_append_rather_than_overwrite(tmp_path: Path) -> None:
    home = tmp_path / "asst"

    record_turn_trail(_runtime(home), _state("第一句"), now_ms=_NOW_MS)
    record_turn_trail(_runtime(home), _state("第二句"), now_ms=_NOW_MS)

    text = _trail(home)
    assert "第一句" in text
    assert "第二句" in text


def test_credential_bearing_utterance_is_refused(tmp_path: Path) -> None:
    """ADR-0260 C3-3 凭证红线在写入侧，不落盘也不进索引。"""
    home = tmp_path / "asst"

    assert (
        record_turn_trail(_runtime(home), _state("我的密码: hunter2abc"), now_ms=_NOW_MS) is False
    )
    assert "hunter2abc" not in _trail(home)


def test_private_personal_material_is_written(tmp_path: Path) -> None:
    """写入侧只挡凭证。私人信息的过滤属读侧，见 memory_search 的测试。"""
    home = tmp_path / "asst"

    assert record_turn_trail(_runtime(home), _state("我的手机号是 13800138000"), now_ms=_NOW_MS)
    assert "13800138000" in _trail(home)


def test_overlong_utterance_is_truncated(tmp_path: Path) -> None:
    home = tmp_path / "asst"

    record_turn_trail(_runtime(home), _state("很长" * 400), now_ms=_NOW_MS)

    lines = [line for line in _trail(home).splitlines() if line.startswith("- ")]
    assert len(lines) == 1
    assert len(lines[0]) <= 210


def test_missing_home_returns_false(tmp_path: Path) -> None:
    assert record_turn_trail(_runtime(None), _state("还是简洁一点好"), now_ms=_NOW_MS) is False


def test_empty_utterance_returns_false(tmp_path: Path) -> None:
    home = tmp_path / "asst"

    assert record_turn_trail(_runtime(home), _state("   "), now_ms=_NOW_MS) is False
    assert not (home / "memory").exists() or list((home / "memory").glob("20*.md")) == []


def test_missing_state_returns_false(tmp_path: Path) -> None:
    assert record_turn_trail(_runtime(tmp_path / "asst"), None, now_ms=_NOW_MS) is False


@pytest.mark.parametrize("task", ["还是简洁一点好", "别那么啰嗦", "回复请简短"])
def test_criterion_sentences_all_land(tmp_path: Path, task: str) -> None:
    """Phase 0 条件二的三条判据句都不含记忆动词，govern() 全部返回 None。"""
    home = tmp_path / "asst"

    assert record_turn_trail(_runtime(home), _state(task), now_ms=_NOW_MS) is True
    assert task in _trail(home)
