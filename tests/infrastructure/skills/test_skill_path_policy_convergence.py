"""RA-076: store 与 gate 的 traversal-safety 策略收敛到同一谓词。

同一输入在两条路径下必须得到同一策略结果（都接受或都拒绝），
且 ``require_canonical_rel_path`` 对非 canonical 输入 fail-loud ——
store 不再静默归一化/跳过。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.memory.operational_skills import (
    SkillContractError,
    SkillImportError,
    SkillPackage,
)
from lca.infrastructure.skills.disk.store import (
    DiskSkillPackageStore,
    is_canonical_rel_path,
    require_canonical_rel_path,
)
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.plugins.assistant.skill.overlay.gating import _gate_package


_CANONICAL = ["REFERENCE.md", "resources/REFERENCE.md", "a/b/c.txt"]
_NON_CANONICAL = [
    "",
    "../outside.md",
    "a/../b.md",
    "a/./b.md",
    "a//b.md",
    "a\\b.md",
    "/abs.md",
    "./rel.md",
]


def _valid_package_with(resource_paths: tuple[str, ...]) -> SkillPackage:
    return SkillPackage(
        skill_id="policy-pin",
        name="policy-pin",
        summary="",
        content="body",
        resource_paths=resource_paths,
        source_url="u",
        content_hash="abc",
    )


def _gate_accepts(rel: str) -> bool:
    try:
        _gate_package(_valid_package_with((rel,)))
    except SkillImportError:
        return False
    return True


@pytest.mark.parametrize("rel", _CANONICAL)
def test_converged_predicate_accepts_canonical(rel: str) -> None:
    assert is_canonical_rel_path(rel) is True
    assert _gate_accepts(rel) is True


@pytest.mark.parametrize("rel", _NON_CANONICAL)
def test_converged_predicate_rejects_non_canonical(rel: str) -> None:
    assert is_canonical_rel_path(rel) is False
    assert _gate_accepts(rel) is False


@pytest.mark.parametrize("rel", _NON_CANONICAL)
def test_store_install_rejects_non_canonical_key_fail_loud(
    tmp_path: Path, rel: str
) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))
    with pytest.raises(SkillContractError):
        store.install_package(
            skill_id="policy-pin",
            skill_md_text="---\nname: policy-pin\ndescription: d\nreferences: []\n---\nbody",
            resource_files={rel: b"data"},
            source_url="u",
        )


@pytest.mark.parametrize("rel", _NON_CANONICAL)
def test_store_read_resource_rejects_non_canonical_fail_loud(
    tmp_path: Path, rel: str
) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))
    store.install_package(
        skill_id="policy-pin",
        skill_md_text="---\nname: policy-pin\ndescription: d\nreferences: []\n---\nbody",
        resource_files={"REFERENCE.md": b"data"},
        source_url="u",
    )
    with pytest.raises(SkillContractError):
        store.read_resource("policy-pin", rel)


def test_require_canonical_rel_path_returns_input_unchanged() -> None:
    assert require_canonical_rel_path("resources/a.txt") == "resources/a.txt"
