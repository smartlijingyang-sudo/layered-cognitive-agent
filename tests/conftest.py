"""Top-level pytest fixtures for the LCA test suite."""

from __future__ import annotations

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
