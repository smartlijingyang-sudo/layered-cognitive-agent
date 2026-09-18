"""Two-scope lookup in ``AssistantMergedSkillStore``.

``get`` / ``read_resource`` / ``resource_files`` all follow one rule: try the
assistant Home scope first, and only if it does not have the skill fall through
to the global store. The global store's own ``SkillNotFoundError`` is the single
authoritative miss — an assistant-scope miss must never surface. The three
methods used to repeat that try/except/fall-through by hand; they now share one
helper, so the behavior is pinned once here.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillNotFoundError
from lca.infrastructure.skills.assistant.merged_store import AssistantMergedSkillStore
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings

_SKILL_MD = "---\nname: {sid}\ndescription: demo\nreferences: []\n---\nbody"


def _store_with(root: Path, *skill_ids: str) -> DiskSkillPackageStore:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=root))
    for sid in skill_ids:
        store.install_package(
            skill_id=sid,
            skill_md_text=_SKILL_MD.format(sid=sid),
            resource_files={"REFERENCE.md": b"ref"},
            source_url="u",
        )
    return store


class _OverlayStub:
    """Only ``list_installed`` is read, to locate the assistant Home skills dir."""

    def __init__(self, install_path: Path) -> None:
        self._receipts = (SimpleNamespace(install_path=str(install_path)),)

    def list_installed(self, assistant_id: str) -> tuple[object, ...]:
        del assistant_id
        return self._receipts


def _merged(tmp_path: Path) -> AssistantMergedSkillStore:
    assistant_home = tmp_path / "home" / "skills"
    _store_with(assistant_home, "assistant-only")
    # ``install_path`` is the installed package directory; the merged store takes
    # its parent as the assistant scope's store root.
    return AssistantMergedSkillStore(
        global_store=_store_with(tmp_path / "global", "global-skill"),
        overlay=_OverlayStub(assistant_home / "assistant-only"),  # type: ignore[arg-type]
        assistant_id="asst",
    )


def test_assistant_scope_hit_wins(tmp_path: Path) -> None:
    merged = _merged(tmp_path)
    assert merged.get("assistant-only").skill_id == "assistant-only"


def test_assistant_scope_miss_falls_back_to_global(tmp_path: Path) -> None:
    merged = _merged(tmp_path)
    assert merged.get("global-skill").skill_id == "global-skill"
    assert merged.read_resource("global-skill", "REFERENCE.md") == "ref"
    # references 用 ``resources/`` 前缀声明；resource_files 返回带前缀的挂载键。
    assert merged.resource_files("global-skill") == {"resources/REFERENCE.md": b"ref"}
    assert merged.read_resource("global-skill", "resources/REFERENCE.md") == "ref"


def test_both_scopes_missing_raises_once(tmp_path: Path) -> None:
    merged = _merged(tmp_path)
    with pytest.raises(SkillNotFoundError):
        merged.get("nobody-has-me")


def test_assistant_scope_resource_falls_back(tmp_path: Path) -> None:
    merged = _merged(tmp_path)
    with pytest.raises(SkillNotFoundError):
        merged.read_resource("assistant-only", "MISSING.md")
