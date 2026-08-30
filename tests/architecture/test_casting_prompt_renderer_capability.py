"""Substitution gates for the Team-casting prompt content policy."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.capabilities import TEAM_CASTER, TEAM_CASTING_PROMPT_RENDERER
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.protocols.collaboration.casting import RoleCard, RoleIndexEntry, RoleNotFoundError
from lca.harness.profile.resolve import resolve_profile
from lca.application.casting import LLMTeamCaster
from tests.harness.scripted_llm import ScriptedLLMAdapter

REPO = Path(__file__).resolve().parents[2]


class _Library:
    def index(self) -> tuple[RoleIndexEntry, ...]:
        return (
            RoleIndexEntry("product/pm", "产品经理", "product", "规划任务"),
            RoleIndexEntry("strategy/lead", "负责人", "strategy", "统筹任务"),
        )

    def get(self, role_id: str) -> RoleCard:
        entries = {
            "product/pm": RoleCard("product/pm", "产品经理", "product", "规划任务", "负责需求"),
            "strategy/lead": RoleCard(
                "strategy/lead", "负责人", "strategy", "统筹任务", "负责统筹"
            ),
        }
        try:
            return entries[role_id]
        except KeyError as exc:
            raise RoleNotFoundError(role_id) from exc


class _Renderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[RoleIndexEntry, ...]]] = []

    def render(self, objective: str, index: tuple[RoleIndexEntry, ...]) -> str:
        self.calls.append((objective, index))
        return "ROLE: caster\nCUSTOM-CASTING-PROMPT"


async def test_team_caster_uses_the_injected_prompt_renderer() -> None:
    """A replacement renderer changes casting content without replacing policy logic."""

    renderer = _Renderer()
    llm = ScriptedLLMAdapter(
        {
            "caster": [
                LLMResponse(
                    text=(
                        '{"selected":[{"role_id":"strategy/lead"},{"role_id":"product/pm"}],'
                        '"governance":{"kind":"board","lead_role_id":"strategy/lead"}}'
                    ),
                    model="scripted",
                )
            ]
        },
        default_respond=False,
    )

    plan = await LLMTeamCaster(renderer).cast("制定方案", _Library(), llm)

    assert plan.governance_kind == "board"
    assert renderer.calls == [("制定方案", _Library().index())]


def test_default_team_caster_declares_renderer_dependency() -> None:
    """The selected caster receives content policy from the resolved profile graph."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    by_id = {plugin.id: plugin.definition for plugin in resolved.plugins}

    assert (
        TEAM_CASTING_PROMPT_RENDERER.key
        in by_id["lca-team-caster-default"].required_capability_keys
    )
    assert (
        TEAM_CASTING_PROMPT_RENDERER.key
        in by_id["lca-team-casting-prompt-renderer-builtin"].provided_capability_keys
    )
    assert TEAM_CASTER.key in by_id["lca-team-caster-default"].provided_capability_keys


def test_caster_has_no_direct_builtin_prompt_dependency() -> None:
    """Only the renderer plugin may select the built-in casting prompt resource."""

    source = (REPO / "lca/application/casting.py").read_text(encoding="utf-8")
    assert "load_builtin_prompt" not in source
