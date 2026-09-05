r"""Pure constants: which env keys may be loaded from .env.

Pure module — does NOT import :mod:`os`, :mod:`sys`, or :mod:`dotenv`. PR-1
verification ``grep -rE 'import os|import sys|from dotenv' lca/infrastructure/env/``
must be empty. The whitelist is consumed by
:func:`lca.infrastructure.env.layered.filter_env_keys` and the kernel facade
:func:`lca_kernel.env.load_layered_env`; see ADR-0115 §决定 1 K7 + ADR-0117
§决定 4 for the deepseek BOOTSTRAP model adapted to Python + LCA.

Three constants are exposed:

- :data:`BOOTSTRAP_NAMES` — exact names whose ambient value may be overridden
  by ``.env`` (Python/venv, shell/locale, VCS hooks, network trust).
- :data:`BOOTSTRAP_PREFIXES` — name prefixes allowed from ``.env``. The ``LCA_``
  / ``LLM_`` / ``LCA_KERNEL_SERVE_`` / ``LOBE_`` etc. coverage mirrors the
  ``grep -rhE 'os.environ\[|os\.getenv\(' lca/ scripts/`` inventory captured
  during PR-1 (see plan §C1.1 and ADR-0117 §决定 4).
- :data:`BOOTSTRAP_FORBIDDEN` — exact names that ``.env`` must NEVER set,
  regardless of prefix. ``LCA_PROFILE`` must come from argv (D5), secret
  material goes through the LLM resolver, ``LCA_INTERNAL_INJECTION`` defends
  the kernel internal flag namespace.
"""

from __future__ import annotations

BOOTSTRAP_NAMES: frozenset[str] = frozenset(
    {
        # Python / venv
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_PROJECT_ENVIRONMENT",
        "UV_LINK_MODE",
        # Shell / locale
        "HOME",
        "USERPROFILE",
        "SHELL",
        "LANG",
        "LC_ALL",
        "TZ",
        # VCS hooks
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_EXTERNAL_DIFF",
        "GIT_PAGER",
        "GIT_EDITOR",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_COUNT",
        "EDITOR",
        "VISUAL",
        "PAGER",
        # Network trust
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "PYTHONHTTPSVERIFY",
        "NODE_TLS_REJECT_UNAUTHORIZED",
    }
)

BOOTSTRAP_PREFIXES: tuple[str, ...] = (
    # Core LCA env whitelist
    "LCA_",
    "LCA_INTERNAL_",
    # Freedesktop / OS conventions
    "XDG_",
    "DYLD_",
    "LD_",
    "BASH_FUNC_",
    # LCA actual deployment env (PR-1 inventory of grep result)
    "LLM_",  # LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / LLM_API_STYLE / ...
    "LCA_KERNEL_SERVE_",  # LCA_KERNEL_SERVE_HOST / _PORT / _BIND
    # Deprecated; preserved until 2026-12-31 per ADR-0119 followup-2.
    "GATEWAY_",  # GATEWAY_HOST / GATEWAY_PORT / GATEWAY_BIND (compat shim)
    "LOBE_",  # LOBE_HOST / LOBE_DEV_PORT
    "LOBEHUB_",  # LOBEHUB_RELEASE
    "ONLYBOXES_",  # ONLYBOXES_BASE_URL / _ACCESS_TOKEN / _TERMINAL_IMAGE / _WORKER_SERVICE
    "MARKET_",  # MARKET_CLIENT_ID / MARKET_CLIENT_SECRET
    "AGENCY_",  # AGENCY_ROLES_DIR
    "WAL_",  # WAL_PATH / WAL_RETENTION
    "DB_",  # DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
    "S3_",  # S3_ENDPOINT / S3_BUCKET / S3_ACCESS_KEY
    "REDIS_",  # REDIS_HOST / REDIS_PORT / REDIS_DB
    "OTEL_",  # OpenTelemetry standard
    "VAULT_",  # VAULT_ADDR / VAULT_TOKEN
    "COMPOSIO_",  # COMPOSIO_API_KEY / COMPOSIO_AUTH_CONFIG_IDS
)

BOOTSTRAP_FORBIDDEN: frozenset[str] = frozenset(
    {
        "LCA_PROFILE",  # must be decided by argv, not .env (ADR-0115 D5)
        "LCA_KERNEL_KEY",  # secrets go through the LLM resolver, not .env
        "LCA_INTERNAL_INJECTION",  # protects kernel internal flag namespace
    }
)


__all__ = ["BOOTSTRAP_FORBIDDEN", "BOOTSTRAP_NAMES", "BOOTSTRAP_PREFIXES"]
