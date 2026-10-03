"""Tests for AssistantStatusDrawer component (Task 4: Right-side status drawer).

Validates TSX component source presence, three horizontal sections
(Identity / Memory / Workspace), standing files card rendering, and
fullscreen edit trigger contracts.
"""

from __future__ import annotations

from pathlib import Path


def _get_drawer_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantStatusDrawer.tsx"
    )


def test_assistant_status_drawer_tsx_exists() -> None:
    path = _get_drawer_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_assistant_status_drawer_sections_contract() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-01: 必须提供 5 大产品化 Section 切换 (动态 / 批准 / 即将到来 / 身份 / 连接器)
    assert "activity" in content or "动态" in content
    assert "approvals" in content or "批准" in content
    assert "upcoming" in content or "即将到来" in content
    assert "identity" in content or "身份" in content
    assert "connectors" in content or "连接器" in content

    # INV-02: 身份卡片必须采用 2 列网格排布 (一行两个)
    assert "grid-template-columns: repeat(2, 1fr)" in content or "identityGrid" in content


def test_assistant_status_drawer_standing_files_contract() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-03: 必须覆盖 5 大核心 Standing Files 与点击编辑入口
    assert "IDENTITY.md" in content
    assert "SOUL.md" in content
    assert "USER.md" in content
    assert "AGENTS.md" in content
    assert "MEMORY.md" in content
    assert "onEditFile" in content
    assert "standing-files" in content


def test_assistant_status_drawer_props_and_layout() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含抽屉显隐控制与 480px 宽度规范
    assert "open" in content
    assert "onClose" in content
    assert "480" in content
    assert "AssistantStatusDrawer" in content


def test_assistant_status_drawer_no_low_level_jargon() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-04: 绝不向用户呈现底层技术用语
    assert "状态与真值中心" not in content
    assert "File as SSOT" not in content
    assert "全屏编辑资源" not in content


def test_assistant_status_drawer_editor_autofill_contract() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-05: 必须支持向 LobeHub 富文本聊天编辑器回填指令
    assert "__mainEditor" in content
    assert "setDocument" in content


def test_assistant_status_drawer_refresh_binding_no_undefined_identifiers() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # Regression: fetchStandingFiles must not be referenced as undefined identifier
    assert "fetchStandingFiles" not in content
    assert "onClick={fetchStatusSnapshot}" in content


def test_assistant_status_drawer_activity_detail_contract() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 点击单个 item 弹窗只展示当前活动/运行内部的思考与调用概要，不再展示跨 run 全局行动列表
    assert "本次思考与调用概要" in content
    assert "近期行动列表" not in content

    # 弹窗标题与内容绝不出现“人读”字样或“Agent 行动记录与人读日志”
    assert "Agent 行动记录与人读日志" not in content
    assert "人读执行概述" not in content
    assert "人读" not in content

    # 弹窗标题绑定为选中 item 的具体概要标题
    assert "selectedActivity.title" in content
    # 右侧展示具体情况的清晰文本说明
    assert "具体情况详细说明" in content


def test_drawer_list_pure_natural_language_no_tool_badge() -> None:
    """Verifies INV-03: Drawer list is pure natural language without technical badges."""
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    assert 'toolBadge: a.tool_name || a.category' not in content
    assert 'toolBadge?: string;' not in content
    assert '<Tag color="blue"' not in content
    assert '点击查看执行详情' not in content

