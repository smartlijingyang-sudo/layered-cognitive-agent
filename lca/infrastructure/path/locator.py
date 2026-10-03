"""Authoritative user home and LCA workspace path locator (ADR-0195 / Path Governance).

Provides deterministic resolution of the host user's actual home directory and
the authoritative ``~/.lca`` root, preventing storage drift into sandbox or
multi-account tool directories (e.g. ``.agy-accounts/<account-id>``).
"""

from __future__ import annotations

import os
from pathlib import Path


def get_real_user_home() -> Path:
    """Resolve the authoritative host user home directory.

    Priority:
    1. Explicit override via ``LCA_USER_HOME`` environment variable.
    2. OS user database entry via ``pwd.getpwuid(os.getuid()).pw_dir`` when
       available and pointing to an existing directory, or when the active
       ``HOME`` environment variable points to a synthetic account directory
       (such as ``.agy-accounts``).
    3. Heuristic rollback if ``HOME`` contains ``.agy-accounts``.
    4. Fallback to :meth:`pathlib.Path.home`.
    """
    override = os.environ.get("LCA_USER_HOME", "").strip()
    if override:
        return Path(override).resolve()

    env_home = os.environ.get("HOME", "").strip()
    is_agy_sandbox = ".agy-accounts" in env_home

    try:
        import pwd

        pw_home = pwd.getpwuid(os.getuid()).pw_dir
        if pw_home:
            pw_path = Path(pw_home)
            if is_agy_sandbox or not env_home:
                return pw_path.resolve()
            if pw_path.is_dir():
                return pw_path.resolve()
    except (KeyError, ImportError, AttributeError, OSError):
        pass

    if is_agy_sandbox and env_home:
        # Heuristic fallback: /path/to/user/.agy-accounts/<id> -> /path/to/user
        idx = env_home.find("/.agy-accounts")
        if idx > 0:
            candidate = Path(env_home[:idx])
            if candidate.is_dir():
                return candidate.resolve()

    if env_home:
        return Path(env_home).resolve()

    return Path.home().resolve()


def get_lca_home() -> Path:
    """Return the authoritative ``~/.lca`` root directory.

    Priority:
    1. Explicit override via ``LCA_HOME`` environment variable.
    2. ``get_real_user_home() / ".lca"``.
    """
    override = os.environ.get("LCA_HOME", "").strip()
    if override:
        return Path(override).resolve()
    return get_real_user_home() / ".lca"



def assistant_workspace_root(assistant_id: str | None = None) -> Path:
    """Return the single authoritative workspace directory (Workspace SSOT).

    This is the ONE place that decides where "the workspace" lives on the
    host. Every host-side consumer (local sandbox mount, FileStore root,
    WorkspaceService) must resolve through here instead of hardcoding
    ``/mnt/data`` or ``traces/files``.

    The guest contract is untouched: inside the sandbox the path is still
    ``/mnt/data`` (``SANDBOX_MOUNT_ROOT``, Onlyboxes image contract); this
    function decides what host directory that guest path is backed by.

    Resolution priority:
    1. ``LCA_WORKSPACE_ROOT`` env — explicit ops override (wins).
    2. ``LCA_LOCAL_SANDBOX_ROOT`` env — backward compat with the pre-SSOT
       local-sandbox override.
    3. ``{lca_home}/assistants/<assistant_id>/workspace`` — the per-assistant
       durable workspace (assistant_id from arg or ``LCA_ASSISTANT_ID`` env).
    4. Legacy fallback: writable ``/mnt/data``, else
       ``~/.cache/lca/local-sandbox/mnt/data`` (keeps exotic deployments
       working).
    """
    override = os.environ.get("LCA_WORKSPACE_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    legacy = os.environ.get("LCA_LOCAL_SANDBOX_ROOT", "").strip()
    if legacy:
        return Path(legacy).resolve()
    aid = (assistant_id or os.environ.get("LCA_ASSISTANT_ID", "")).strip()
    if aid:
        return get_lca_home() / "assistants" / aid / "workspace"
    try:
        path = Path("/mnt/data")
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".lca-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        cache = Path.home() / ".cache" / "lca" / "local-sandbox" / "mnt" / "data"
        cache.mkdir(parents=True, exist_ok=True)
        return cache

def expand_user_path(path: str | Path) -> Path:
    """Expand user tilde references against the authoritative user/LCA home.

    Rules:
    - If path is ``"~/.lca"`` or starts with ``"~/.lca/"``, routes directly to
      :func:`get_lca_home` (honoring ``LCA_HOME`` if configured).
    - If path is ``"~"`` or starts with ``"~/"``, expands against :func:`get_real_user_home`.
    - Other paths (absolute, relative, or ``~other_user``) are resolved via standard
      :meth:`pathlib.Path.expanduser` or returned as-is.
    """
    raw = str(path).strip()
    if not raw:
        return Path(raw)

    if raw == "~/.lca":
        return get_lca_home()
    if raw.startswith("~/.lca/"):
        return get_lca_home() / raw[7:]

    if raw == "~":
        return get_real_user_home()
    if raw.startswith("~/"):
        return get_real_user_home() / raw[2:]

    if raw.startswith("~"):
        return Path(raw).expanduser()

    return Path(raw)


__all__ = [
    "expand_user_path",
    "get_lca_home",
    "get_real_user_home",
    "assistant_workspace_root",
]
