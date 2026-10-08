"""Per-exec mount-namespace wrapping for the Local sandbox plane (todo-81 (c)).

Spike-verified on 252 (2026-10-08): ``unshare -U -m`` works unprivileged
(kernel 5.10, ``unprivileged_userns_clone=1``). Pattern A: each exec runs as::

    unshare -Urm bash -c 'mount --make-rprivate /; mkdir -p /mnt/data;
        mount --bind <session-dir> /mnt/data; cd /mnt/data && <command>'

No holder process: the namespace is created fresh per exec and dies with it.
Session state lives in the host session directory, so there is nothing to
manage across execs (5 consecutive execs verified: zero residual mounts /
processes on the host; ``user.max_user_namespaces`` is ample).

``--make-rprivate /`` is REQUIRED: systemd defaults ``/`` to shared
propagation; without it the bind mount would leak back into the host mount
table (pinned by ``test_no_mount_leak_into_host_mount_table``).

``mkdir -p`` the guest mount inside the namespace: the bind target must exist;
it is idempotent and, once shadowed by the private bind, invisible to the
host (an empty directory may remain on the host filesystem — harmless).
"""

from __future__ import annotations

import functools
import os
import platform
import shlex
import shutil
import subprocess

#: Env var override for mount-namespace mode. Explicit ``0``/``1`` wins;
#: unset means auto-detect via :func:`mount_namespace_available`.
MOUNT_NS_ENV_VAR = "LCA_SANDBOX_MOUNT_NS"


@functools.lru_cache(maxsize=1)
def mount_namespace_available() -> bool:
    """Probe: does ``unshare -U -m`` work on this machine? Cached.

    Pure capability check — no sandbox state touched. False on non-Linux,
    when ``unshare`` is missing, or when unprivileged user namespaces are
    disabled.
    """
    if platform.system() != "Linux":
        return False
    if shutil.which("unshare") is None:
        return False
    try:
        proc = subprocess.run(
            ["unshare", "-Urm", "true"],  # noqa: S607 -- unshare via PATH is intentional (shutil.which gate above)
            capture_output=True,
            timeout=15,
        )
    except Exception:
        return False
    return proc.returncode == 0


def mount_namespace_enabled() -> bool:
    """Whether the Local plane should use per-exec mount namespaces.

    Explicit ``LCA_SANDBOX_MOUNT_NS=0``/``1`` wins (test/debug escape hatch);
    otherwise auto-detect via :func:`mount_namespace_available`. When False,
    the adapter falls back to the (b) virtual string-mapping path — the agent
    sees the same ``/mnt/data`` namespace either way.
    """
    raw = os.environ.get(MOUNT_NS_ENV_VAR, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return mount_namespace_available()


def wrap_in_mount_namespace(
    command: str, *, session_dir: str, guest_mount: str
) -> str:
    """Wrap shell *command* so it runs with *session_dir* bind-mounted at *guest_mount*.

    Pure string construction (no userns needed) — safe to unit-test anywhere.
    The guest command itself is NOT rewritten: inside the namespace
    ``guest_mount`` really is ``session_dir``, so the kernel translates and
    string rewriting would be wrong (it would map an already-correct path).
    """
    setup = (
        "mount --make-rprivate / && "
        f"mkdir -p {shlex.quote(guest_mount)} && "
        f"mount --bind {shlex.quote(session_dir)} {shlex.quote(guest_mount)}"
    )
    inner = f"{setup} && cd {shlex.quote(guest_mount)} && {command}"
    return "unshare -Urm bash -c " + shlex.quote(inner)
