"""Tests for the WeChat channel service rename and path helper.

``WechatChannelManager`` was renamed to ``WechatChannelService`` (module
``service.py``) to satisfy AGENTS.md naming discipline; the config-path
algebra is a pure helper that the service delegates to.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.channels.wechat.service import (
    WechatChannelService,
    channel_config_path,
)


def test_channel_config_path_shape() -> None:
    path = channel_config_path(Path("/home/x"), "asst_1")
    assert path == Path("/home/x/assistants/asst_1/channels/wechat.json")


def test_channel_config_path_is_deterministic(tmp_path: Path) -> None:
    base = tmp_path / "wechat-base"
    assert channel_config_path(base, "a") == channel_config_path(base, "a")
    assert channel_config_path(base, "a") != channel_config_path(base, "b")


def test_service_get_config_path_delegates_to_helper(tmp_path: Path) -> None:
    service = WechatChannelService(base_dir=tmp_path)
    assert service._get_config_path("asst_x") == channel_config_path(tmp_path, "asst_x")


def test_service_importable_from_package() -> None:
    from lca.infrastructure.channels.wechat import WechatChannelService as PkgService

    assert PkgService is WechatChannelService


def test_manager_module_no_longer_exists() -> None:
    repo = Path(__file__).resolve().parents[2]
    assert not (repo / "lca" / "infrastructure" / "channels" / "wechat" / "manager.py").exists()
    assert (repo / "lca" / "infrastructure" / "channels" / "wechat" / "service.py").exists()
