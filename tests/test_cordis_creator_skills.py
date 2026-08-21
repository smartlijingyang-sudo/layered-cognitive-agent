"""Bundled skills for cordis-creator persona — discovery, install, and tool use.

Asserts that two first-party SKILL.md packs ship at the repo root under
``skills/``, that ``ensure_bundled_skills`` materializes them into a
:class:`DiskSkillPackageStore`, that ``_render_available_skills`` exposes
their summary + version in the prompt catalog, and that
``SkillActivateTool`` / ``SkillReadReferenceTool`` load the body and
resource files. Mirrors the pattern of :mod:`tests.test_officecli_plane`.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from lca.layer0_infra.skills.activation_scope import activated_skills_scope
from lca.layer0_infra.skills.bundled import (
    default_bundled_skills_root,
    ensure_bundled_skills,
)
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore
from lca.layer0_infra.skills.settings import SkillSettings
from lca.layer0_infra.tools.skills.activate_tool import SkillActivateTool
from lca.layer0_infra.tools.skills.read_reference_tool import SkillReadReferenceTool

CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID: str = "cordis-plugin-development"
EDITING_LCA_COMPOSITIONS_SKILL_ID: str = "editing-lca-compositions"

_EXPECTED_BUNDLED_IDS: tuple[str, ...] = (
    CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID,
    EDITING_LCA_COMPOSITIONS_SKILL_ID,
)


def _stub_scope_with_skill_store(store: DiskSkillPackageStore) -> SimpleNamespace:
    """Build a minimal scope stub that exposes a `skills.current()` provider."""

    skills_provider = SimpleNamespace(current=lambda: store)
    return SimpleNamespace(_skills_provider=skills_provider)


def _patch_skill_store_resolution(monkeypatch: Any, store: DiskSkillPackageStore) -> None:
    """Replace ``_skill_store_from_scope`` so ``_render_available_skills``
    can read from a store without booting the full cordis context."""
    from lca.layer4_app import spawn as spawn_module

    monkeypatch.setattr(spawn_module, "_skill_store_from_scope", lambda _scope: store)


class TestBundledCordisCreatorSkills(unittest.TestCase):
    """Skills required by the cordis-creator persona (Creator §13.3)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_repo_ships_cordis_plugin_development_skill_pack(self) -> None:
        root = default_bundled_skills_root()
        skill_md = root / CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID / "SKILL.md"
        self.assertTrue(skill_md.is_file(), f"missing {skill_md}")
        text = skill_md.read_text(encoding="utf-8")
        self.assertIn("PluginMeta", text)
        self.assertIn("§23.2", text)
        self.assertIn("PR12", text)
        self.assertIn("cordis_control", text)

    def test_repo_ships_editing_lca_compositions_skill_pack(self) -> None:
        root = default_bundled_skills_root()
        skill_md = root / EDITING_LCA_COMPOSITIONS_SKILL_ID / "SKILL.md"
        self.assertTrue(skill_md.is_file(), f"missing {skill_md}")
        text = skill_md.read_text(encoding="utf-8")
        self.assertIn("HOST", text)
        self.assertIn("PRESET", text)
        self.assertIn("$LCA_AGENT_PRESETS_HOME", text)
        self.assertIn("C4", text)

    def test_both_skills_have_frontmatter_with_name_and_description(self) -> None:
        root = default_bundled_skills_root()
        for skill_id in _EXPECTED_BUNDLED_IDS:
            with self.subTest(skill_id=skill_id):
                text = (root / skill_id / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"), f"{skill_id} missing frontmatter")
                self.assertIn("name:", text)
                self.assertIn("description:", text)

    def test_both_skills_ship_with_references_subdir(self) -> None:
        root = default_bundled_skills_root()
        for skill_id in _EXPECTED_BUNDLED_IDS:
            resources = root / skill_id / "resources"
            self.assertTrue(resources.is_dir(), f"missing {resources}")
            self.assertTrue(any(resources.glob("*.md")), f"{resources} empty")

    def test_ensure_installs_both_skills(self) -> None:
        written = ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        for skill_id in _EXPECTED_BUNDLED_IDS:
            with self.subTest(skill_id=skill_id):
                self.assertIn(skill_id, written)
                package = self.store.get(skill_id)
                self.assertEqual(package.skill_id, skill_id)
                self.assertTrue(package.source_url.startswith("bundled:"))
                self.assertEqual(package.version, "1.0.0")

    def test_ensure_is_idempotent_when_hashes_match(self) -> None:
        first = ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        for skill_id in _EXPECTED_BUNDLED_IDS:
            self.assertIn(skill_id, first)
        second = ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        self.assertEqual(second, ())

    def test_cordis_creator_persona_goal_references_both_skills(self) -> None:
        """Persona goal text must point at both skill ids so the model knows
        to load them via the skill tool before authoring."""
        from lca.plugins.roles.cordis_creator import PERSONA_GOAL

        self.assertIn(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID, PERSONA_GOAL)
        self.assertIn(EDITING_LCA_COMPOSITIONS_SKILL_ID, PERSONA_GOAL)


class TestRenderAvailableSkills(unittest.TestCase):
    """``_render_available_skills`` must surface summary + version so the
    model can pick the right skill before loading the body."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))
        self._monkey = _MonkeyPatcher()
        self._monkey.start()
        ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        _patch_skill_store_resolution(self._monkey, self.store)

    def tearDown(self) -> None:
        self._monkey.undo()
        self._tmp.cleanup()

    def test_catalog_includes_skill_id_and_name(self) -> None:
        from lca.layer4_app.spawn import _render_available_skills

        rendered = _render_available_skills(_stub_scope_with_skill_store(self.store))
        self.assertIn(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID, rendered)
        self.assertIn(EDITING_LCA_COMPOSITIONS_SKILL_ID, rendered)
        self.assertIn("cordis-plugin-development", rendered.lower())

    def test_catalog_includes_summary_for_each_skill(self) -> None:
        """Summaries must surface so the model can route without loading body."""
        from lca.layer4_app.spawn import _render_available_skills

        rendered = _render_available_skills(_stub_scope_with_skill_store(self.store))
        for skill_id in _EXPECTED_BUNDLED_IDS:
            package = self.store.get(skill_id)
            with self.subTest(skill_id=skill_id):
                self.assertTrue(package.summary, f"{skill_id} has empty summary")
                # Summary fragment — first 32 chars keep the test stable across copy edits
                self.assertIn(package.summary[:32], rendered)

    def test_catalog_includes_version_when_present(self) -> None:
        from lca.layer4_app.spawn import _render_available_skills

        rendered = _render_available_skills(_stub_scope_with_skill_store(self.store))
        for skill_id in _EXPECTED_BUNDLED_IDS:
            package = self.store.get(skill_id)
            with self.subTest(skill_id=skill_id):
                self.assertEqual(package.version, "1.0.0")
                self.assertIn("v1.0.0", rendered)

    def test_catalog_handles_empty_store(self) -> None:
        """Empty store should produce the documented fallback string."""
        from lca.layer4_app.spawn import _render_available_skills

        empty_store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name) / "empty"))
        _patch_skill_store_resolution(self._monkey, empty_store)
        rendered = _render_available_skills(_stub_scope_with_skill_store(empty_store))
        self.assertIn("search_skill", rendered)


class TestActivateSkillTool(unittest.TestCase):
    """``activate_skill`` must return the full SKILL.md body for both creator skills."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))
        ensure_bundled_skills(self.store, root=default_bundled_skills_root())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _activate(self, skill_id: str) -> Any:
        with activated_skills_scope(()):
            tool = SkillActivateTool(self.store)
            return await tool.execute({"skill_id": skill_id})

    def test_activate_cordis_plugin_development_returns_body(self) -> None:
        observation = asyncio.run(self._activate(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID))
        self.assertTrue(observation.success)
        body = observation.payload["text"]
        self.assertIn("PR12", body)
        self.assertIn("§23.2", body)
        self.assertIn("plugin_meta", body)
        self.assertIn("cordis_control", body)

    def test_activate_editing_lca_compositions_returns_body(self) -> None:
        observation = asyncio.run(self._activate(EDITING_LCA_COMPOSITIONS_SKILL_ID))
        self.assertTrue(observation.success)
        body = observation.payload["text"]
        self.assertIn("HOST", body)
        self.assertIn("PRESET", body)
        self.assertIn("C4", body)
        self.assertIn("LCA_AGENT_PRESETS_HOME", body)

    def test_activate_unknown_skill_returns_validation_failure(self) -> None:
        observation = asyncio.run(self._activate("does-not-exist"))
        self.assertFalse(observation.success)
        self.assertIn("未找到 skill", observation.error or "")


class TestReadSkillReferenceTool(unittest.TestCase):
    """``read_skill_reference`` must load resource/*.md files declared in frontmatter."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))
        ensure_bundled_skills(self.store, root=default_bundled_skills_root())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _read_reference(self, skill_id: str, path: str) -> Any:
        tool = SkillReadReferenceTool(self.store)
        return await tool.execute({"skill_id": skill_id, "path": path})

    def test_read_plugin_meta_fields_reference(self) -> None:
        observation = asyncio.run(
            self._read_reference(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID, "plugin-meta-fields.md")
        )
        self.assertTrue(observation.success)
        body = observation.payload["text"]
        self.assertIn("layer", body)
        self.assertIn("implements", body)
        self.assertIn("policy_class", body)

    def test_read_preset_schema_reference(self) -> None:
        observation = asyncio.run(
            self._read_reference(EDITING_LCA_COMPOSITIONS_SKILL_ID, "preset-schema.md")
        )
        self.assertTrue(observation.success)
        body = observation.payload["text"]
        self.assertIn("plugin_meta", body)
        self.assertIn("source_path", body)
        self.assertIn("preset_id", body)

    def test_read_unknown_path_returns_validation_failure(self) -> None:
        observation = asyncio.run(
            self._read_reference(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID, "does-not-exist.md")
        )
        self.assertFalse(observation.success)


class TestCordisCreatorToolPermissions(unittest.TestCase):
    """``allowed_tools`` must include the skill loaders so the model can fetch body."""

    def test_role_profile_manifest_advertises_skill_loaders(self) -> None:
        from lca.plugins.roles.cordis_creator import build_cordis_creator_role_profile

        profile = build_cordis_creator_role_profile()
        allowed = set(profile.tool_permission_manifest.allowed_tools)
        self.assertIn("activate_skill", allowed)
        self.assertIn("read_skill_reference", allowed)
        self.assertIn("cordis_control", allowed)
        self.assertIn("file_write", allowed)
        self.assertIn("bash", allowed)

    def test_role_profile_manifest_budgets_skill_loaders(self) -> None:
        from lca.plugins.roles.cordis_creator import build_cordis_creator_role_profile

        profile = build_cordis_creator_role_profile()
        budgets = profile.tool_permission_manifest.max_calls_per_task
        self.assertIn("activate_skill", budgets)
        self.assertIn("read_skill_reference", budgets)
        self.assertGreater(budgets["activate_skill"], 0)
        self.assertGreater(budgets["read_skill_reference"], 0)


class TestFilterCreatorTools(unittest.TestCase):
    """``_filter_creator_tools`` must keep the creator subset and fail-loud
    when the upstream pool drops ``activate_skill``.

    This is the boot-time guard that catches a profile misconfiguration
    before any Agent is constructed; the model would otherwise only learn
    the missing tool via a runtime ValidationError on its first step.
    """

    @staticmethod
    def _fake_tool(name: str) -> Any:
        # Default-arg trick: class body has no enclosing scope; capture
        # via default arg.
        def _build(tool_name: str = name) -> Any:
            class _Stub:
                pass

            stub = _Stub()
            stub.name = tool_name
            return stub

        return _build()

    def test_keeps_creator_subset_in_input_order(self) -> None:
        from gateway.runs.loop_drivers import _filter_creator_tools

        pool = [
            self._fake_tool("file_write"),
            self._fake_tool("bash"),
            self._fake_tool("activate_skill"),
            self._fake_tool("read_skill_reference"),
            self._fake_tool("web_search"),  # must drop
            self._fake_tool("file_read"),  # must drop
        ]
        filtered = _filter_creator_tools(pool)
        self.assertEqual(
            set(filtered.keys()),
            {"file_write", "bash", "activate_skill", "read_skill_reference"},
        )

    def test_returns_empty_when_input_is_none(self) -> None:
        """Empty pool must raise so misconfiguration is loud."""
        from gateway.runs.loop_drivers import _filter_creator_tools

        with self.assertRaises(RuntimeError) as ctx:
            _filter_creator_tools(None)
        self.assertIn("activate_skill", str(ctx.exception))

    def test_fails_loud_when_activate_skill_missing(self) -> None:
        """Pool without activate_skill is a profile bug; raise clearly."""
        from gateway.runs.loop_drivers import _filter_creator_tools

        pool = [self._fake_tool("file_write"), self._fake_tool("bash")]
        with self.assertRaises(RuntimeError) as ctx:
            _filter_creator_tools(pool)
        msg = str(ctx.exception)
        self.assertIn("activate_skill", msg)
        self.assertIn("PERSONA_GOAL", msg)
        # Should also hint at the diagnostic command, so on-call engineers
        # can resolve without reading the full source.
        self.assertIn("lca-ops", msg)

    def test_fails_loud_when_pool_is_empty_list(self) -> None:
        from gateway.runs.loop_drivers import _filter_creator_tools

        with self.assertRaises(RuntimeError):
            _filter_creator_tools([])


class TestCordisCreatorCapabilityGrantSync(unittest.TestCase):
    """``profiles/cordis-creator.yaml:capability_grant`` must stay in sync
    with ``gateway/runs/loop_drivers.py``'s cordis_control ``caller_grant``.

    Two hand-written lists, six places they could drift apart. This test
    is the single source of truth that catches drift before it hits prod.
    """

    @staticmethod
    def _load_profile_grant() -> set[str]:
        """Read profiles/cordis-creator.yaml capability_grant without yaml dep."""
        from pathlib import Path

        text = Path("profiles/cordis-creator.yaml").read_text(encoding="utf-8")
        # Simple parser: find `capability_grant:` block; collect non-comment
        # list entries until the next top-level key (no leading spaces).
        lines = text.splitlines()
        in_block = False
        grant: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("capability_grant:"):
                in_block = True
                continue
            if in_block:
                # Block ends when we dedent back to no leading whitespace.
                if line and not line.startswith(" "):
                    break
                if stripped.startswith("- "):
                    grant.add(stripped[2:].strip())
        return grant

    @staticmethod
    def _extract_loop_drivers_caller_grant() -> set[str]:
        """Pull the caller_grant tuple literal from loop_drivers.py.

        Targets the ``_build_cordis_creator_agent`` and ``_reinject_cordis_control``
        blocks; both must hold the same set (the helper asserts it).
        """
        import re
        from pathlib import Path

        text = Path("gateway/runs/loop_drivers.py").read_text(encoding="utf-8")
        # Find every tuple literal of the form ``caller_grant=(\n  "a",\n  "b",\n)``
        # and union the strings across all occurrences.
        block_re = re.compile(r"caller_grant=\(\s*((?:\"[^\"]*\",\s*)+)\)", re.DOTALL)
        all_grants: set[str] = set()
        for match in block_re.finditer(text):
            inner = match.group(1)
            for item_match in re.finditer(r"\"([^\"]+)\"", inner):
                all_grants.add(item_match.group(1))
        return all_grants

    def test_profile_capability_grant_matches_loop_drivers_caller_grant(self) -> None:
        """The two hand-written lists must agree; otherwise profile boots
        with a grant the cordis_control tool won't propagate to mounts."""
        profile_grant = self._load_profile_grant()
        loop_drivers_grant = self._extract_loop_drivers_caller_grant()
        self.assertEqual(
            profile_grant,
            loop_drivers_grant,
            f"profiles/cordis-creator.yaml:capability_grant ({profile_grant}) "
            f"!= gateway/runs/loop_drivers.py caller_grant ({loop_drivers_grant}); "
            f"keep them in sync to avoid C5 drift between persona and cordis_control mount.",
        )

    def test_profile_capability_grant_includes_required_keys(self) -> None:
        """Belt-and-braces: document the keys the cordis-creator needs.

        If anyone removes one of these by accident, the sync test above
        also fires — but a dedicated test makes the intent legible.
        """
        grant = self._load_profile_grant()
        required = {
            "cordis_control.inspect",
            "cordis_control.mount",
            "cordis_control.unmount",
            "cordis_control.publish",
            "tool_fs.read",
            "tool_fs.write",
            "tool_bash",
            "file_write",
        }
        missing = required - grant
        self.assertFalse(missing, f"capability_grant missing keys: {missing}")


class _MonkeyPatcher:
    """Minimal subset of pytest's monkeypatch fixture (no external dep)."""

    def __init__(self) -> None:
        self._undo: list[tuple[Any, str, Any]] = []

    def start(self) -> None:
        pass

    def undo(self) -> None:
        import contextlib

        for obj, attr, original in reversed(self._undo):
            with contextlib.suppress(AttributeError, TypeError):
                setattr(obj, attr, original)
        self._undo.clear()

    def setattr(self, obj: Any, attr: str, value: Any) -> None:
        from unittest.mock import patch

        original = getattr(obj, attr, None)
        self._undo.append((obj, attr, original))
        patch.object(obj, attr, value).start()


if __name__ == "__main__":
    unittest.main()
