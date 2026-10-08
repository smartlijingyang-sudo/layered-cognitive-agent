"""RA-078: ``get_skill_settings()`` 不再有进程级全局 memo。

每次调用按当前 env 重新解析；测试隔离不再依赖"记得 cache_clear"，
生产 env 变更也不再被首调 pin 住。
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.skills.settings.settings import get_skill_settings


def test_settings_not_memoized_env_change_takes_effect(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LCA_SKILL_CACHE_DIR", str(tmp_path / "a"))
    first = get_skill_settings()
    assert Path(first.cache_dir) == tmp_path / "a"

    monkeypatch.setenv("LCA_SKILL_CACHE_DIR", str(tmp_path / "b"))
    second = get_skill_settings()
    assert Path(second.cache_dir) == tmp_path / "b"
    assert first is not second


def test_store_construction_creates_nothing_first_write_creates(
    tmp_path: Path,
) -> None:
    """RA-078: 构造零 FS 触碰；首次 install_package 建目录并落盘。"""
    from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
    from lca.infrastructure.skills.settings.settings import SkillSettings

    root = tmp_path / "fresh-root"
    store = DiskSkillPackageStore(SkillSettings(cache_dir=root))
    assert not root.exists()

    store.install_package(
        skill_id="lazy",
        skill_md_text="---\nname: lazy\ndescription: d\nreferences: []\n---\nbody",
        resource_files={"r.txt": b"data"},
        source_url="u",
    )
    assert (root / "lazy" / "manifest.json").is_file()
    assert (root / "lazy" / "resources" / "r.txt").is_file()
