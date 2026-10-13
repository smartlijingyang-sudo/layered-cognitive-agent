"""Tests for ``resolve_skill_store`` (ADR-0242 D4 / I-B4).

Verifies the global-vs-merged decision and the "Home skill is loadable via
``activate_skill``" integration — the regression guard for the
"有发现、无加载" gap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.infrastructure.skills.assistant.merged_store import AssistantMergedSkillStore
from lca.infrastructure.skills.assistant.resolver import resolve_skill_store
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.infrastructure.tools.skills._package_lookup import resolve_package
from lca.infrastructure.tools.skills.activate.tool import SkillActivateTool
from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl


class _FakeService:
    """Definition-service stand-in exposing ``current()`` to provider_current."""

    def __init__(self, current: Any = None) -> None:
        self._current = current

    def current(self) -> Any:
        return self._current


class _FakeCtx:
    """Minimal Cordis-like context: ``require`` raises KeyError when absent."""

    def __init__(self, services: dict[str, Any]) -> None:
        self._services = dict(services)

    def require(self, key: str) -> Any:
        if key not in self._services:
            raise KeyError(key)
        return self._services[key]


def _global_store(tmp_path: Path) -> DiskSkillPackageStore:
    return DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "global"))


class TestResolveSkillStore:
    def test_without_assistant_id_returns_global_store(self, tmp_path: Path) -> None:
        global_store = _global_store(tmp_path)
        ctx = _FakeCtx({"skills": _FakeService(global_store)})
        assert resolve_skill_store(ctx, "") is global_store

    def test_with_assistant_id_but_no_overlay_returns_global_store(self, tmp_path: Path) -> None:
        global_store = _global_store(tmp_path)
        ctx = _FakeCtx({"skills": _FakeService(global_store)})
        assert resolve_skill_store(ctx, "asst_x") is global_store

    def test_with_assistant_id_and_overlay_returns_merged_store(self, tmp_path: Path) -> None:
        global_store = _global_store(tmp_path)
        overlay = object()
        ctx = _FakeCtx(
            {
                "skills": _FakeService(global_store),
                "assistant.skill_overlay": _FakeService(overlay),
            }
        )
        merged = resolve_skill_store(ctx, "asst_x")
        assert isinstance(merged, AssistantMergedSkillStore)
        assert merged._global is global_store
        assert merged._overlay is overlay
        assert merged._assistant_id == "asst_x"

    def test_blank_assistant_id_returns_global_store(self, tmp_path: Path) -> None:
        global_store = _global_store(tmp_path)
        ctx = _FakeCtx({"skills": _FakeService(global_store)})
        assert resolve_skill_store(ctx, "   ") is global_store


@pytest.mark.asyncio
class TestHomeSkillActivationViaMergedStore:
    """A Home-installed skill must be reachable through ``activate_skill``
    when the run resolves the merged store (I-B4)."""

    async def test_activate_skill_resolves_home_skill(self, tmp_path: Path) -> None:
        catalog = AssistantCatalogImpl(root=tmp_path / "assistants")
        overlay = AssistantSkillOverlayImpl(catalog=catalog)
        handle = catalog.create(CreateAssistantRequest(name="SkillOwner"))

        skill_src = tmp_path / "pkg"
        skill_src.mkdir()
        (skill_src / "SKILL.md").write_text(
            "---\nname: assistant-only\ndescription: home skill\nreferences: []\n---\nbody\n",
            encoding="utf-8",
        )
        await overlay.install(handle.assistant_id, SkillSource(local_path=str(skill_src)))

        global_store = _global_store(tmp_path)
        global_store.install_package(
            skill_id="global-skill",
            skill_md_text="---\nname: global\ndescription: g\nreferences: []\n---\nbody",
            resource_files={},
            source_url="u",
        )
        ctx = _FakeCtx(
            {
                "skills": _FakeService(global_store),
                "assistant.skill_overlay": _FakeService(overlay),
            }
        )
        merged = resolve_skill_store(ctx, handle.assistant_id)
        assert isinstance(merged, AssistantMergedSkillStore)

        tool = SkillActivateTool(store=merged)
        package = resolve_package(tool._store, "assistant-only")
        assert package is not None
        assert package.skill_id == "assistant-only"
        # Global skills remain reachable through the same merged view.
        assert resolve_package(tool._store, "global-skill") is not None


class TestResolvePackageSeam:
    """``resolve_package`` 的直接单元测试：interface 即测试面（RA-127）。

    此前覆盖走的是各 tool 的私有 ``_resolve_package`` adapter；adapter 已删，
    测试面回到共享 seam 本体。
    """

    def _store(self, tmp_path: Path) -> DiskSkillPackageStore:
        store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "seam"))
        store.install_package(
            skill_id="pkg-one",
            skill_md_text="---\nname: One\ndescription: d\nreferences: []\n---\nbody",
            resource_files={},
            source_url="u",
        )
        return store

    def test_exact_id_hit(self, tmp_path: Path) -> None:
        package = resolve_package(self._store(tmp_path), "pkg-one")
        assert package is not None
        assert package.skill_id == "pkg-one"

    def test_name_fallback_case_insensitive(self, tmp_path: Path) -> None:
        package = resolve_package(self._store(tmp_path), "ONE")
        assert package is not None
        assert package.skill_id == "pkg-one"

    def test_miss_returns_none(self, tmp_path: Path) -> None:
        assert resolve_package(self._store(tmp_path), "no-such-skill") is None
