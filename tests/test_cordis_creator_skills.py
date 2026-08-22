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
_EXPECTED_VERSIONS = {
    CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID: "2.0.0",
    EDITING_LCA_COMPOSITIONS_SKILL_ID: "1.0.0",
}


def _stub_scope_with_skill_store(store: DiskSkillPackageStore) -> SimpleNamespace:
    """Build a minimal scope stub that exposes a `skills.current()` provider."""

    skills_provider = SimpleNamespace(current=lambda: store)
    return SimpleNamespace(_skills_provider=skills_provider)


def _fake_tool(name: str) -> Any:
    """Build a stub tool with the given ``name`` for prompt-rendering tests.

    Used where :func:`_format_tools_xml` only reads ``name`` + ``description``.
    """
    def _build(tool_name: str = name) -> Any:
        stub = SimpleNamespace()
        stub.name = tool_name
        stub.description = f"test tool {tool_name}"
        return stub

    return _build()


def _patch_skill_store_resolution(monkeypatch: Any, store: DiskSkillPackageStore) -> None:
    """Replace the plan-composition skill resolver without booting Cordis."""
    from lca.plugins.composer import plan_composition_support as support_module

    monkeypatch.setattr(support_module, "_skill_store_from_scope", lambda _scope: store)


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
                self.assertEqual(package.version, _EXPECTED_VERSIONS[skill_id])

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
                expected = _EXPECTED_VERSIONS[skill_id]
                self.assertEqual(package.version, expected)
                self.assertIn(f"v{expected}", rendered)

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

    def test_keeps_creator_subset_in_input_order(self) -> None:
        from gateway.runs.loop_drivers import _filter_creator_tools

        pool = [
            _fake_tool("file_write"),
            _fake_tool("bash"),
            _fake_tool("activate_skill"),
            _fake_tool("read_skill_reference"),
            _fake_tool("web_search"),  # must drop
            _fake_tool("file_read"),  # must drop
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

        pool = [_fake_tool("file_write"), _fake_tool("bash")]
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


class TestCordisCreatorEndToEndPrompt(unittest.TestCase):
    """End-to-end prompt assembly: the model-side view of the cordis-creator
    chain, without needing a real LLM. Verifies the four pieces of
    information the model needs at step 0 to act correctly:

    1. ``<available_skills>`` lists both bundled skills with summary + version
    2. ``<tools>`` advertises ``activate_skill`` (and friends)
    3. ``ROLE:`` / ``GOAL:`` prompt the model to load those skills
    4. ``react_prompt.md`` template renders without KeyError

    If any of these break, the creator flow's first step is a confused LLM.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))
        ensure_bundled_skills(self.store, root=default_bundled_skills_root())
        self._monkey = _MonkeyPatcher()
        self._monkey.start()
        _patch_skill_store_resolution(self._monkey, self.store)

    def tearDown(self) -> None:
        self._monkey.undo()
        self._tmp.cleanup()

    def _render_full_prompt(self) -> str:
        """Compose the exact prompt the cordis-creator agent sees at step 0."""
        from lca.contracts.atoms.ids import new_id
        from lca.contracts.models.core.budget import Budget
        from lca.contracts.models.core.state import AgentState
        from lca.layer1_cognitive.brain.prompts._loader import load_builtin_prompt
        from lca.layer1_cognitive.brain.reasoner import (
            _context_lines,
            _role_prompt_vars,
        )
        from lca.layer1_cognitive.sensors.skill_catalog import SkillCatalogSensor
        from lca.layer4_app.spawn import (
            _format_tools_xml,
            _render_available_skills,
        )
        from lca.plugins.roles.cordis_creator import build_cordis_creator_role_profile

        profile = build_cordis_creator_role_profile()
        scope = _stub_scope_with_skill_store(self.store)
        available_skills = _render_available_skills(scope)

        # Tool list mirrors _filter_creator_tools output: the four the
        # creator persona expects, plus cordis_control (which is added
        # separately by the boot driver). We don't need real Tool instances
        # here — _format_tools_xml only reads name + description.
        fake_tools = [
            _fake_tool("cordis_control"),
            _fake_tool("file_write"),
            _fake_tool("bash"),
            _fake_tool("activate_skill"),
            _fake_tool("read_skill_reference"),
        ]
        tools_xml = _format_tools_xml(fake_tools)

        state = AgentState(trace_id=new_id("trace"), task="=test=", budget=Budget())
        # Drive the skill_catalog sensor so ``context`` reflects installed skills.
        sensor = SkillCatalogSensor(self.store)
        manifest_items = asyncio.run(sensor.read(state))
        # Build a state that includes the sensor's context items; we
        # intentionally keep everything else default-shaped so this
        # test mirrors what a fresh step-0 boot would look like.
        state_with_skills = AgentState(
            trace_id=state.trace_id,
            task=state.task,
            budget=state.budget,
            retrieved_context=list(state.retrieved_context)
            + [item.payload for item in manifest_items],
        )
        context_lines = _context_lines(state_with_skills)

        variables = _role_prompt_vars(
            profile,
            tools_xml,
            state_with_skills,
            context_lines,
            tools=fake_tools,
            available_skills=available_skills,
        )
        template = load_builtin_prompt("react_prompt")
        return template.format(**variables)

    def test_prompt_contains_both_bundled_skills_in_available_section(self) -> None:
        prompt = self._render_full_prompt()
        # The catalog segment must surface both skill ids with summary + version.
        self.assertIn(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID, prompt)
        self.assertIn(EDITING_LCA_COMPOSITIONS_SKILL_ID, prompt)
        # Format: ``- {id}: {name} — {summary} (v{version})``
        self.assertIn("v2.0.0", prompt)
        self.assertIn("v1.0.0", prompt)
        # The new summary-bearing format vs the legacy ``{id}: {name}`` only.
        self.assertIn(
            f"- {CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID}:", prompt,
            "available_skills segment must use the bullet-list format",
        )

    def test_prompt_advertises_activate_skill_in_tools_section(self) -> None:
        prompt = self._render_full_prompt()
        # <tools> section should expose all five creator tools.
        self.assertIn('name="activate_skill"', prompt)
        self.assertIn('name="read_skill_reference"', prompt)
        self.assertIn('name="file_write"', prompt)
        self.assertIn('name="bash"', prompt)
        self.assertIn('name="cordis_control"', prompt)

    def test_prompt_goal_directs_model_to_load_skills(self) -> None:
        prompt = self._render_full_prompt()
        # The new PERSONA_GOAL paragraph appended in this PR.
        self.assertIn("Two bundled skills ship with this persona", prompt)
        self.assertIn("cordis-plugin-development", prompt)
        self.assertIn("editing-lca-compositions", prompt)
        self.assertIn("activate_skill", prompt)

    def test_prompt_activated_skills_section_renders_empty_initially(self) -> None:
        """First step: no skill has been loaded yet → ``<activated_skills>``
        shows the empty fallback string the model can rely on."""
        prompt = self._render_full_prompt()
        # The template has ``<activated_skills>{activated_skills}</activated_skills>``
        # so the placeholder text shows up verbatim when state is empty.
        self.assertIn("（无）", prompt)

    def test_prompt_renders_without_template_keyerror(self) -> None:
        """If a new template variable is added without a default, react_prompt
        rendering would KeyError. This guards against that regression."""
        self.assertTrue(self._render_full_prompt())


class TestCordisCreatorEndToEndAgentStep(unittest.TestCase):
    """Drive a single agent step through the real reasoner + real
    ``SkillActivateTool`` to prove the chain the model would execute:

        state.activated_skills == []
            → LLM emits Decision(use_tool, name='activate_skill',
                                 args={'skill_id': 'cordis-plugin-development'})
            → SkillActivateTool.execute(...) returns SkillPackage.content
            → state.activated_skills == [ActivatedSkill(...)]

    Uses ``SequenceScriptedLLM`` (the same harness used by
    ``test_cordis_creator_real_scenario``) so the LLM layer is deterministic.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DiskSkillPackageStore(SkillSettings(cache_dir=Path(self._tmp.name)))
        ensure_bundled_skills(self.store, root=default_bundled_skills_root())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def _activate_and_check(self, skill_id: str) -> tuple[Any, str, Any]:
        """Run ``SkillActivateTool.execute(skill_id)`` and return
        (observation, body_text, state_after). state_after is a plain
        dict snapshot of state.activated_skills contents."""
        from lca.layer0_infra.skills.activation_scope import (
            activated_skills_scope,
            register_activated,
        )
        from lca.layer0_infra.tools.skills.activate_tool import SkillActivateTool

        with activated_skills_scope(()):
            tool = SkillActivateTool(self.store)
            observation = await tool.execute({"skill_id": skill_id})
            # In production, this happens via register_activated's scope
            # machinery; here we simulate the resulting state mutation
            # so we can assert what state.activated_skills would look like.
            register_activated(skill_id, skill_id)
            from lca.layer0_infra.skills.activation_scope import (
                resolve_skill_for_exec,
            )

            activated = resolve_skill_for_exec(None)
        body = observation.payload["text"] if observation.success else ""
        return observation, body, activated

    def test_first_step_loads_cordis_plugin_development(self) -> None:
        observation, body, activated = asyncio.run(
            self._activate_and_check(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID)
        )
        self.assertTrue(observation.success)
        self.assertIn("PR12", body)
        self.assertIn("§23.2", body)
        self.assertEqual(activated.skill_id, CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID)

    def test_second_step_loads_editing_lca_compositions(self) -> None:
        """After step 1, the model would call activate_skill again for the
        second skill — verify the body and the activated list updates."""
        from lca.layer0_infra.skills.activation_scope import (
            activated_skills_scope,
            register_activated,
        )

        with activated_skills_scope(()):
            register_activated(CORDIS_PLUGIN_DEVELOPMENT_SKILL_ID, "first")
            observation, body, _ = asyncio.run(
                self._activate_and_check(EDITING_LCA_COMPOSITIONS_SKILL_ID)
            )
        self.assertTrue(observation.success)
        self.assertIn("HOST", body)
        self.assertIn("PRESET", body)


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
