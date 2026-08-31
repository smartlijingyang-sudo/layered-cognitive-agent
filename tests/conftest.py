"""Top-level pytest fixtures for the LCA test suite."""

from __future__ import annotations

import sys

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


@pytest.fixture(autouse=True)
def _block_kernel_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """K6's :class:`DefaultShutdownCoordinator` calls ``sys.exit`` on dispose
    (kernel is a process-root CM). Test processes must keep running, so
    neutralize the exit call globally. The kernel lifespan tests assert
    dispose semantics, not process termination.
    """
    monkeypatch.setattr(sys, "exit", lambda code=0: None)
