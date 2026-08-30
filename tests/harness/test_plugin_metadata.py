"""已解析插件元数据读取 seam 的契约测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from lca.harness.profile.plugin_metadata import plugin_metadata
from lca.harness.profile.resolve import ResolvedPlugin


def _plugin_with_setup(setup: object) -> ResolvedPlugin:
    """构造仅满足元数据读取 seam 所需形状的已解析插件。"""
    return cast(
        "ResolvedPlugin",
        SimpleNamespace(definition=SimpleNamespace(setup=setup)),
    )


def test_plugin_metadata_merges_setup_and_module_metadata() -> None:
    setup = SimpleNamespace(
        meta={"control": "setup", "shared": "setup"},
        plugin_meta={"relations": "module", "shared": "module"},
    )

    assert plugin_metadata(_plugin_with_setup(setup)) == {
        "control": "setup",
        "relations": "module",
        "shared": "module",
    }


def test_plugin_metadata_ignores_non_mapping_carriers() -> None:
    setup = SimpleNamespace(meta=["not-a-mapping"], plugin_meta=None)

    assert plugin_metadata(_plugin_with_setup(setup)) == {}


def test_plugin_metadata_returns_an_isolated_view() -> None:
    declared = {"scope": "run"}
    setup = SimpleNamespace(meta=declared)

    metadata = plugin_metadata(_plugin_with_setup(setup))
    metadata["scope"] = "session"

    assert declared == {"scope": "run"}
