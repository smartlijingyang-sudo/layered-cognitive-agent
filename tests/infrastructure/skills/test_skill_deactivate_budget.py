"""deactivateSkill + per-run activation budget tests.

- unregister_activated removes from the run-scoped set and is idempotent.
- deactivate_skill tool clears activation; afterwards run_skill_script's
  resolve_skill_for_exec rejects the skill.
- The 9th concurrent activation is rejected with a clear error; deactivating
  one frees the budget.
- Bridge folds deactivation into state.activated_skills; the prompt assembler
  section no longer renders the deactivated skill.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from lca.cognition.brain.sections.types import render_activated_skills
from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.memory.operational_skills import (
    SkillNotFoundError,
    SkillPackage,
)
from lca.infrastructure.skills.activation.bridge import bridge as global_bridge
from lca.infrastructure.skills.activation.scope import (
    MAX_ACTIVATED_SKILLS_PER_RUN,
    activated_skills_scope,
    can_activate,
    get_activated_skills,
    register_activated,
    resolve_skill_for_exec,
    unregister_activated,
)
from lca.infrastructure.tools.skills.manifest.manifest import MANIFEST
from lca.plugins.loop.reducer.plugin import DefaultReducer


@pytest.fixture
def package() -> SkillPackage:
    return SkillPackage(
        skill_id="demo-skill",
        name="Demo",
        content="---\nname: demo\n---\n# Demo",
        summary="demo",
        version="1",
        content_hash="sha256:demo",
        resource_paths=(),
        source_url="",
    )


class _Store:
    def __init__(self, package: SkillPackage) -> None:
        self._package = package

    def get(self, skill_id: str) -> SkillPackage:
        if skill_id in (self._package.skill_id, self._package.name):
            return self._package
        raise SkillNotFoundError(skill_id)

    def list_installed(self) -> tuple:
        return ()


def _activate_tool(package: SkillPackage):
    from lca.infrastructure.tools.skills.activate.tool import SkillActivateTool

    return SkillActivateTool(_Store(package))


def _deactivate_tool(package: SkillPackage):
    from lca.infrastructure.tools.skills.deactivate.tool import SkillDeactivateTool

    return SkillDeactivateTool(_Store(package))


def test_unregister_activated_removes_and_is_idempotent() -> None:
    with activated_skills_scope(()):
        register_activated("s1", "S1")
        register_activated("s2", "S2")
        assert unregister_activated("s1") is True
        assert [s.skill_id for s in get_activated_skills()] == ["s2"]
        assert unregister_activated("s1") is False
        assert unregister_activated("never-there") is False


def test_deactivate_tool_clears_activation_and_blocks_exec(package: SkillPackage) -> None:
    # NOTE: tool execute() runs inside asyncio.run, which copies the context;
    # ContextVar writes are only visible inside the same async context, so the
    # whole scenario (activate -> assert -> deactivate -> assert) must live in
    # one coroutine.
    async def scenario() -> None:
        with patch(
            "lca.infrastructure.observability.meta_event_emit.emit_skill_activated",
        ):
            obs = await _activate_tool(package).execute({"skill_id": "demo-skill"})
        assert obs.success is True
        assert resolve_skill_for_exec("demo-skill").skill_id == "demo-skill"

        obs = await _deactivate_tool(package).execute({"skill_id": "demo-skill"})
        assert obs.success is True
        assert obs.payload["was_active"] is True

        with pytest.raises(SkillNotFoundError):
            resolve_skill_for_exec("demo-skill")

        # idempotent second call
        obs = await _deactivate_tool(package).execute({"skill_id": "demo-skill"})
        assert obs.success is True
        assert obs.payload["was_active"] is False

    with activated_skills_scope(()):
        asyncio.run(scenario())


def test_activation_budget_rejects_ninth(package: SkillPackage) -> None:
    assert MAX_ACTIVATED_SKILLS_PER_RUN == 8
    with activated_skills_scope(()):
        for i in range(MAX_ACTIVATED_SKILLS_PER_RUN):
            register_activated(f"s{i}", f"S{i}")
        assert can_activate("s0") is True, "re-activation must not consume budget"
        assert can_activate("s8") is False

        with patch(
            "lca.infrastructure.observability.meta_event_emit.emit_skill_activated",
        ):
            obs = asyncio.run(_activate_tool(package).execute({"skill_id": "demo-skill"}))
        assert obs.success is False
        assert "deactivate_skill" in (obs.error or "")

        assert unregister_activated("s0") is True
        with patch(
            "lca.infrastructure.observability.meta_event_emit.emit_skill_activated",
        ):
            obs = asyncio.run(_activate_tool(package).execute({"skill_id": "demo-skill"}))
        assert obs.success is True


def test_bridge_folds_deactivation_into_state() -> None:
    state = AgentState(trace_id="t_deact", task="x", budget=Budget())
    reducer = DefaultReducer()
    global_bridge.install(reducer=reducer, state_getter=lambda: state)
    try:
        with activated_skills_scope(()):
            register_activated("pdf", "PDF")
            register_activated("office", "Office")
            assert {s.skill_id for s in state.activated_skills} == {"pdf", "office"}
            assert unregister_activated("pdf") is True
            assert [s.skill_id for s in state.activated_skills] == ["office"]
    finally:
        global_bridge.dispose()


def test_prompt_render_excludes_deactivated_skill() -> None:
    with activated_skills_scope(()):
        register_activated("pdf", "PDF")
        register_activated("office", "Office")
        assert "PDF" in render_activated_skills(get_activated_skills())
        unregister_activated("pdf")
        rendered = render_activated_skills(get_activated_skills())
        assert "PDF" not in rendered
        assert "Office" in rendered


def test_manifest_advertises_deactivate_skill() -> None:
    names = [api.name for api in MANIFEST.api]
    assert "deactivateSkill" in names
    assert "activateSkill" in names
