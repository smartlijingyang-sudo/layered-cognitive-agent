"""Home-only lookup in ``AssistantMergedSkillStore`` (ADR-0243 D1/I-B16).

``get`` / ``read_resource`` / ``resource_files`` 全部经 ``_lookup`` 只查
assistant Home 范围（``{home}/skills/`` 是完整有效技能集）；全局
``~/.lca/skills/`` 只是创建时硬链接物化的内容源，不再是运行时兜底层——
assistant-scope miss 即抛 ``SkillNotFoundError``，绝不 fall through 到全局。
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


def test_both_scopes_missing_raises_once(tmp_path: Path) -> None:
    merged = _merged(tmp_path)
    with pytest.raises(SkillNotFoundError):
        merged.get("nobody-has-me")


def test_assistant_scope_resource_falls_back(tmp_path: Path) -> None:
    merged = _merged(tmp_path)
    with pytest.raises(SkillNotFoundError):
        merged.read_resource("assistant-only", "MISSING.md")
