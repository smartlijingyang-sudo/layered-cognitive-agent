"""Top-level pytest fixtures for the LCA test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _ensure_no_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep LLM_API_KEY / LANGFUSE_* out of the test process so the
    resolver's ``is_available()`` flips to ``False`` deterministically.

    Opt-out: a test module that drives scripted runs (no real LLM traffic)
    sets module-level ``__keep_llm_key__ = True``. Such runs must still pass
    the reasoner fail-loud credential gate
    (``lca/plugins/think/reasoner/credentials.py``); the scripted adapter
    never touches the network, so the ambient dummy key is enough.
    LANGFUSE_* deletions always apply.
    """
    if not getattr(request.module, "__keep_llm_key__", False):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LCA_OBS_INCLUDE_LANGFUSE", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LCA_OBS_INCLUDE_LANGFUSE", "false")


@pytest.fixture(autouse=True)
def _isolate_runs_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Point every profile-driven runs root at a temporary directory.

    The kernel sinks resolve ``runs_root`` through ``LCA_RUNS_ROOT`` (see
    ``lca.infrastructure.persistence.run_paths.default_runs_root`` and the
    ``{from_env: LCA_RUNS_ROOT}`` keys in the web profiles), so this one
    variable keeps the whole test suite from writing harness runs into the
    production ``traces/runs`` tree. Opt out module-wide with
    ``__keep_runs_root__ = True`` only for tests that must read the real tree.
    """
    if getattr(request.module, "__keep_runs_root__", False):
        return
    monkeypatch.setenv("LCA_RUNS_ROOT", str(tmp_path / "traces" / "runs"))


@pytest.fixture(autouse=True)
def _isolate_skill_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[None]:
    """Point the global operational skill store at a temporary directory.

    Same hazard as ``_isolate_runs_root``, different production tree. A test
    that builds an ``Agent`` without ``scope=`` boots the default kernel
    profile, which loads ``lca-skills-provider``, whose ``setup()`` calls
    ``materialize_bundled_skills()``; that install_packages every repo
    ``skills/`` pack into ``~/.lca/skills``. Rewriting a global pack
    orphans the hard links 700+ assistant homes hold to it (ADR-0243 D1).

    Opt out module-wide with ``__keep_skill_store__ = True`` only for a test
    that must read the real store.
    """
    from lca.infrastructure.skills.settings.settings import get_skill_settings

    if not getattr(request.module, "__keep_skill_store__", False):
        monkeypatch.setenv("LCA_SKILL_CACHE_DIR", str(tmp_path / "skills"))
    # ``get_skill_settings`` is ``@lru_cache(maxsize=1)``. Without the clear, a
    # settings object built by an earlier test pins its root for the rest of the
    # process and this test's env change never takes effect. Clearing on the
    # opt-out path too, so such a test re-resolves the real root rather than
    # inheriting some previous test's tmp dir.
    get_skill_settings.cache_clear()
    yield
    get_skill_settings.cache_clear()


@pytest.fixture
def isolated_lca_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``LCA_HOME`` at a temporary directory and return it.

    Load-bearing for a test that runs a plugin ``setup()``, because that is
    where ``get_lca_home()`` resolves the host routine lock directory. Belt and
    braces for a test that builds a scheduler directly and passes its own
    ``lock_dir``: ``get_lca_home`` appears in none of ``dream.py``,
    ``dream_scheduler.py``, ``episode_buffer.py``,
    ``contextfiles/domain/layout.py`` or ``contextfiles/service/indexing.py``,
    and the FTS index is ``Path(home) / chosen.index_db_path``. What keeps such
    a test inside ``tmp_path`` is home-relative resolution all the way through
    ``run_dream``, not this variable.

    Requested by name rather than autouse, unlike the two fixtures above.
    Flipping ``LCA_HOME`` for the whole suite would change behaviour for every
    test that resolves a real assistant home, and the two autouse fixtures here
    each carry a module-level opt-out for exactly that reason.
    """
    lca_home = (tmp_path / "lca-home").resolve()
    monkeypatch.setenv("LCA_HOME", str(lca_home))
    return lca_home
