"""RA-080: 三处技能源目录 walk 收敛到 ``disk/store.py`` 的唯一接缝。

接缝语义: ``rglob(walk_root)`` 下所有文件 -> ``{rel: bytes}``；
``rel`` 相对 ``rel_root``（缺省 ``walk_root``）；``skip_paths`` 命中跳过；
非 canonical 的 rel 按 RA-076 策略 fail-loud（``require_canonical_rel_path``），
不再静默归一化。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillContractError
from lca.infrastructure.skills.disk.store import walk_skill_source_files


def _tree(root: Path) -> None:
    (root / "SKILL.md").write_text("---\nname: x\n---\nbody", encoding="utf-8")
    (root / "resources").mkdir()
    (root / "resources" / "a.txt").write_bytes(b"a")
    (root / "resources" / "sub").mkdir()
    (root / "resources" / "sub" / "b.txt").write_bytes(b"b")


def test_flat_walk_matches_bundled_shape(tmp_path: Path) -> None:
    """bundled 形状: walk resources_dir 本体，rel 不带前缀。"""
    res = tmp_path / "resources"
    (res / "sub").mkdir(parents=True)
    (res / "a.txt").write_bytes(b"a")
    (res / "sub" / "b.txt").write_bytes(b"b")
    out = walk_skill_source_files(res)
    assert out == {"a.txt": b"a", "sub/b.txt": b"b"}
    assert list(out) == sorted(out)  # 确定性顺序


def test_rel_root_prefix_shape_matches_stage_edited(tmp_path: Path) -> None:
    """_stage_edited_package 形状: walk resources 子目录，rel 带 resources/ 前缀。"""
    _tree(tmp_path)
    out = walk_skill_source_files(tmp_path / "resources", rel_root=tmp_path)
    assert out == {"resources/a.txt": b"a", "resources/sub/b.txt": b"b"}


def test_skip_paths_matches_import_local_path(tmp_path: Path) -> None:
    """_import_local_path 形状: 跳过 SKILL.md 本体，其余全收。"""
    _tree(tmp_path)
    out = walk_skill_source_files(tmp_path, skip_paths=(tmp_path / "SKILL.md",))
    assert out == {"resources/a.txt": b"a", "resources/sub/b.txt": b"b"}


def test_non_canonical_rel_fails_loud_per_ra076(tmp_path: Path) -> None:
    """RA-076 策略覆盖接缝: 反斜杠文件名不再静默归一化，直接 fail-loud。"""
    (tmp_path / "we\\ird.txt").write_bytes(b"x")
    with pytest.raises(SkillContractError):
        walk_skill_source_files(tmp_path)


def test_missing_walk_root_yields_empty(tmp_path: Path) -> None:
    assert walk_skill_source_files(tmp_path / "nope") == {}
