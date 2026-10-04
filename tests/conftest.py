"""Top-level pytest fixtures for the LCA test suite."""

from __future__ import annotations

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
