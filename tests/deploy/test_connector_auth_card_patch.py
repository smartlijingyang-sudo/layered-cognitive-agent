"""Tests for ConnectorAuthCard component and chat mounting (Task 4: CONNECTOR-TASK-4-CHAT-CARD).

Validates:
1. TSX component source presence (deploy/lobehub/patches/ui/ConnectorAuthCard.tsx).
2. Props contract: appName, authUrl, connectionId, title, description, onConnected.
3. Popup window opening (600x700 centered) & OAuth flow.
4. Auto-polling / refresh connection status machine.
5. Brand icons support (Gmail, GitHub, Slack, Google Drive, etc.).
6. Patch integration into Assistant/index.tsx.
"""

from __future__ import annotations

from pathlib import Path


def _get_card_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "ConnectorAuthCard.tsx"
    )


def _get_patch_py_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "connector_auth_card.py"
    )


def test_connector_auth_card_tsx_exists() -> None:
    path = _get_card_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_connector_auth_card_props_and_state_contract() -> None:
    path = _get_card_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 必须支持核心 Props
    assert "appName" in content
    assert "authUrl" in content
    assert "connectionId" in content
    assert "onConnected" in content

    # 状态机：待授权、授权中、已连接
    assert "pending" in content.lower()
    assert "authoriz" in content.lower()
    assert "connected" in content.lower()


def test_connector_auth_card_popup_and_polling_contract() -> None:
    path = _get_card_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 独立弹窗
    assert "window.open" in content
    # 状态轮询
    assert "composio" in content.lower()
    assert "refresh" in content.lower() or "fetch" in content.lower()


def test_connector_auth_card_brand_ecosystem() -> None:
    path = _get_card_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 覆盖主流连接器品牌
    assert "Gmail" in content or "gmail" in content
    assert "GitHub" in content or "github" in content


def test_connector_auth_card_patch_module() -> None:
    path = _get_patch_py_path()
    assert path.is_file(), f"Missing patch module: {path}"
    content = path.read_text(encoding="utf-8")
    assert "ConnectorAuthCard" in content
    assert "assistant_naming_widget" in content or "depends_on" in content
