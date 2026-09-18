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
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl


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


def _valid_soul() -> str:
    """构造一个能通过完整度校验的 SOUL（四核心段 + 去空白 >= 200 字符）。"""
    return (
        "## 🧠 身份\n"
        "你是向导助理，服务用户完成深度研究。\n"
        + "你是一位资深研究员。" * 20
        + "\n## 🎭 性格\n"
        + "结论先行，直接坦诚。" * 20
        + "\n## 🛠 能力\n"
        + "擅长资料搜集与交叉核验。" * 20
        + "\n## 🗣 语气\n"
        + "专业务实，简洁量化。" * 20
    )


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
        # capabilities 是结构化清单（ADR-0242 D7）：含模板示例目标与工具名
        assert isinstance(payload["capabilities"], list)
        assert "深度研究" in payload["capabilities"]
        assert "workspace.read" in payload["capabilities"]
        # personality / tone 从 SOUL 提取
        assert payload["personality"]
        assert payload["tone"]

    @pytest.mark.asyncio
    async def test_create_with_soul_marks_bootstrap_completed(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        tool = AssistantCreateTool(catalog=catalog, bridge=None)
        soul = _valid_soul()
        obs = await tool.execute({"name": "向导", "soul": soul})
        assert obs.success
        assert obs.payload["bootstrap_completed"] is True

    @pytest.mark.asyncio
    async def test_soul_validation_failure_returns_validation_kind(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        tool = AssistantCreateTool(catalog=catalog, bridge=None)
        # 缺「语气」段的 SOUL ⇒ 校验失败 ⇒ success=False + validation kind
        soul_missing_tone = (
            "## 🧠 身份\n"
            + "你是一个测试助理。" * 30
            + "\n## 🎭 性格\n"
            + "直接坦诚。" * 30
            + "\n## 🛠 能力\n"
            + "擅长测试。" * 30
        )
        obs = await tool.execute({"name": "向导", "soul": soul_missing_tone})
        assert not obs.success
        assert obs.error is not None and "## 🗣 语气" in obs.error
        from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION

        assert obs.extra.get(FAILURE_KIND) == FAILURE_KIND_VALIDATION

    @pytest.mark.asyncio
    async def test_soul_and_inherit_from_passed_to_catalog(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        captured: list[CreateAssistantRequest] = []

        class _RecordingCatalog:
            def create(self, req: CreateAssistantRequest) -> AssistantHandle:
                captured.append(req)
                return AssistantHandle(
                    assistant_id="asst_rec",
                    home_path=str(catalog._root / "asst_rec"),
                    revision_seq=0,
                )

        tool = AssistantCreateTool(catalog=_RecordingCatalog())  # type: ignore[arg-type]
        obs = await tool.execute(
            {
                "name": "向导",
                "soul": _valid_soul(),
                "inherit_from": "asst_source",
            }
        )
        assert obs.success
        assert len(captured) == 1
        assert captured[0].soul == _valid_soul()
        assert captured[0].inherit_from == "asst_source"

    @pytest.mark.asyncio
    async def test_create_with_seed_marks_bootstrap_completed(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        tool = AssistantCreateTool(catalog=catalog, bridge=None)
        obs = await tool.execute({"name": "小研", "seed_user_md": "# USER\n\n偏好"})
        assert obs.success
        assert obs.payload["bootstrap_completed"] is True

    @pytest.mark.asyncio
    async def test_bridge_receives_home_opening_message(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        """bridge 的 opening_message 必须来自 Home profile.json，而不是工具拼装。"""
        bridge = _FakeBridge("agt_front")
        tool = AssistantCreateTool(catalog=catalog, bridge=bridge)
        obs = await tool.execute({"name": "小研"})
        assert obs.success
        assert bridge.calls[0]["opening_message"] == ""  # 默认模板 profile.json 为空

    @pytest.mark.asyncio
    async def test_bridge_receives_description_with_capability_merge(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        """ADR-0242 D7:能力摘要并入 description，前端 agent 行直接可见。"""
        bridge = _FakeBridge("agt_front")
        tool = AssistantCreateTool(catalog=catalog, bridge=bridge)
        obs = await tool.execute({"name": "小研", "description": "深度研究"})
        assert obs.success
        merged = bridge.calls[0]["description"]
        assert merged.startswith("深度研究 · 能力：")
        # 默认模板 goals + tools allow 都进入能力清单。
        assert "日常协助" in merged
        assert "workspace.read" in merged
        # Observation payload 的 capabilities 与并入描述的能力同源。
        assert obs.payload["capabilities"] == ["日常协助", "信息整理", "问题解答",
                                               "workspace.read", "workspace.write", "workspace.list"]

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
