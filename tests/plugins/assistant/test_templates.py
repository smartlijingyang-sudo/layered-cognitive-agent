"""角色模板注册表 + 引导式创建 BOOTSTRAP 完成流（ADR-0187 §3 D11/D12）。

覆盖：

- ``TEMPLATE_REGISTRY`` 6 个 template_id 全部可渲染，配置面文件齐全；
- 每个角色模板的 profile.json emoji / SOUL 人设非空；
- ``catalog.create`` 接受已登记角色模板，manifest.template_id 一致；
- 未知 template_id ⇒ ``AssistantCatalogError``（fail-closed，不回落）；
- ``seed_user_md`` 非空 ⇒ 删除 BOOTSTRAP.md + 发 ``assistant.bootstrap.completed``；
- 无 ``seed_user_md`` ⇒ 保留 BOOTSTRAP.md、不发完成 EP。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CREATED,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.plugins.assistant._home_layout import (
    CONFIG_FACE_FILES,
    TEMPLATE_REGISTRY,
    AssistantCatalogError,
    known_template_ids,
    render_template,
)
from lca.plugins.assistant.catalog import AssistantCatalogImpl

ROLE_TEMPLATES: tuple[str, ...] = (
    "assistant.research",
    "assistant.writing",
    "assistant.coding",
    "assistant.translation",
    "assistant.daily",
)


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(tmp_path: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=tmp_path, event_emitter=_record)


class TestTemplateRegistry:
    def test_registry_contains_default_and_five_roles(self) -> None:
        assert set(known_template_ids()) == {
            "assistant.default",
            *ROLE_TEMPLATES,
        }

    @pytest.mark.parametrize("template_id", sorted(TEMPLATE_REGISTRY))
    def test_render_template_produces_all_config_face_files(self, template_id: str) -> None:
        rendered = render_template(template_id, name="小助", description="测试职责")
        for entry in CONFIG_FACE_FILES:
            assert entry in rendered.files, f"{template_id} 缺 {entry}"
        assert rendered.files["BOOTSTRAP.md"].strip()
        assert "小助" in rendered.files["IDENTITY.md"]
        assert "{{ name }}" not in rendered.files["IDENTITY.md"]

    @pytest.mark.parametrize("template_id", ROLE_TEMPLATES)
    def test_role_template_profile_carries_emoji_and_soul(self, template_id: str) -> None:
        rendered = render_template(template_id, name="角色", description="角色职责")
        profile = json.loads(rendered.files["profile.json"])
        assert profile["emoji"].strip(), f"{template_id} 缺 emoji"
        assert rendered.files["SOUL.md"].strip()
        goals = rendered.files["goals.yaml"]
        assert "name:" in goals, f"{template_id} goals.yaml 应含具体目标"

    def test_render_unknown_template_raises(self) -> None:
        with pytest.raises(AssistantCatalogError, match="template_id"):
            render_template("assistant.nonexistent", name="x", description="")


class TestCreateWithRoleTemplates:
    @pytest.mark.parametrize("template_id", ROLE_TEMPLATES)
    def test_create_accepts_role_templates(
        self, catalog: AssistantCatalogImpl, template_id: str
    ) -> None:
        handle = catalog.create(CreateAssistantRequest(name="角色助理", template_id=template_id))
        manifest = json.loads((Path(handle.home_path) / "manifest.json").read_text())
        assert manifest["template_id"] == template_id

    def test_create_rejects_unknown_template(self, catalog: AssistantCatalogImpl) -> None:
        with pytest.raises(AssistantCatalogError, match="template_id"):
            catalog.create(CreateAssistantRequest(name="x", template_id="other.tpl"))


class TestBootstrapCompletion:
    def test_seed_user_md_deletes_bootstrap_and_emits_ep(
        self, catalog: AssistantCatalogImpl, emitted: list[tuple[str, dict[str, Any]]]
    ) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="引导创建",
                template_id="assistant.research",
                seed_user_md="# USER\n\n用户偏好：报告要带引用。",
            )
        )
        assert not (Path(handle.home_path) / "BOOTSTRAP.md").exists()
        user_md = (Path(handle.home_path) / "USER.md").read_text(encoding="utf-8")
        assert "报告要带引用" in user_md

        events = [event for event, _ in emitted]
        assert ASSISTANT_CREATED in events
        assert ASSISTANT_BOOTSTRAP_COMPLETED in events
        completed = dict(emitted[events.index(ASSISTANT_BOOTSTRAP_COMPLETED)][1])
        assert completed["assistant_id"] == handle.assistant_id
        assert completed["revision_seq"] == 0
        assert completed["manifest_digest"]
        assert completed["actor"]

    def test_no_seed_keeps_bootstrap_and_skips_ep(
        self, catalog: AssistantCatalogImpl, emitted: list[tuple[str, dict[str, Any]]]
    ) -> None:
        handle = catalog.create(CreateAssistantRequest(name="裸创建"))
        assert (Path(handle.home_path) / "BOOTSTRAP.md").exists()
        events = [event for event, _ in emitted]
        assert ASSISTANT_BOOTSTRAP_COMPLETED not in events

    def test_bootstrap_absent_from_digest_face(self, catalog: AssistantCatalogImpl) -> None:
        """BOOTSTRAP.md 不在配置面 digest 内：删除不影响 get 校验。"""
        handle = catalog.create(
            CreateAssistantRequest(name="digest 校验", seed_user_md="# USER\n\nx")
        )
        spec = catalog.get(handle.assistant_id)
        assert spec.assistant_id == handle.assistant_id
