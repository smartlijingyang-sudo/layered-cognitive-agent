"""Sandbox resolver — explicit backend switch; no silent fake capability.

Production tool wiring (``build_default_tools``) **omits** the sandbox tool when
no real backend is selected (ProductionLLMResolver pattern: no fake capability).

Selection order:
1. ``LCA_SANDBOX_BACKEND=local`` → microsandbox microVM (no cloud key).
2. ``LCA_SANDBOX_BACKEND=e2b`` or default with ``E2B_API_KEY`` → E2B cloud.
3. ``prefer_mock=True`` (or ``LCA_SANDBOX_BACKEND=mock``) → in-process test double.
4. Otherwise ``None`` (caller omits sandbox-backed tools).

``MockSandboxAdapter`` is **not** a security boundary — only a unit-test / demo
stand-in (ADR-0044).
"""

from __future__ import annotations

import logging
import os

from lca.contracts.protocols import Sandbox
from lca.layer0_infra.llm_adapter.factory import load_dotenv_if_present

_log = logging.getLogger(__name__)

_ENV_E2B_API_KEY = "E2B_API_KEY"
_ENV_SANDBOX_BACKEND = "LCA_SANDBOX_BACKEND"

_BACKEND_LOCAL = "local"
_BACKEND_E2B = "e2b"
_BACKEND_MOCK = "mock"


def e2b_api_key() -> str | None:
    """Return configured E2B API key, if any (loads nearest ``.env`` first)."""
    load_dotenv_if_present()
    key = os.getenv(_ENV_E2B_API_KEY)
    return key if key else None


def sandbox_backend() -> str:
    """Return ``LCA_SANDBOX_BACKEND`` (lowercased), or empty when unset."""
    load_dotenv_if_present()
    return os.getenv(_ENV_SANDBOX_BACKEND, "").strip().lower()


def resolve_sandbox(
    *,
    api_key: str | None = None,
    prefer_mock: bool = False,
) -> Sandbox | None:
    """Resolve a Sandbox implementation.

    Returns:
        ``LocalSandboxAdapter`` when ``LCA_SANDBOX_BACKEND=local``;
        ``E2BSandboxAdapter`` when a key is available (or backend=e2b with key);
        ``MockSandboxAdapter`` when ``prefer_mock=True`` / ``backend=mock``;
        ``None`` when neither (caller should omit sandbox-backed tools).
    """
    backend = sandbox_backend()

    if backend == _BACKEND_LOCAL:
        from lca.layer0_infra.sandbox.local_adapter import LocalSandboxAdapter

        _log.info("LCA_SANDBOX_BACKEND=local; using LocalSandboxAdapter (microsandbox)")
        return LocalSandboxAdapter()

    if backend == _BACKEND_MOCK:
        from lca.layer0_infra.sandbox.mock_adapter import MockSandboxAdapter

        _log.info("LCA_SANDBOX_BACKEND=mock; using MockSandboxAdapter (test double)")
        return MockSandboxAdapter()

    resolved = api_key if api_key is not None else e2b_api_key()
    if backend == _BACKEND_E2B and not resolved:
        _log.warning("LCA_SANDBOX_BACKEND=e2b but E2B_API_KEY is unset")
        if prefer_mock:
            from lca.layer0_infra.sandbox.mock_adapter import MockSandboxAdapter

            return MockSandboxAdapter()
        return None

    if resolved:
        from lca.layer0_infra.sandbox.e2b_adapter import E2BSandboxAdapter

        return E2BSandboxAdapter(api_key=resolved)

    if prefer_mock:
        from lca.layer0_infra.sandbox.mock_adapter import MockSandboxAdapter

        _log.info("No E2B_API_KEY; using MockSandboxAdapter (prefer_mock=True)")
        return MockSandboxAdapter()
    return None
