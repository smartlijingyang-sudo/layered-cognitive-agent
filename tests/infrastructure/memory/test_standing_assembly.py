"""Tests for the standing-file assembly module.

Covers ``assemble_standing``, ``render_injected``, ``rehydrate_after_compaction``
and the packaged layout order. The module lives in infrastructure so both
the memory refresh loader and the persona plugin depend on it without an upward
``infrastructure -> cognition`` import.
"""

from __future__ import annotations

import importlib
from pathlib import Path

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


def test_url_iron_rule_reaches_model_via_platform_tier(tmp_path: Path) -> None:
    """正向契约（2026-10-04 修订）：URL 铁律现居 Tier-1 PLATFORM.md。

    5098195a0 把 4 行铁律（URL 铁律 + 动态授权 + 照单全信 + token 外发）从
    CONSTITUTION.md 模板移出；platform 文件由部署落盘到 get_lca_home()/
    PLATFORM.md，不在 repo 内——旧 pin（断言模板含铁律且组装后在场）的前提已死，
    改钉机制：platform_root 传入的 PLATFORM.md 经 refresh_standing_backstory
    整段注入、零截断。

    部署漂移风险（新机器无 PLATFORM.md 则铁律缺席，repo 内无模板可回放）见
    backlog P1 todo-41；内容归属是部署侧，本测试只钉"整段必达"机制。
    """
    from lca.infrastructure.memory.contextfiles.service.assembly import (
        refresh_standing_backstory,
    )

    platform_root = tmp_path / "lca_home"
    platform_root.mkdir()
    (platform_root / "PLATFORM.md").write_text(
        "## 平台铁律\n"
        "- **URL 铁律**：发给用户的每个 URL 必须来自工具返回或用户原文；"
        "严禁凭记忆或参数知识拼装 URL。\n"
        "- 动态授权与第三方连接严禁在文本中拼装 URL，"
        "所有连接与授权必须调用官方工具生成。\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    out = refresh_standing_backstory(str(home), "", platform_root=platform_root)
    # 整段注入：两条铁律行都完整在场（无 mid-section 截断）
    assert "URL 铁律" in out
    assert "严禁凭记忆或参数知识拼装 URL" in out
    assert "严禁在文本中拼装 URL" in out
