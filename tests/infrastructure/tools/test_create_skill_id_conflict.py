"""``create_assistant_skill`` must not silently drop a conflicting ``skill_id``.

The tool takes an optional ``skill_id``, while the installer names the package
from SKILL.md's frontmatter ``name:``. When the two disagreed the tool computed a
sanitized id, never used it, and installed under the frontmatter name — so the
caller got a success receipt for a skill id it did not ask for.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.infrastructure.tools.assistant.create_skill_tool import AssistantCreateSkillTool

_SKILL_MD = "---\nname: flight-booker\ndescription: d\nreferences: []\n---\nbody"


class _NeverInstalledOverlay:
    async def install(self, assistant_id: str, source: object, *, actor: str) -> object:
        raise AssertionError(
            "install must not be reached when the requested skill_id conflicts "
            "with the frontmatter name"
        )


def _tool() -> AssistantCreateSkillTool:
    return AssistantCreateSkillTool(
        overlay=_NeverInstalledOverlay(),  # type: ignore[arg-type]
        assistant_id="asst-1",
    )


@pytest.mark.asyncio
async def test_conflicting_skill_id_fails_without_installing() -> None:
    obs = await _tool().execute({"skill_md": _SKILL_MD, "skill_id": "hotel-search"})

    assert obs.success is False
    assert "hotel-search" in (obs.error or "")
    assert "flight-booker" in (obs.error or "")


@pytest.mark.asyncio
async def test_agreeing_skill_id_is_accepted(tmp_path: Path) -> None:
    class _Overlay:
        def __init__(self) -> None:
            self.calls = 0

        async def install(self, assistant_id: str, source: object, *, actor: str) -> object:
            self.calls += 1
            return SimpleNamespace(skill_id="flight-booker", install_path=str(tmp_path))

    overlay = _Overlay()
    tool = AssistantCreateSkillTool(overlay=overlay, assistant_id="asst-1")  # type: ignore[arg-type]

    obs = await tool.execute({"skill_md": _SKILL_MD, "skill_id": "flight-booker"})

    assert overlay.calls == 1
    assert obs.success is True
    assert obs.payload["skill_id"] == "flight-booker"


@pytest.mark.asyncio
async def test_missing_skill_id_still_derives_from_frontmatter(tmp_path: Path) -> None:
    class _Overlay:
        async def install(self, assistant_id: str, source: object, *, actor: str) -> object:
            return SimpleNamespace(skill_id="flight-booker", install_path=str(tmp_path))

    tool = AssistantCreateSkillTool(overlay=_Overlay(), assistant_id="asst-1")  # type: ignore[arg-type]

    obs = await tool.execute({"skill_md": _SKILL_MD})

    assert obs.success is True
