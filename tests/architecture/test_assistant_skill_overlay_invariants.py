"""ADR-0187 §6 删除条件 + §7 PR-6 架构不变量(assistant.skill_overlay)。

每条测试对应一项删除条件 / 安全立场:

- 写路径 ⊆ ``{home}/skills/``;**禁写**全局 ``~/.lca/skills/``
  (静态:模块不引用全局 store 默认路径;动态:HOME 重定向后安装
  不触达 ``$HOME/.lca/skills``)
- 未 VERIFIED 不可 activate(ADR-0187 §3 D6 fail-closed)
- install / activate EP 必含四件套字段(ADR-0187 §3 D8)
- ``AssistantRuntime`` / ``AssistantLoop`` / ``compile_assistant_plan`` = 0
  (与 ``test_assistant_runtime_invariants`` 同口径,本文件按删除条件
  原文三词重扫一遍)
- 拉取必经 0048 既有机制:模块内无 ``urllib`` / ``requests`` / ``httpx``
  直接导入
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
LCA = REPO / "lca"
OVERLAY_MODULE = LCA / "plugins" / "assistant" / "skill_overlay.py"

_BANNED_TOKENS: tuple[str, ...] = (
    "AssistantRuntime",
    "AssistantLoop",
    "compile_assistant_plan",
)


def _read_lca_source() -> str:
    """把 lca/ 下所有 ``.py`` 文件拼成一个字符串(忽略 __pycache__)。"""
    chunks: list[str] = []
    for path in sorted(LCA.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _code_only(text: str) -> str:
    """去除 docstring 与行注释,只留代码。"""
    stripped = re.sub(r'"""[\s\S]*?"""', "", text)
    stripped = re.sub(r"'''[\s\S]*?'''", "", stripped)
    lines = [line for line in stripped.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


# ── 写路径 ⊆ {home}/skills/;禁写全局 ~/.lca/skills ─────────────────


class TestWritePathConstrainedToHomeSkills:
    def test_module_does_not_reference_global_skill_store(self) -> None:
        """静态:不引用全局 store 默认路径,不调 ``get_skill_settings``。"""
        code = _code_only(OVERLAY_MODULE.read_text(encoding="utf-8"))
        assert ".lca/skills" not in code, "overlay 代码引用全局 skills store 路径"
        assert "Path.home()" not in code, "overlay 代码不得用 Path.home() 定落点"
        assert "get_skill_settings" not in code, (
            "overlay 不得用全局默认 SkillSettings(cache_dir 缺省 = ~/.lca/skills)"
        )

    def test_module_constructs_store_with_explicit_cache_dir(self) -> None:
        """每个 ``DiskSkillPackageStore(`` 调用点必须带显式 settings。"""
        code = _code_only(OVERLAY_MODULE.read_text(encoding="utf-8"))
        for match in re.finditer(r"DiskSkillPackageStore\(([^)]*)\)", code):
            arg = match.group(1)
            assert "SkillSettings(cache_dir=" in arg, (
                f"DiskSkillPackageStore 调用缺显式 cache_dir: {match.group(0)!r}"
            )

    @pytest.mark.asyncio
    async def test_install_does_not_touch_global_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """动态:HOME 重定向后,本地源安装不在 ``$HOME/.lca/skills`` 落任何文件。"""
        from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
        from lca.contracts.protocols.assistant.skill_overlay import SkillSource
        from lca.plugins.assistant.catalog import AssistantCatalogImpl
        from lca.plugins.assistant.skill_overlay import AssistantSkillOverlayImpl

        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        root = tmp_path / "assistants"
        skill_src = tmp_path / "pkg"
        skill_src.mkdir()
        (skill_src / "SKILL.md").write_text(
            "---\nname: iso-skill\ndescription: d\n---\nbody\n", encoding="utf-8"
        )

        catalog = AssistantCatalogImpl(root=root)
        overlay = AssistantSkillOverlayImpl(catalog=catalog)
        handle = catalog.create(CreateAssistantRequest(name="Iso"))
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(skill_src)))

        assert (Path(handle.home_path) / "skills" / "iso-skill" / "SKILL.md").is_file()
        global_store = fake_home / ".lca" / "skills"
        assert not global_store.exists(), (
            f"install 触达全局 skills store: {list(global_store.rglob('*')) if global_store.exists() else ''}"
        )


# ── 未 VERIFIED 不可 activate(ADR-0187 §3 D6)─────────────────────


class TestUnverifiedPackageCannotActivate:
    @pytest.mark.asyncio
    async def test_manually_drafted_package_rejected(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
        from lca.contracts.protocols.assistant.skill_overlay import SkillNotVerified
        from lca.plugins.assistant.catalog import AssistantCatalogImpl
        from lca.plugins.assistant.skill_overlay import AssistantSkillOverlayImpl

        catalog = AssistantCatalogImpl(root=tmp_path / "assistants")
        overlay = AssistantSkillOverlayImpl(catalog=catalog)
        handle = catalog.create(CreateAssistantRequest(name="Gate"))
        rogue = Path(handle.home_path) / "skills" / "rogue"
        rogue.mkdir(parents=True)
        (rogue / "SKILL.md").write_text("draft", encoding="utf-8")

        with pytest.raises(SkillNotVerified):
            overlay.activate(handle.assistant_id, "rogue")

    def test_activate_state_allowlist_is_closed(self) -> None:
        from lca.plugins.assistant.skill_overlay import _ACTIVATABLE_STATES

        assert frozenset({"verified", "active"}) == _ACTIVATABLE_STATES


# ── install / activate EP 必含四件套(ADR-0187 §3 D8)───────────────


class TestEPClosureForInstallAndActivate:
    @pytest.mark.asyncio
    async def test_install_and_activate_eps_carry_required_fields(self, tmp_path: Path) -> None:
        from lca.contracts.observability.assistant_ep_closure import (
            ASSISTANT_REQUIRED_FIELDS,
            ASSISTANT_SKILL_ACTIVATED,
            ASSISTANT_SKILL_INSTALLED,
        )
        from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
        from lca.contracts.protocols.assistant.skill_overlay import SkillSource
        from lca.plugins.assistant.catalog import AssistantCatalogImpl
        from lca.plugins.assistant.skill_overlay import AssistantSkillOverlayImpl

        emitted: list[tuple[str, dict[str, Any]]] = []

        def _record(event: str, payload: Mapping[str, Any]) -> None:
            emitted.append((event, dict(payload)))

        catalog = AssistantCatalogImpl(root=tmp_path / "assistants", event_emitter=_record)
        overlay = AssistantSkillOverlayImpl(catalog=catalog, event_emitter=_record)
        handle = catalog.create(CreateAssistantRequest(name="Ep"))
        skill_src = tmp_path / "pkg"
        skill_src.mkdir()
        (skill_src / "SKILL.md").write_text(
            "---\nname: ep-skill\ndescription: d\n---\nbody\n", encoding="utf-8"
        )

        await overlay.install(handle.assistant_id, SkillSource(local_path=str(skill_src)))
        overlay.activate(handle.assistant_id, "ep-skill")

        by_ep = dict(emitted)
        assert ASSISTANT_SKILL_INSTALLED in by_ep, "install 未发 assistant.skill.installed"
        assert ASSISTANT_SKILL_ACTIVATED in by_ep, "activate 未发 assistant.skill.activated"
        for ep in (ASSISTANT_SKILL_INSTALLED, ASSISTANT_SKILL_ACTIVATED):
            for field_name in ASSISTANT_REQUIRED_FIELDS:
                assert field_name in by_ep[ep], f"{ep} payload 缺 {field_name}"

    def test_plugin_ownership_declares_both_eps(self) -> None:
        from lca.contracts.observability.assistant_ep_closure import (
            ASSISTANT_SKILL_ACTIVATED,
            ASSISTANT_SKILL_INSTALLED,
        )
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.skill_overlay import setup

        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assert ASSISTANT_SKILL_INSTALLED in definition.ownership.emits
        assert ASSISTANT_SKILL_ACTIVATED in definition.ownership.emits

    def test_ep_emission_limited_to_two_skill_eps(self) -> None:
        """PR-6 只允许发 ``assistant.skill.installed`` + ``assistant.skill.activated``。"""
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.skill_overlay import setup

        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assistant_eps = {ep for ep in definition.ownership.emits if ep.startswith("assistant.")}
        assert assistant_eps == {
            "assistant.skill.installed",
            "assistant.skill.activated",
        }


# ── 删除条件:无第二套 loop / 平行编译器 ────────────────────────────


class TestNoParallelAssistantLoopOrCompiler:
    @pytest.mark.parametrize("token", _BANNED_TOKENS)
    def test_banned_token_absent_from_lca(self, token: str) -> None:
        text = _read_lca_source()
        class_pattern = re.compile(rf"^\s*class\s+{token}\b", re.MULTILINE)
        assert class_pattern.findall(text) == [], f"lca/ 出现 class {token} 定义"
        assert f"{token}(" not in text and f"class {token}" not in text, f"lca/ 出现 {token} 引用"


# ── 拉取必经 0048:禁直连网络库 ─────────────────────────────────────


class TestNoDirectNetworkImports:
    def test_overlay_module_has_no_http_client_imports(self) -> None:
        code = _code_only(OVERLAY_MODULE.read_text(encoding="utf-8"))
        for banned in ("import httpx", "import requests", "import urllib", "from urllib"):
            assert banned not in code, f"overlay 直连网络库: {banned!r}(应经 0048)"

    def test_overlay_uses_0048_importer_seam(self) -> None:
        code = _code_only(OVERLAY_MODULE.read_text(encoding="utf-8"))
        assert "import_from_url" in code, "overlay 应经 SkillImporter.import_from_url 拉取"
        assert "install_package" in code, "overlay 应经 SkillPackageInstaller.install_package 校验"
