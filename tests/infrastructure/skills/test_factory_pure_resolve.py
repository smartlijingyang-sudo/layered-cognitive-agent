"""RA-058: resolve_skill_store() is pure construction; bundled-skill writes are explicit.

71515dace: a unit test booted a default kernel -> skills-provider setup() ->
resolve_skill_store() rewrote the production ~/.lca/skills because "resolve"
secretly ran ensure_bundled_skills. After the split, resolve never writes;
materialize_bundled_skills() is the single explicit write step.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.skills.factory.factory import (
    materialize_bundled_skills,
    resolve_skill_store,
)


def _pack_dirs(root: Path) -> list[Path]:
    return [c for c in root.iterdir() if c.is_dir() and (c / "SKILL.md").is_file()]


def test_resolve_skill_store_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    """纯 resolve 不得落盘任何技能包（autouse fixture 已隔离到 tmp）。"""
    from lca.infrastructure.skills.settings.settings import get_skill_settings

    store_root = Path(get_skill_settings().cache_dir)
    store = resolve_skill_store()
    assert Path(store._root) == store_root
    assert _pack_dirs(store_root) == []


def test_materialize_bundled_skills_writes_packs() -> None:
    """显式物化步骤写盘 bundled 包并返回 skill_ids。"""
    from lca.infrastructure.skills.settings.settings import get_skill_settings

    store = resolve_skill_store()
    written = materialize_bundled_skills(store)
    assert written, "expected bundled skills to be materialized"
    store_root = Path(get_skill_settings().cache_dir)
    assert {c.name for c in _pack_dirs(store_root)} >= set(written)


def test_materialize_bundled_skills_is_idempotent() -> None:
    """第二次物化无写入（ensure_bundled_skills 按 content_hash 跳过）。"""
    store = resolve_skill_store()
    first = materialize_bundled_skills(store)
    assert first
    second = materialize_bundled_skills(store)
    assert second == ()


def test_materialize_defaults_to_resolved_store() -> None:
    """不传 store 时内部走纯 resolve 再物化。"""
    written = materialize_bundled_skills()
    assert written
