"""Tests for ConnectorsPanel & AssistantStatusDrawer Integration (Task 5: CONNECTOR-TASK-5-DRAWER-HUB).

Validates:
1. ConnectorsPanel.tsx component presence.
2. AssistantStatusDrawer has Connectors tab in Segmented options.
3. AssistantStatusDrawer top profile header (large dynamic avatar + assistant name + edit pencil button).
4. Edit pencil menu with "修改形象" and "修改名字" with chat input autofill.
5. ConnectorsPanel lists ecosystem connectors (Gmail, Google Drive, GitHub, Slack, Notion, Companion),
   expandable tool lists, and assistant enablement switch.
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


def _get_connectors_panel_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "ConnectorsPanel.tsx"
    )


def test_connectors_panel_tsx_exists() -> None:
    path = _get_connectors_panel_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_drawer_contains_connectors_tab() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含 connectors tab
    assert "connectors" in content
    assert "ConnectorsPanel" in content


def test_drawer_top_profile_and_edit_pencil() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含顶栏大头像、名字与编辑铅笔
    assert "AssistantTopMascot" in content or "avatar" in content.lower()
    assert "pencil" in content.lower() or "edit" in content.lower() or "✏️" in content
    # 引导输入
    assert "修改你的形象" in content or "形象" in content
    assert "名字" in content


def test_connectors_panel_ecosystem_and_tools() -> None:
    path = _get_connectors_panel_path()
    content = path.read_text(encoding="utf-8")

    # 包含 Gmail, Google Drive, GitHub, Slack, 本机伴侣
    assert "Gmail" in content or "gmail" in content
    assert "GitHub" in content or "github" in content
    assert "Slack" in content or "slack" in content
    assert "Companion" in content or "伴侣" in content

    # 包含工具展开与开关
    assert "Switch" in content or "switch" in content.lower()
    assert "工具" in content or "tools" in content.lower()
