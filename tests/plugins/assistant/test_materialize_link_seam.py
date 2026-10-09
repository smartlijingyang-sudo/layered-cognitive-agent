"""RA-059: hardlink materialization is a first-class ``SkillPackageStore`` seam.

Guards:
- ``DiskSkillPackageStore.materialize_link`` hardlinks the pack into ``dest``,
  replaces an existing ``dest``, and raises ``SkillNotFoundError`` for a
  missing/incomplete pack.
- The Protocol default raises ``NotImplementedError`` (read-only views such as
  the merged store opt out — same pattern as ``update_package_meta``).
- ``_list_materializable_global_skills`` works against a store WITHOUT a
  ``root`` attribute: the ``getattr(store, "root", None)`` backdoor is gone.
- ``_materialize_global_skills`` translates ``NotImplementedError`` into
  ``_CatalogConfigError`` (capability downgrade preserved).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lca.contracts.protocols.memory.operational_skills import (
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.plugins.domain.assistant.catalog.handlers import (
    _CatalogConfigError,
    _list_materializable_global_skills,
    _materialize_global_skills,
)

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


class _BareStore(SkillPackageStore):
    """Inherits the Protocol default ``materialize_link`` (read-only view)."""


def test_materialize_link_hardlinks_pack(tmp_path: Path) -> None:
    store = _store_with(tmp_path / "global", "demo-skill")
    dest = store.materialize_link("demo-skill", tmp_path / "home" / "skills" / "demo-skill")

    assert dest.is_dir()
    assert (dest / "SKILL.md").is_file()
    assert (dest / "manifest.json").is_file()
    src_file = tmp_path / "global" / "demo-skill" / "SKILL.md"
    assert os.path.samefile(src_file, dest / "SKILL.md"), "must be a hardlink, not a copy"


def test_materialize_link_replaces_existing_dest(tmp_path: Path) -> None:
    store = _store_with(tmp_path / "global", "demo-skill")
    dest = tmp_path / "skills" / "demo-skill"
    dest.mkdir(parents=True)
    (dest / "STALE.txt").write_text("stale", encoding="utf-8")

    out = store.materialize_link("demo-skill", dest)

    assert out == dest
    assert not (dest / "STALE.txt").exists()
    assert (dest / "SKILL.md").is_file()


def test_materialize_link_missing_pack_raises_not_found(tmp_path: Path) -> None:
    store = _store_with(tmp_path / "global", "demo-skill")
    with pytest.raises(SkillNotFoundError):
        store.materialize_link("nope", tmp_path / "dest")


def test_protocol_default_materialize_link_raises_not_implemented(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError):
        _BareStore().materialize_link("demo-skill", tmp_path / "dest")


class _RootlessFakeStore:
    """A store with no ``root`` attribute at all — the old getattr backdoor
    would have returned () / raised here."""

    def __init__(self, complete: tuple[str, ...], incomplete: tuple[str, ...]) -> None:
        self._complete = complete
        self._incomplete = incomplete

    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        return tuple(
            SkillIndexEntry(
                skill_id=sid, name=sid, summary="", source_url="", version=""
            )
            for sid in (*self._complete, *self._incomplete)
        )

    def get(self, skill_id: str) -> SkillPackage:
        if skill_id in self._complete:
            return SkillPackage(
                skill_id=skill_id,
                name=skill_id,
                summary="",
                content="body",
                resource_paths=(),
                source_url="",
                content_hash="",
            )
        raise SkillNotFoundError(f"技能库中不存在 skill_id：{skill_id}")


def test_list_materializable_needs_no_root_attribute() -> None:
    store = _RootlessFakeStore(complete=("a", "b"), incomplete=("broken",))
    assert not hasattr(store, "root")
    assert _list_materializable_global_skills(store) == ("a", "b")


def test_materialize_global_skills_translates_missing_capability(tmp_path: Path) -> None:
    class _NoLinkStore(_BareStore):
        pass

    with pytest.raises(_CatalogConfigError, match="materialize_link"):
        _materialize_global_skills(
            _NoLinkStore(), tmp_path / "home", ("demo-skill",), "2026-10-09T00:00:00Z"
        )
