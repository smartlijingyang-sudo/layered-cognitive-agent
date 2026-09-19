"""assistant.tool_overlay plugin tests（ADR-0243 D4）。

覆盖契约：

- create：写 ``{home}/tools/<tool_id>/tool.json`` + manifest tools 索引 +
  ``revision_seq++`` + 发 ``assistant.profile.revised`` EP（四件套）
- create 校验：非法 ToolSpec / 重复创建 ⇒ 不写盘、不发 EP
- update：覆盖式修改，``tool_id`` 必须等于 ``spec.name``
- remove：删盘 + manifest 修订 + EP；未知工具抛 ``ToolNotInstalled``
- list_installed：扫 ``{home}/tools/`` 返回回执
- 跨助理隔离：A 的工具不出现在 B
- plugin Manifest：provides / requires / effects / test_suite / emits 声明
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_TOOL_OVERLAY
from lca.contracts.models.assistant.tool_spec import ToolHandlerSpec, ToolSpec
from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_PROFILE_REVISED,
    ASSISTANT_REQUIRED_FIELDS,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.tool_overlay import ToolNotInstalled
from lca.plugins.assistant.tool.overlay import AssistantToolOverlayImpl
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl


def _spec(name: str = "my_tool") -> ToolSpec:
    return ToolSpec(
        name=name,
        description="自定义工具",
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=ToolHandlerSpec(kind="builtin_preset", builtin="runCommand"),
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "assistants"


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(root: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=root, event_emitter=_record)


@pytest.fixture
def overlay(
    catalog: AssistantCatalogImpl,
    emitted: list[tuple[str, dict[str, Any]]],
) -> AssistantToolOverlayImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantToolOverlayImpl(catalog=catalog, event_emitter=_record)


@pytest.fixture
def handle(catalog: AssistantCatalogImpl) -> Any:
    return catalog.create(CreateAssistantRequest(name="Demo", description="d"))


def _read_manifest(home: Path) -> dict[str, Any]:
    return json.loads((home / "manifest.json").read_text(encoding="utf-8"))


class TestToolSpecContract:
    def test_valid_spec(self) -> None:
        spec = _spec()
        assert spec.name == "my_tool"
        assert spec.handler.kind == "builtin_preset"
        assert spec.handler.builtin == "runCommand"

    def test_invalid_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="非法工具名"):
            _spec(name="1bad")

    def test_unknown_handler_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"未知 handler\.kind"):
            ToolSpec(
                name="t",
                description="d",
                handler=ToolHandlerSpec(kind="magic"),
            )

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValueError):
            ToolSpec.model_validate_json(
                json.dumps(_spec().model_dump() | {"extra": 1})
            )


class TestCreate:
    async def test_create_writes_home_and_manifest(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
    ) -> None:
        receipt = await overlay.create(handle.assistant_id, _spec())
        home = Path(handle.home_path)
        tool_json = home / "tools" / "my_tool" / "tool.json"
        assert tool_json.is_file()
        assert ToolSpec.model_validate_json(tool_json.read_text(encoding="utf-8")) == _spec()

        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 1
        assert manifest["digests"]["tools/my_tool"] == receipt.digest
        assert manifest["tools"]["my_tool"]["digest"] == receipt.digest

    async def test_create_emits_profile_revised_ep(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        events = [(ep, p) for ep, p in emitted if ep == ASSISTANT_PROFILE_REVISED]
        assert len(events) == 1
        _, payload = events[0]
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload, f"EP payload 缺 {field_name}"
        assert payload["assistant_id"] == handle.assistant_id
        assert payload["revision_seq"] == 1
        assert payload["reason"] == "upsert_tool"
        assert payload["changes"] == ["tools/my_tool"]

    async def test_create_duplicate_rejected(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        with pytest.raises(ValueError, match="已存在"):
            await overlay.create(handle.assistant_id, _spec())
        revised = [ep for ep, _ in emitted if ep == ASSISTANT_PROFILE_REVISED]
        assert len(revised) == 1, "重复创建不应再发 EP"

    async def test_create_bad_spec_no_write(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        with pytest.raises(ValueError, match="非法工具名"):
            await overlay.create(handle.assistant_id, _spec(name="1bad"))
        assert not (Path(handle.home_path) / "tools" / "1bad").exists()
        assert not any(ep == ASSISTANT_PROFILE_REVISED for ep, _ in emitted)


class TestUpdate:
    async def test_update_overwrites(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        updated = _spec()
        updated = ToolSpec(
            name="my_tool",
            description="改过的描述",
            parameters=updated.parameters,
            handler=updated.handler,
        )
        receipt = await overlay.update(handle.assistant_id, "my_tool", updated)
        home = Path(handle.home_path)
        parsed = ToolSpec.model_validate_json(
            (home / "tools" / "my_tool" / "tool.json").read_text(encoding="utf-8")
        )
        assert parsed.description == "改过的描述"
        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 2
        assert manifest["digests"]["tools/my_tool"] == receipt.digest

    async def test_update_tool_id_must_match_name(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        with pytest.raises(ValueError, match="不一致"):
            await overlay.update(handle.assistant_id, "other", _spec())


class TestRemove:
    async def test_remove_deletes_dir_and_manifest(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        await overlay.remove(handle.assistant_id, "my_tool")
        home = Path(handle.home_path)
        assert not (home / "tools" / "my_tool").exists()
        manifest = _read_manifest(home)
        assert manifest["revision_seq"] == 2
        assert "tools/my_tool" not in manifest.get("tools", {})
        assert any(ep == ASSISTANT_PROFILE_REVISED for ep, _ in emitted)

    async def test_remove_unknown_tool_raises(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
    ) -> None:
        with pytest.raises(ToolNotInstalled):
            await overlay.remove(handle.assistant_id, "missing")


class TestListInstalled:
    async def test_list_returns_receipts(
        self,
        overlay: AssistantToolOverlayImpl,
        handle: Any,
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        await overlay.create(handle.assistant_id, _spec(name="second_tool"))
        receipts = overlay.list_installed(handle.assistant_id)
        assert [r.tool_id for r in receipts] == ["my_tool", "second_tool"]
        assert all(r.digest.startswith("sha256:") for r in receipts)
        assert all(r.install_path.startswith(handle.home_path) for r in receipts)

    async def test_cross_assistant_isolation(
        self,
        overlay: AssistantToolOverlayImpl,
        catalog: AssistantCatalogImpl,
        handle: Any,
    ) -> None:
        await overlay.create(handle.assistant_id, _spec())
        other = catalog.create(CreateAssistantRequest(name="Other", description="d"))
        assert overlay.list_installed(other.assistant_id) == ()
        assert not (Path(other.home_path) / "tools" / "my_tool").exists()


class TestPluginManifest:
    def test_manifest_shape(self) -> None:
        from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
            PluginSpecKind,
        )
        from lca.harness.plugin.manifest import EffectClass
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.tool.overlay import setup

        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.tool.overlay"
        assert ASSISTANT_TOOL_OVERLAY.key in definition.provided_capability_keys
        assert "assistant.catalog" in definition.required_capability_keys
        assert definition.spec.layer == "L4"
        assert definition.spec.kind is PluginSpecKind.PROVIDER
        assert EffectClass.FILESYSTEM in definition.spec.effects
        assert (
            definition.spec.verification.test_suite
            == "tests/plugins/assistant/test_tool_overlay.py"
        )
        assert definition.ownership is not None
        assert ASSISTANT_PROFILE_REVISED in definition.ownership.emits
