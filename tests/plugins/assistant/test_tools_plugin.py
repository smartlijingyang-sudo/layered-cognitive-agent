"""assistant.tools plugin tests（create_assistant / create_assistant_skill 工具工厂）。"""

from __future__ import annotations

from typing import Any

import pytest

from lca.harness.plugin_api import definition_from_plugin
from lca.infrastructure.tools.assistant.create_skill_tool import AssistantCreateSkillTool
from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool
from lca.plugins.assistant import tools as tools_plugin


class _FakeToolsService:
    def __init__(self) -> None:
        self.factories: dict[str, Any] = {}

    def register_factory(self, name: str, factory: Any) -> None:
        self.factories[name] = factory


class _FakeCtx:
    def __init__(self, catalog: Any, bridge: Any, overlay: Any, tools: _FakeToolsService) -> None:
        self._catalog = catalog
        self._bridge = bridge
        self._overlay = overlay
        self._tools = tools

    def require(self, key: str) -> Any:
        if key == "assistant.catalog":
            return self._catalog
        if key == "assistant.frontend_bridge":
            return self._bridge
        if key == "assistant.skill_overlay":
            return self._overlay
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
    ctx = _FakeCtx(catalog=object(), bridge=object(), overlay=object(), tools=tools_service)
    await tools_plugin.setup.setup(ctx, None)
    assert "assistant" in tools_service.factories


@pytest.mark.asyncio
async def test_factory_builds_create_tool_with_injected_deps() -> None:
    catalog = object()
    bridge = object()
    overlay = object()
    tools_service = _FakeToolsService()
    ctx = _FakeCtx(catalog=catalog, bridge=bridge, overlay=overlay, tools=tools_service)
    await tools_plugin.setup.setup(ctx, None)

    produced = tools_service.factories["assistant"](None)
    assert isinstance(produced, list) and len(produced) == 1
    tool = produced[0]
    assert isinstance(tool, AssistantCreateTool)
    assert tool._catalog is catalog
    assert tool._bridge is bridge


@pytest.mark.asyncio
async def test_factory_adds_create_skill_tool_when_assistant_id_bound() -> None:
    overlay = object()
    tools_service = _FakeToolsService()
    ctx = _FakeCtx(catalog=object(), bridge=object(), overlay=overlay, tools=tools_service)
    await tools_plugin.setup.setup(ctx, None)

    produced = tools_service.factories["assistant"]({"assistant_id": "asst_demo"})
    assert isinstance(produced, list) and len(produced) == 2
    assert isinstance(produced[0], AssistantCreateTool)
    assert isinstance(produced[1], AssistantCreateSkillTool)
    assert produced[1]._overlay is overlay
    assert produced[1]._assistant_id == "asst_demo"


def test_plugin_manifest_declares_no_provides() -> None:
    defn = definition_from_plugin(tools_plugin.setup)
    assert set(defn.provided_capability_keys) == set()
    assert "assistant.catalog" in set(defn.required_capability_keys)
    assert "assistant.skill_overlay" in set(defn.required_capability_keys)
    assert "tools" in set(defn.required_capability_keys)
