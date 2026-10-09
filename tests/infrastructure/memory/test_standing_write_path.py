"""Standing-file write guard tests.

``run_ab78aeb6eabf`` 中 writeFile 整文件覆盖了
``~/.lca/assistants/<id>/memory/USER.md``，没有审批事件。这是模型对
助手自己 standing 记忆文件的直接写入，会绕过 memory_add / memory_extract
的投影语义，因此 writeFile 必须拒绝这些路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.infrastructure.memory.contextfiles.domain.standing_path import (
    is_skill_package_write_path,
    is_standing_write_path,
    skill_package_write_block_message,
    standing_write_block_message,
)


def test_rejects_shadow_user_md_under_assistant_memory() -> None:
    # 真实故障路径：writeFile 写入 memory/USER.md
    assert is_standing_write_path("/home/lichao/.lca/assistants/asst_x/memory/USER.md")


def test_rejects_standing_files_under_agent_home() -> None:
    for name in ("SOUL.md", "USER.md", "MEMORY.md", "IDENTITY.md", "AGENTS.md", "TOOLS.md"):
        assert is_standing_write_path(f"/home/u/.lca/assistants/asst_x/{name}")
        assert is_standing_write_path(f"/home/u/.lca/assistants/asst_x/memory/{name}")


def test_rejects_semantic_json() -> None:
    assert is_standing_write_path("/home/u/.lca/assistants/asst_x/memory/semantic.json")


def test_allows_regular_workspace_files() -> None:
    assert not is_standing_write_path("/home/u/projects/USER.md")
    assert not is_standing_write_path("/tmp/report.md")  # noqa: S108
    assert not is_standing_write_path("/mnt/data/outputs/chart.png")


def test_allows_relative_workspace_paths() -> None:
    assert not is_standing_write_path("reports/notes.md")


def test_message_mentions_memory_add() -> None:
    msg = standing_write_block_message()
    assert "memory_add" in msg
    assert "standing" in msg
    assert "update_assistant_profile" in msg
    assert "update_assistant_soul" in msg


def test_workspace_file_with_dot_lca_segment_is_not_blocked() -> None:
    """INV-04: 工作区内的项目文件即使包含 .lca 目录段也必须放行，不被误杀。"""
    assert not is_standing_write_path("/home/lichao/my_project/.lca/USER.md")
    assert not is_standing_write_path("/home/lichao/my_project/.lca/SOUL.md")


def test_custom_lca_home_override_is_honored(tmp_path: Path, monkeypatch: Any) -> None:
    """INV-04: 当配置自定义 LCA_HOME 时，该自治目录下的 standing 文件必须严格防御。"""
    custom_home = tmp_path / "custom_agent_data"
    monkeypatch.setenv("LCA_HOME", str(custom_home))
    assert is_standing_write_path(custom_home / "assistants/asst_1/SOUL.md")
    assert is_standing_write_path(custom_home / "assistants/asst_1/memory/USER.md")
    assert is_standing_write_path(custom_home / "assistants/asst_1/memory/semantic.json")


# ── RA-057:技能包写守卫 ────────────────────────────────────────────────


def test_rejects_skill_package_files_under_home() -> None:
    # run_755719d1a9d5 的真实故障路径：writeFile 直写 {home}/skills/<id>/SKILL.md
    base = "/home/lichao/.lca/assistants/asst_c8b83acb1920/skills/psychological-counselor"
    assert is_skill_package_write_path(f"{base}/SKILL.md")
    assert is_skill_package_write_path(f"{base}/manifest.json")
    assert is_skill_package_write_path(f"{base}/resources/helper.py")
    # 包目录本身作为写入目标同样拒绝
    assert is_skill_package_write_path(base)


def test_skill_package_guard_ignores_workspace_and_out_of_scope() -> None:
    # 工作区同名文件保持可写
    assert not is_skill_package_write_path(
        "/home/lichao/.lca/assistants/asst_x/workspace/SKILL.md"
    )
    assert not is_skill_package_write_path("/home/u/projects/skills/demo/SKILL.md")
    assert not is_skill_package_write_path("skills/demo/SKILL.md")  # 相对路径无作用域
    assert not is_skill_package_write_path("/tmp/report.md")  # noqa: S108
    # skills/ 不是 home 的直接子目录（workspace 下的 skills 子目录）不误杀
    assert not is_skill_package_write_path(
        "/home/u/.lca/assistants/asst_x/workspace/skills/demo/SKILL.md"
    )


def test_skill_package_message_names_production_tools() -> None:
    msg = skill_package_write_block_message()
    assert "create_assistant_skill" in msg
    assert "edit_assistant_skill" in msg


def test_skill_package_guard_honors_lca_home_override(
    tmp_path: Path, monkeypatch: Any
) -> None:
    custom_home = tmp_path / "custom_agent_data"
    monkeypatch.setenv("LCA_HOME", str(custom_home))
    assert is_skill_package_write_path(
        custom_home / "assistants/asst_1/skills/demo/SKILL.md"
    )
    assert not is_skill_package_write_path(custom_home / "workspace/SKILL.md")
