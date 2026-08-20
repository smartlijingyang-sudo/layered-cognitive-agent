"""Top-level pytest fixtures for the LCA test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ensure_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep LLM_API_KEY / LANGFUSE_* out of the test process so the
    resolver's ``is_available()`` flips to ``False`` deterministically.
    """
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LCA_OBS_INCLUDE_LANGFUSE", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LCA_OBS_INCLUDE_LANGFUSE", "false")
