"""流水里的风格偏好按维度归一，同一维度的不同措辞只产一条语义记录。

`_trail_episode` 原先用内容摘要作 `preference:` 键，两种措辞永不聚到同一个
cluster，各自提升为一条独立语义记录。本文件在 `run_dream` 这个真实入口上钉住
归一后的行为，并钉住一条容易误信的反面事实：稳定维度键**不**带来复现保护，
`_lifecycle` 的 `authority` 分支先于 `recurrence` 短路。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.cli.commands.ops.memory import _dream_callbacks
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.dream import run_dream

_NOW_MS = 1_759_200_000_000


def _home_with_trail(tmp_path: Path, *lines: str) -> Path:
    home = tmp_path / "asst"
    for sub in ("people", "groups", "episodes"):
        (home / "memory" / sub).mkdir(parents=True)
    body = "".join(f"- {line}\n" for line in lines)
    (home / "memory" / "2026-10-04.md").write_text(f"# 2026-10-04\n\n{body}", encoding="utf-8")
    return home


def _dream(home: Path) -> None:
    render, backfill = _dream_callbacks(home)
    run_dream(home, now_ms=_NOW_MS, backfill=backfill, render=render)


def _active(home: Path) -> list[MemoryRecord]:
    return AssistantMemory(home).query(MemoryLayer.SEMANTIC)


def test_two_phrasings_of_one_style_preference_become_one_record(tmp_path: Path) -> None:
    home = _home_with_trail(tmp_path, "以后回复简洁一点", "回复要简洁")

    _dream(home)

    records = _active(home)
    verbosity = [r for r in records if r.dedupe_key == "preference:verbosity"]
    assert len(verbosity) == 1
    assert len(records) == 1


def test_style_preference_uses_the_shared_dimension_key(tmp_path: Path) -> None:
    home = _home_with_trail(tmp_path, "以后回复简洁一点")

    _dream(home)

    records = _active(home)
    assert [r.dedupe_key for r in records] == ["preference:verbosity"]
    assert records[0].category is MemoryCategory.PREFERENCE


def test_non_style_preference_keeps_the_content_digest_key(tmp_path: Path) -> None:
    """非风格类偏好没有维度可映射，保留摘要键，不被归一波及。

    授权收窄之后它首次不再提升，要跨天复现。完整的授权矩阵见
    ``test_trail_authority_narrowing.py``。
    """
    home = tmp_path / "asst"
    for sub in ("people", "groups", "episodes"):
        (home / "memory" / sub).mkdir(parents=True)
    for date in ("2026-10-04", "2026-10-05"):
        (home / "memory" / f"{date}.md").write_text(
            f"# {date}\n\n- 以后不要用 emoji\n", encoding="utf-8"
        )

    _dream(home)

    records = _active(home)
    assert len(records) == 1
    key = records[0].dedupe_key
    assert key is not None
    assert key.startswith("preference:")
    assert key != "preference:verbosity"


def test_non_preference_trail_line_is_not_promoted(tmp_path: Path) -> None:
    home = _home_with_trail(tmp_path, "李雷说项目下周发布")

    _dream(home)

    assert _active(home) == []


def test_stable_key_does_not_add_recurrence_protection(tmp_path: Path) -> None:
    """显式指令加稳定维度的行仍然首次即提升。

    `_lifecycle` 先判 `explicit_user_authority`，命中即 `consolidated_slow`，
    走不到 `recurrence >= 2`。授权在 Task 5 收窄到「显式且能映射维度」这一格，
    本条数据正落在该格，所以维度归一在这里既不提供也不需要复现保护。
    """
    home = _home_with_trail(tmp_path, "以后回复简洁一点")

    _dream(home)

    assert len(_active(home)) == 1


def test_second_dream_pass_adds_nothing(tmp_path: Path) -> None:
    """归一后 `_already_active` 的 NOOP 对风格偏好生效。"""
    home = _home_with_trail(tmp_path, "以后回复简洁一点", "回复要简洁")

    _dream(home)
    first = _active(home)
    _dream(home)
    second = _active(home)

    assert len(first) == 1
    assert len(second) == 1
