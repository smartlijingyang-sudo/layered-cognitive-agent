"""``DiskSkillPackageStore.install_package`` must keep declared references inside
the installed package directory.

SKILL.md declares ``references:`` entries; the store resolves each one under its
own package dir and rejects anything that escapes (ADR-0214 §7). The rejection
used to be expressed as ``Path.relative_to`` raising ``ValueError`` and being
translated; it is now ``Path.is_relative_to``. Either way the guard is the only
thing stopping a skill package from reading or naming a file outside its own
directory, so both the accepted and the rejected shape are pinned here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillContractError
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings


def _install(store: DiskSkillPackageStore, *, references: str, files: dict[str, bytes]) -> object:
    return store.install_package(
        skill_id="ref-guard",
        skill_md_text=f"---\nname: ref-guard\ndescription: d\nreferences: {references}\n---\nbody",
        resource_files=files,
        source_url="u",
    )


def test_in_package_reference_is_accepted(tmp_path: Path) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))

    package = _install(
        store,
        references="[resources/REFERENCE.md]",
        files={"REFERENCE.md": b"# ref\n"},
    )

    assert package.skill_id == "ref-guard"
    assert (tmp_path / "root" / "ref-guard" / "resources" / "REFERENCE.md").is_file()


@pytest.mark.parametrize("escaping", ["../outside.md", "resources/../../outside.md", "/etc/passwd"])
def test_reference_escaping_the_package_is_rejected(tmp_path: Path, escaping: str) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))

    with pytest.raises(SkillContractError, match="越界"):
        _install(store, references=f"[{escaping}]", files={"REFERENCE.md": b"x"})
