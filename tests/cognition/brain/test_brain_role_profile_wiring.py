"""The composed Brain must carry the role profile its render node reads.

``think.reason.render`` builds each turn's ``RoleSnapshot`` from
``context.runtime.brain.role_profile``. The standard factory used to
discard the profile it was handed, so the render node's dependency guard
tripped and it returned empty ports — every request of
``run_71456ce99914`` went out with ``system=""``: no identity, no rules,
no tool policy. The run looked healthy; only the recorded headers showed
the model was promptless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.cognition.brain.pipeline.default_factory import SimpleBrainFactory
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest


@dataclass
class _Reasoner:
    llm: Any
    selector: Any = None
    template_provider: Any = None
    section_registry: Any = None


class _ThinkPipeline:
    async def decide(self, **kwargs: Any) -> Any:
        raise NotImplementedError


class _ReflectionPipeline:
    async def reflect(self, **kwargs: Any) -> Any:
        raise NotImplementedError


def _profile() -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="帮助用户完成日常任务",
        backstory="我是 LobeHub 助手.",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _factory() -> SimpleBrainFactory:
    return SimpleBrainFactory(
        classifier=object(),  # type: ignore[arg-type]
        critic_factory=lambda: object(),
        reasoner_cls=_Reasoner,  # type: ignore[arg-type]
        think_pipeline=_ThinkPipeline(),  # type: ignore[arg-type]
        reflection_pipeline=_ReflectionPipeline(),  # type: ignore[arg-type]
    )


def test_brain_carries_the_role_profile_it_was_composed_with() -> None:
    profile = _profile()
    brain = _factory()(object(), profile, object(), tools=[], template_provider=None)

    assert brain.role_profile is profile


def test_reason_render_resolves_role_profile_from_the_composed_brain() -> None:
    """Close the loop the render node actually walks: runtime → brain → profile."""
    from lca.nodes.think.reason.render import _resolve_role_profile

    profile = _profile()
    brain = _factory()(object(), profile, object(), tools=[], template_provider=None)

    @dataclass
    class _Runtime:
        brain: Any

    assert _resolve_role_profile(_Runtime(brain=brain)) is profile
