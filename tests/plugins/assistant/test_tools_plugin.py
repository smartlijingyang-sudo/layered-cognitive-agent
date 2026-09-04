"""assistant.tools plugin tests（create_assistant 工具工厂）。

覆盖：工厂注册的 ``assistant`` factory 返回 ``AssistantCreateTool``，
且工具持有 boot 期注入的 catalog / bridge 句柄；``provides`` 为空
（工厂注册是动作，不是 capability，与 lca-tools-provider 约定一致）。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.harness.plugin_api import definition_from_plugin
from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool
from lca.plugins.assistant import tools as tools_plugin


class _FakeToolsService:
    def __init__(self) -> None:
        self.factories: dict[str, Any] = {}

    def register_factory(self, name: str, factory: Any) -> None:
        self.factories[name] = factory


class _FakeCtx:
    def __init__(self, catalog: Any, bridge: Any, tools: _FakeToolsService) -> None:
        self._catalog = catalog
        self._bridge = bridge
        self._tools = tools

    def require(self, key: str) -> Any:
        if key == "assistant.catalog":
            return self._catalog
        if key == "assistant.frontend_bridge":
            return self._bridge
        if key == "tools":
            return self._tools
        raise KeyError(key)

    def soft_get(self, key: str) -> Any:
        if key == "assistant.frontend_bridge":
            return self._bridge
        return None


@pytest.mark.asyncio
async def test_setup_registers_assistant_factory() -> None:
    tools_service = _FakeToolsService()
    ctx = _FakeCtx(catalog=object(), bridge=object(), tools=tools_service)
    await tools_plugin.setup.setup(ctx, None)
    assert "assistant" in tools_service.factories


@pytest.mark.asyncio
async def test_factory_builds_create_tool_with_injected_deps() -> None:
    catalog = object()
    bridge = object()
    tools_service = _FakeToolsService()
    ctx = _FakeCtx(catalog=catalog, bridge=bridge, tools=tools_service)
    await tools_plugin.setup.setup(ctx, None)

    produced = tools_service.factories["assistant"](None)
    assert isinstance(produced, list) and len(produced) == 1
    tool = produced[0]
    assert isinstance(tool, AssistantCreateTool)
    assert tool._catalog is catalog
    assert tool._bridge is bridge


def test_plugin_manifest_declares_no_provides() -> None:
    defn = definition_from_plugin(tools_plugin.setup)
    assert set(defn.provided_capability_keys) == set()
    assert "assistant.catalog" in set(defn.required_capability_keys)
    assert "tools" in set(defn.required_capability_keys)
