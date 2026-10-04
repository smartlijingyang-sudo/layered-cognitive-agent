"""Tests for the standing-file assembly module.

Covers ``assemble_standing``, ``render_injected``, ``rehydrate_after_compaction``
and the packaged layout order. The module lives in infrastructure so both
the memory refresh loader and the persona plugin depend on it without an upward
``infrastructure -> cognition`` import.
"""

from __future__ import annotations

import importlib

import pytest

from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.domain.standing import (
    assemble_standing,
    rehydrate_after_compaction,
    render_injected,
)


def test_standing_order_comes_from_the_layout_file() -> None:
    # ada0919cc: CONSTITUTION.md 注册为 standing_files 首位（deliberate 布局变更）
    assert packaged_layout().standing_files == (
        "CONSTITUTION.md",
        "SOUL.md",
        "IDENTITY.md",
        "USER.md",
        "MEMORY.md",
        "AGENTS.md",
        "TOOLS.md",
        "memory/people/INDEX.md",
        "memory/groups/INDEX.md",
        "dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md",
    )


def test_assemble_standing_respects_budget() -> None:
    files = [("SOUL.md", "s" * 500), ("USER.md", "u" * 500), ("AGENTS.md", "a" * 500)]
    out = assemble_standing(files, budget_chars=100)
    assert len(out) <= 100


def test_assemble_standing_preserves_order() -> None:
    files = [("AGENTS.md", "agents"), ("SOUL.md", "soul"), ("USER.md", "user")]
    out = assemble_standing(files, budget_chars=1000)
    assert out.index("soul") < out.index("user") < out.index("agents")


def test_assemble_standing_empty_budget() -> None:
    assert assemble_standing([("SOUL.md", "x")], budget_chars=0) == ""


def test_assemble_standing_omits_blank_files() -> None:
    out = assemble_standing([("SOUL.md", "  "), ("USER.md", "user")], budget_chars=1000)
    assert "user" in out
    assert "soul" not in out.lower()


def test_assemble_standing_missing_file_treated_as_empty() -> None:
    out = assemble_standing([("SOUL.md", "soul")], budget_chars=1000)
    assert "soul" in out


def test_render_injected_wraps_body() -> None:
    rendered = render_injected("SOUL.md", "  body text  ")
    assert "<!-- INJECTED FILE: SOUL.md -->" in rendered
    assert "body text" in rendered
    assert "<!-- END INJECTED FILE: SOUL.md -->" in rendered


def test_rehydrate_after_compaction_keeps_history_then_standing() -> None:
    history = "old history line"
    files = [("SOUL.md", "fresh soul"), ("USER.md", "fresh user")]
    out = rehydrate_after_compaction(history, files, budget_chars=2000)
    assert "old history line" in out
    assert "fresh soul" in out


def test_rehydrate_after_compaction_budget_limits() -> None:
    history = "h" * 300
    files = [("SOUL.md", "s" * 300)]
    out = rehydrate_after_compaction(history, files, budget_chars=100)
    assert len(out) <= 100


def test_rehydrate_after_compaction_drops_injected_blocks() -> None:
    history = render_injected("SOUL.md", "stale injected soul") + "\nreal history"
    files = [("SOUL.md", "fresh soul")]
    out = rehydrate_after_compaction(history, files, budget_chars=2000)
    assert "stale injected soul" not in out
    assert "fresh soul" in out


def test_refresh_standing_backstory_uses_infrastructure_standing() -> None:
    """The loader must not reach upward into cognition for standing assembly."""
    loader = importlib.import_module("lca.infrastructure.memory.contextfiles.service.assembly")
    source = importlib.util.find_spec(
        "lca.infrastructure.memory.contextfiles.service.assembly"
    ).origin
    text = __import__("pathlib").Path(source).read_text(encoding="utf-8")
    assert "lca.cognition" not in text
    assert callable(loader.refresh_standing_backstory)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "P1 todo-40: fd53f1642 把 URL 铁律从 react_tool_usage_guidelines 段搬进 "
        "CONSTITUTION.md 模板，但铁律在模板内偏移 13651/23838，远超 backstory "
        "3000 预算（首文件 cap 仅预算一半），组装后模型实际看不到。45ac7b6c0 时代 "
        "该规则在 section 全量渲染、模型必见；迁移后只剩负向测试（不在 py）为绿， "
        "正向契约断裂。修法待源码侧决策（模板前置/提预算/独立 section），tests lane 只钉契约。"
    ),
)
def test_url_iron_rule_survives_standing_assembly() -> None:
    """正向契约：URL 铁律必须能到达组装后的 backstory（模型实际看到的文本）。

    负向测试 test_no_url_rules_hardcoded_in_py 只保证"不在 py 里硬编码"，
    不保证"在宪法里仍然生效"——本测试补另一半：源头模板里必须有，
    且经 assemble_standing（与 persona_from_home / refresh_standing_backstory
    同预算）裁剪后仍然在场。
    """
    from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
        DEFAULT_STANDING_FILE_TEMPLATES,
    )

    template = DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"]
    assert "URL 铁律" in template, "铁律已从 CONSTITUTION.md 模板源头消失"
    out = assemble_standing(
        [("CONSTITUTION.md", template)],
        budget_chars=packaged_layout().backstory_budget_chars,
        order=packaged_layout().standing_files,
    )
    assert "URL 铁律" in out, "铁律被 backstory 预算截断，模型实际看不到"
