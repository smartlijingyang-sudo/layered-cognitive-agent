"""收窄后的授权矩阵：只有既是显式指令又落到稳定维度的行才首次即提升。

`_lifecycle` 的 authority 分支先于 recurrence 短路，所以授权就等于永久提升且
不再被审视。收窄之前任何 `is_preference_statement` 命中都拿授权，而捕获面一旦
为 Phase 0 条件二放宽，「这段代码很简洁」这类提到风格词的句子就会永久写进
`preference:verbosity`。矩阵按显式与维度两个轴分四格。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.infrastructure.cli.commands.ops.memory import _dream_callbacks
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.dream import run_dream

_NOW_MS = 1_759_200_000_000


def _home(tmp_path: Path, name: str, lines_by_day: dict[str, list[str]]) -> Path:
    home = tmp_path / name
    for sub in ("people", "groups", "episodes"):
        (home / "memory" / sub).mkdir(parents=True)
    for date, lines in lines_by_day.items():
        body = "".join(f"- {line}\n" for line in lines)
        (home / "memory" / f"{date}.md").write_text(f"# {date}\n\n{body}", encoding="utf-8")
    return home


def _dream(home: Path) -> None:
    render, backfill = _dream_callbacks(home)
    run_dream(home, now_ms=_NOW_MS, backfill=backfill, render=render)


def _active(home: Path) -> list:
    return AssistantMemory(home).query(MemoryLayer.SEMANTIC)


def test_explicit_style_instruction_promotes_on_first_occurrence(tmp_path: Path) -> None:
    home = _home(tmp_path, "a", {"2026-10-04": ["以后回复要简洁"]})

    _dream(home)

    records = _active(home)
    assert [r.dedupe_key for r in records] == ["preference:verbosity"]


def test_style_topic_alone_does_not_promote_on_first_occurrence(tmp_path: Path) -> None:
    """捕获面放宽后，提到风格词但没有指令标记的行不带授权。"""
    home = _home(tmp_path, "b", {"2026-10-04": ["这段代码很简洁"]})

    _dream(home)

    assert _active(home) == []


def test_criterion_sentence_promotes_only_after_it_recurs(tmp_path: Path) -> None:
    """判据句被捕获，但要跨天复现才提升。漏提升可恢复，误提升不可恢复。"""
    once = _home(tmp_path, "c1", {"2026-10-04": ["还是简洁一点好"]})
    _dream(once)
    assert _active(once) == []

    twice = _home(
        tmp_path,
        "c2",
        {"2026-10-04": ["还是简洁一点好"], "2026-10-05": ["还是简洁一点好"]},
    )
    _dream(twice)
    assert [r.dedupe_key for r in _active(twice)] == ["preference:verbosity"]


def test_explicit_non_style_preference_needs_recurrence(tmp_path: Path) -> None:
    """收窄的代价，已裁决接受：非风格的显式偏好不再首次即提升。"""
    once = _home(tmp_path, "d1", {"2026-10-04": ["以后不要用 emoji"]})
    _dream(once)
    assert _active(once) == []

    twice = _home(
        tmp_path,
        "d2",
        {"2026-10-04": ["以后不要用 emoji"], "2026-10-05": ["以后不要用 emoji"]},
    )
    _dream(twice)
    assert len(_active(twice)) == 1


def test_two_style_wordings_share_one_dimension_when_both_recur(tmp_path: Path) -> None:
    """不同措辞落进同一维度，仍然只产一条记录。"""
    home = _home(
        tmp_path,
        "e",
        {"2026-10-04": ["还是简洁一点好"], "2026-10-05": ["回复请简短"]},
    )

    _dream(home)

    records = _active(home)
    assert [r.dedupe_key for r in records] == ["preference:verbosity"]
