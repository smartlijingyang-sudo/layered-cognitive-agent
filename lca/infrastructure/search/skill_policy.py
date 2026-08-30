"""Skill discovery exclusions when Unified Search Plane owns realtime search (ADR-0053).

LobeHub native search uses ``lobe-web-browsing`` / MCP Tavily — not Market CLI skills.
When LCA ``web_search`` (+ Tavily REST) is available, hide redundant Tavily CLI skills
from ``search_skill`` / ``activate_skill`` so agents stay on the builtin wire.
"""

from __future__ import annotations

from lca.contracts.protocols.operational_skills import SkillSearchResult

# Market ids like ``tavily-ai-skills-tavily-search`` — CLI guides, not LCA search plane.
_CLI_SEARCH_SKILL_ID_MARKERS: tuple[str, ...] = ("tavily",)


def is_redundant_cli_search_skill(*, skill_id: str, name: str = "") -> bool:
    """True when skill is a Tavily CLI/search Market pack superseded by ``web_search``."""
    sid = (skill_id or "").lower()
    label = (name or "").lower()
    if not any(marker in sid for marker in _CLI_SEARCH_SKILL_ID_MARKERS):
        return False
    return "search" in sid or "search" in label or "tavily" in label


def filter_skill_search_result(
    result: SkillSearchResult,
    *,
    unified_search_available: bool,
) -> SkillSearchResult:
    """Drop CLI search skills from market/local discovery when ``web_search`` is ready."""
    if not unified_search_available:
        return result
    kept = tuple(
        item
        for item in result.items
        if not is_redundant_cli_search_skill(skill_id=item.skill_id, name=item.name)
    )
    if kept == result.items:
        return result
    return SkillSearchResult(
        items=kept,
        total=len(kept),
        page=result.page,
        page_size=result.page_size,
    )
