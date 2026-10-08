"""The suite must not resolve the global operational skill store to production.

A test that builds an ``Agent`` without ``scope=`` boots the default kernel
profile, which loads ``lca-skills-provider``; its ``setup()`` calls
``resolve_skill_store()``, which runs ``ensure_bundled_skills`` and writes every
repo ``skills/`` pack into the resolved store root. When that root was the
production ``~/.lca/skills``, a memory-wiring unit test rewrote
``skill-creator`` there and orphaned the hard links 700+ assistant homes hold to
it (ADR-0243 D1 pins versions, so nothing re-links them on its own).

``_isolate_skill_store`` in ``tests/conftest.py`` closes that by pointing
``LCA_SKILL_CACHE_DIR`` at ``tmp_path``. These assertions pin the resolution
seam the production path actually uses, without performing any write.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.path.locator import get_lca_home
from lca.infrastructure.skills.settings.settings import get_skill_settings


def test_global_skill_store_root_is_redirected_off_production(tmp_path: Path) -> None:
    cache_dir = get_skill_settings().cache_dir

    assert Path(cache_dir) == tmp_path / "skills"
    assert not Path(cache_dir).is_relative_to(get_lca_home())


def test_production_skill_root_is_not_the_resolved_root() -> None:
    """Guard the guard: the redirect must actually move the root somewhere else.

    Without this, ``test_global_skill_store_root_is_redirected_off_production``
    would also pass if ``LCA_HOME`` were redirected suite wide, which would
    silently change behaviour for every test resolving a real assistant home.
    """
    assert get_skill_settings().cache_dir != get_lca_home() / "skills"
