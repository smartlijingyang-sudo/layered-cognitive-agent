"""Sandbox resolver — Onlyboxes only.

Host sidecar is a machine transport, not a Sandbox. Tests may still inject a
real Sandbox via ``set_sandbox_resolver``. Gateway must not inject Host here.

Required env (after ``load_dotenv_if_present``):
- ``ONLYBOXES_BASE_URL`` — console HTTP base, e.g. ``http://127.0.0.1:8089``
- ``ONLYBOXES_ACCESS_TOKEN`` — dashboard access token (``obx_...``)

Optional:
- ``LCA_SANDBOX_BACKEND`` — if set to anything other than ``onlyboxes`` / empty,
  still only Onlyboxes is supported; unknown values log a warning and return
  ``None`` unless Onlyboxes credentials are present (credentials win).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from lca.contracts.protocols import Sandbox
from lca.layer0_infra.llm_adapter.factory import load_dotenv_if_present

_log = logging.getLogger(__name__)

_override: Callable[[], Sandbox | None] | None = None


def set_sandbox_resolver(resolver: Callable[[], Sandbox | None] | None) -> None:
    """Tests inject a Sandbox. Gateway must not inject Host."""
    global _override
    _override = resolver


_ENV_BASE_URL = "ONLYBOXES_BASE_URL"
_ENV_ACCESS_TOKEN = "ONLYBOXES_ACCESS_TOKEN"  # noqa: S105
_ENV_SANDBOX_BACKEND = "LCA_SANDBOX_BACKEND"
_BACKEND_ONLYBOXES = "onlyboxes"


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
    """Onlyboxes, or a test-injected Sandbox. Never Host."""
    if _override is not None:
        found = _override()
        if found is not None:
            return found

    backend = sandbox_backend()
    if backend and backend not in {_BACKEND_ONLYBOXES, ""}:
        _log.warning(
            "LCA_SANDBOX_BACKEND=%s is unsupported; only 'onlyboxes' is available",
            backend,
        )

    base = onlyboxes_base_url()
    token = onlyboxes_access_token()
    if not base or not token:
        _log.info(
            "Onlyboxes not configured (need %s + %s); sandbox tool omitted",
            _ENV_BASE_URL,
            _ENV_ACCESS_TOKEN,
        )
        return None

    from lca.layer0_infra.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter

    _log.info("Using OnlyboxesSandboxAdapter base_url=%s", base)
    return OnlyboxesSandboxAdapter(base_url=base, access_token=token)
