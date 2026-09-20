"""Sandbox resolver — Onlyboxes preferred, local host-backed fallback.

Host sidecar is a machine transport, not a Sandbox. Tests may still inject a
real Sandbox via ``set_sandbox_resolver``. Gateway must not inject Host here.

Required env for Onlyboxes (after ``load_dotenv_if_present``):
- ``ONLYBOXES_BASE_URL`` — console HTTP base, e.g. ``http://10.36.6.252:8089``
- ``ONLYBOXES_ACCESS_TOKEN`` — dashboard access token (``obx_...``)

Optional:
- ``LCA_SANDBOX_BACKEND`` — ``onlyboxes`` | ``local`` | empty.
  Empty / ``local``: Onlyboxes when credentials exist, else local host-backed.
  ``onlyboxes``: Onlyboxes only (returns ``None`` without credentials).
- ``LCA_LOCAL_SANDBOX_ROOT`` — host directory backing the local guest mount
  (default: writable ``/mnt/data``, else ``~/.cache/lca/local-sandbox/mnt/data``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from lca.contracts.models.core.policy.sandbox_policy import DEFAULT_POLICY, SandboxPolicy
from lca.contracts.protocols import Sandbox
from lca.infrastructure.llm_adapter.factory.factory import load_dotenv_if_present

_log = logging.getLogger(__name__)

_override: Callable[[], Sandbox | None] | None = None
_policy: SandboxPolicy = DEFAULT_POLICY


def get_sandbox_policy() -> SandboxPolicy:
    """Return the currently active SandboxPolicy."""
    return _policy


def set_sandbox_policy(policy: SandboxPolicy) -> None:
    """Override the active SandboxPolicy (tests / composition root)."""
    global _policy
    _policy = policy


def set_sandbox_resolver(resolver: Callable[[], Sandbox | None] | None) -> None:
    """Tests inject a Sandbox. Gateway must not inject Host."""
    global _override
    _override = resolver


_ENV_BASE_URL = "ONLYBOXES_BASE_URL"
_ENV_ACCESS_TOKEN = "ONLYBOXES_ACCESS_TOKEN"  # noqa: S105
_ENV_SANDBOX_BACKEND = "LCA_SANDBOX_BACKEND"
_BACKEND_ONLYBOXES = "onlyboxes"
_BACKEND_LOCAL = "local"


def onlyboxes_base_url() -> str | None:
    load_dotenv_if_present()
    value = os.getenv(_ENV_BASE_URL, "").strip()
    return value or None


def onlyboxes_access_token() -> str | None:
    load_dotenv_if_present()
    value = os.getenv(_ENV_ACCESS_TOKEN, "").strip()
    return value or None


def sandbox_backend() -> str:
    """Return ``LCA_SANDBOX_BACKEND`` (lowercased), or empty when unset."""
    load_dotenv_if_present()
    return os.getenv(_ENV_SANDBOX_BACKEND, "").strip().lower()


def resolve_sandbox() -> Sandbox | None:
    """Onlyboxes when configured; else local host-backed Sandbox. Never Host."""
    if _override is not None:
        found = _override()
        if found is not None:
            return found

    backend = sandbox_backend()
    if backend and backend not in {_BACKEND_ONLYBOXES, _BACKEND_LOCAL, ""}:
        _log.warning(
            "LCA_SANDBOX_BACKEND=%s is unsupported; expected 'onlyboxes' or 'local'",
            backend,
        )

    base = onlyboxes_base_url()
    token = onlyboxes_access_token()
    prefer_onlyboxes = backend in {_BACKEND_ONLYBOXES, ""}
    if prefer_onlyboxes and base and token:
        from lca.infrastructure.sandbox.onlyboxes.adapter import OnlyboxesSandboxAdapter

        _log.info("Using OnlyboxesSandboxAdapter base_url=%s", base)
        return OnlyboxesSandboxAdapter(base_url=base, access_token=token)

    if backend == _BACKEND_ONLYBOXES:
        _log.info(
            "Onlyboxes requested but not configured (need %s + %s); sandbox omitted",
            _ENV_BASE_URL,
            _ENV_ACCESS_TOKEN,
        )
        return None

    # Local host-backed Sandbox: materializes SANDBOX plane tools without
    # conflating Host/MACHINE transport with sandbox computer APIs.
    from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter

    local = LocalSandboxAdapter()
    _log.info("Using LocalSandboxAdapter host_root=%s", local.host_root)
    return local
