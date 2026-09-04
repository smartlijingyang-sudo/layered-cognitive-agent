"""create_assistant tool tests（ADR-0187 §3 D12 执行面）。

覆盖：

- validate：缺 name / 未知 template ⇒ 错误信息；
- execute：catalog.create 被正确调用，payload 含 assistant_id / emoji /
  capabilities / bootstrap_completed / frontend 字段；
- bridge 返回 None ⇒ 仍 success，frontend_url=None（fail-soft）；
- bridge 返回 agt_* ⇒ frontend_url=/agent/<agt_*>；
- catalog 抛错 ⇒ success=False 且不触达 bridge。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.protocols.assistant.catalog import (
    AssistantHandle,
    CreateAssistantRequest,
)
from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool
from lca.plugins.assistant.catalog import AssistantCatalogImpl


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(tmp_path: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: dict[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=tmp_path, event_emitter=_record)


class _FakeBridge:
    def __init__(self, result: str | None) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def register(self, **kwargs: Any) -> str | None:
        self.calls.append(kwargs)
        return self._result


class TestValidate:
    def test_missing_name_rejected(self, catalog: AssistantCatalogImpl) -> None:
        tool = AssistantCreateTool(catalog=catalog)
        assert tool.validate({}) is not None
        assert tool.validate({"name": "  "}) is not None

    def test_unknown_template_rejected(self, catalog: AssistantCatalogImpl) -> None:
        tool = AssistantCreateTool(catalog=catalog)
        error = tool.validate({"name": "x", "template_id": "assistant.nope"})
        assert error is not None and "template_id" in error

    def test_valid_args_pass(self, catalog: AssistantCatalogImpl) -> None:
        tool = AssistantCreateTool(catalog=catalog)
        assert tool.validate({"name": "研究", "template_id": "assistant.research"}) is None


class TestExecute:
    @pytest.mark.asyncio
    async def test_create_without_bridge(self, catalog: AssistantCatalogImpl) -> None:
        tool = AssistantCreateTool(catalog=catalog, bridge=None)
        obs = await tool.execute(
            {"name": "小研", "description": "深度研究", "template_id": "assistant.research"}
        )
        assert obs.success
        payload = obs.payload
        assert payload["assistant_id"].startswith("asst_")
        assert payload["name"] == "小研"
        assert payload["emoji"] == "🔍"
        assert payload["template_id"] == "assistant.research"
        assert payload["bootstrap_completed"] is False
        assert payload["frontend_agent_id"] is None
        assert payload["frontend_url"] is None
        assert "研究" in payload["capabilities"]

    @pytest.mark.asyncio
    async def test_create_with_seed_marks_bootstrap_completed(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        tool = AssistantCreateTool(catalog=catalog, bridge=None)
        obs = await tool.execute({"name": "小研", "seed_user_md": "# USER\n\n偏好"})
        assert obs.success
        assert obs.payload["bootstrap_completed"] is True

    @pytest.mark.asyncio
    async def test_bridge_success_sets_frontend_url(self, catalog: AssistantCatalogImpl) -> None:
        bridge = _FakeBridge("agt_front")
        tool = AssistantCreateTool(catalog=catalog, bridge=bridge)
        obs = await tool.execute({"name": "小研"})
        assert obs.success
        assert obs.payload["frontend_agent_id"] == "agt_front"
        assert obs.payload["frontend_url"] == "/agent/agt_front"
        assert bridge.calls[0]["assistant_id"] == obs.payload["assistant_id"]
        assert bridge.calls[0]["emoji"] == "🤖"

    @pytest.mark.asyncio
    async def test_bridge_failure_degrades(self, catalog: AssistantCatalogImpl) -> None:
        tool = AssistantCreateTool(catalog=catalog, bridge=_FakeBridge(None))
        obs = await tool.execute({"name": "小研"})
        assert obs.success
        assert obs.payload["frontend_agent_id"] is None
        assert obs.payload["frontend_url"] is None

    @pytest.mark.asyncio
    async def test_catalog_error_returns_failure(self, catalog: AssistantCatalogImpl) -> None:
        bridge = _FakeBridge("agt_x")

        class _BoomCatalog:
            def create(self, req: CreateAssistantRequest) -> AssistantHandle:
                raise RuntimeError("disk full")

        tool = AssistantCreateTool(catalog=_BoomCatalog(), bridge=bridge)  # type: ignore[arg-type]
        obs = await tool.execute({"name": "小研"})
        assert not obs.success
        assert obs.error is not None and "disk full" in obs.error
        assert bridge.calls == []  # 创建失败不得触达前端注册
