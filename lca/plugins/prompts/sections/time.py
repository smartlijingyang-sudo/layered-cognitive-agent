"""Current-date section with locale-aware weekday localisation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import clock_from_manifest, label_line
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool

# 英文星期 → 本地化星期（ADR-0242 D9/PR-8）。新增 locale 在此扩展；
# 未知 locale 回退当前英文行为，不新增 prompt section。
_WEEKDAY_LOCALIZATIONS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "Monday": "星期一",
        "Tuesday": "星期二",
        "Wednesday": "星期三",
        "Thursday": "星期四",
        "Friday": "星期五",
        "Saturday": "星期六",
        "Sunday": "星期日",
    },
}


def _localize_clock_text(text: str, locale: str) -> str:
    """把 ``clock`` payload 的英文星期按 locale 翻译；未知 locale 原样返回。"""
    mapping = _WEEKDAY_LOCALIZATIONS.get(locale)
    if not mapping:
        return text
    parts = text.split()
    if not parts:
        return text
    weekday = mapping.get(parts[-1])
    if weekday is None:
        return text
    return " ".join([*parts[:-1], weekday])


class CurrentDateSection:
    name: ClassVar[str] = "current_date"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del role_profile, task, awareness, tools, activated_skills
        clock = clock_from_manifest(manifest)
        if clock is None:
            # An absent CURRENT_DATE line is indistinguishable from "no clock
            # was ever wired", and a model with no date anchor answers from its
            # training cutoff. State the gap instead of hiding it.
            return SectionOutput(
                text=label_line("CURRENT_DATE", "(未知当前时间)"), used_fallback=True
            )
        locale = (manifest.extra.get("locale") if manifest is not None else "") or ""
        text = _localize_clock_text(clock.text, locale) if locale else clock.text
        return SectionOutput(text=label_line("CURRENT_DATE", text))


def build_current_date(config: BaseModel) -> CurrentDateSection:
    del config
    return CurrentDateSection()


__all__ = ["CurrentDateSection", "build_current_date"]
