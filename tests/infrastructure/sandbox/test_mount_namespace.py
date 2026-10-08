"""Per-exec mount-namespace mode for the Local sandbox plane (todo-81 (c)).

Pattern A (spike-verified on 252): each exec runs as::

    unshare -Urm bash -c 'mount --make-rprivate /; mkdir -p <mount>;
        mount --bind <session-dir> <mount>; cd <mount> && <command>'

No holder process — the namespace is fresh per exec and dies with it.
Agent-visible semantics are identical to the (b) virtual path: the agent
sees ``/mnt/data`` backed by its own session directory. Only the mechanism
differs (kernel bind vs string rewriting).
"""

from __future__ import annotations

import os
import shlex
import subprocess

import pytest

from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter
from lca.infrastructure.sandbox.paths.mount_namespace import (
    MOUNT_NS_ENV_VAR,
    mount_namespace_available,
    mount_namespace_enabled,
    wrap_in_mount_namespace,
)
from lca.infrastructure.sandbox.paths.sandbox_paths import SandboxPaths

GUEST_MOUNT = "/mnt/data"

needs_mount_ns = pytest.mark.skipif(
    not mount_namespace_available(),
    reason="unprivileged user namespaces unavailable on this machine",
)


# ---------------------------------------------------------------------------
# mode detection (no userns needed)
# ---------------------------------------------------------------------------


def test_mount_namespace_available_returns_bool() -> None:
    assert isinstance(mount_namespace_available(), bool)


def test_mount_namespace_enabled_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MOUNT_NS_ENV_VAR, "1")
    assert mount_namespace_enabled() is True
    monkeypatch.setenv(MOUNT_NS_ENV_VAR, "0")
    assert mount_namespace_enabled() is False
    monkeypatch.delenv(MOUNT_NS_ENV_VAR)
    assert mount_namespace_enabled() == mount_namespace_available()


def test_adapter_mount_ns_mode_override(tmp_path) -> None:
    auto = LocalSandboxAdapter(root=str(tmp_path))
    assert auto._mount_ns_mode() == mount_namespace_enabled()
    assert LocalSandboxAdapter(root=str(tmp_path), mount_namespace=True)._mount_ns_mode() is True
    assert LocalSandboxAdapter(root=str(tmp_path), mount_namespace=False)._mount_ns_mode() is False


# ---------------------------------------------------------------------------
# wrapper construction (pure — no userns needed)
# ---------------------------------------------------------------------------


def test_wrap_in_mount_namespace_structure() -> None:
    wrapped = wrap_in_mount_namespace(
        "cat /mnt/data/f.txt", session_dir="/s/work", guest_mount=GUEST_MOUNT
    )
    argv = shlex.split(wrapped)
    assert argv[:4] == ["unshare", "-Urm", "bash", "-c"]
    inner = argv[4]
    # --make-rprivate MUST precede the bind: systemd defaults / to shared
    # propagation; without it the bind leaks back to the host mount table.
    assert inner.index("mount --make-rprivate /") < inner.index("mount --bind")
    assert "mount --bind /s/work /mnt/data" in inner
    # guest command passes through UNREWRITTEN — the kernel translates
    assert "cat /mnt/data/f.txt" in inner
    # guest starts in its own directory
    assert inner.index("mount --bind") < inner.index("cd /mnt/data")


def test_wrap_quotes_session_dir_with_spaces() -> None:
    session_dir = "/s/my work'x"
    wrapped = wrap_in_mount_namespace(
        "echo hi", session_dir=session_dir, guest_mount=GUEST_MOUNT
    )
    argv = shlex.split(wrapped)
    inner = argv[4]
    assert f"mount --bind {shlex.quote(session_dir)} {GUEST_MOUNT}" in inner


def test_sandbox_paths_mounted_mode_text_adapters_are_identity(tmp_path) -> None:
    paths = SandboxPaths.for_local(tmp_path, mounted=True)
    assert paths.mounted is True
    # No string translation in mounted mode — the kernel does it.
    assert paths.rewrite_command("cat /mnt/data/f.txt") == "cat /mnt/data/f.txt"
    assert paths.present_text(str(tmp_path / "f.txt")) == str(tmp_path / "f.txt")
    # Path-level mapping still works for host-side operations (staging, etc.).
    assert paths.resolve("/mnt/data/f.txt") == tmp_path / "f.txt"
    assert paths.present(tmp_path / "f.txt") == "/mnt/data/f.txt"


def test_sandbox_paths_virtual_mode_still_rewrites(tmp_path) -> None:
    paths = SandboxPaths.for_local(tmp_path)  # mounted=False default
    assert paths.mounted is False
    assert paths.rewrite_command("cat /mnt/data/f.txt") == f"cat {tmp_path}/f.txt"


# ---------------------------------------------------------------------------
# integration (needs userns)
# ---------------------------------------------------------------------------


@needs_mount_ns
def test_mounted_exec_reads_session_file_via_guest_mount(tmp_path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (session_dir / "marker.txt").write_text("hello-mount")
    wrapped = wrap_in_mount_namespace(
        "cat /mnt/data/marker.txt",
        session_dir=str(session_dir),
        guest_mount=GUEST_MOUNT,
    )
    proc = subprocess.run(  # noqa: S603 -- argv is test-constructed, no user input
        ["bash", "-c", wrapped],  # noqa: S607 -- bash via PATH is fine in tests
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "hello-mount"


@needs_mount_ns
def test_mounted_exec_does_not_leak_into_host_mount_table(tmp_path) -> None:
    """Regression test for ``--make-rprivate /``: without it, the per-exec
    bind propagates back into this process's (host) mount table."""
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    wrapped = wrap_in_mount_namespace(
        "true", session_dir=str(session_dir), guest_mount=GUEST_MOUNT
    )
    subprocess.run(  # noqa: S603 -- argv is test-constructed, no user input
        ["bash", "-c", wrapped],  # noqa: S607 -- bash via PATH is fine in tests
        check=True,
        timeout=30,
    )
    with open("/proc/self/mountinfo", encoding="utf-8") as fh:
        mountinfo = fh.read()
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[4] == GUEST_MOUNT:
            assert str(session_dir) not in line, f"bind leaked to host: {line}"


@needs_mount_ns
def test_mounted_exec_host_mountpoint_gains_no_session_files(tmp_path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    marker = f"noleak-{os.getpid()}.txt"
    (session_dir / marker).write_text("x")
    wrapped = wrap_in_mount_namespace(
        f"cat {GUEST_MOUNT}/{marker}",
        session_dir=str(session_dir),
        guest_mount=GUEST_MOUNT,
    )
    proc = subprocess.run(  # noqa: S603 -- argv is test-constructed, no user input
        ["bash", "-c", wrapped],  # noqa: S607 -- bash via PATH is fine in tests
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "x"  # guest sees it via the bind
    assert not os.path.exists(os.path.join(GUEST_MOUNT, marker))  # host does not


@needs_mount_ns
def test_mounted_exec_no_residual_processes(tmp_path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    for _ in range(3):
        wrapped = wrap_in_mount_namespace(
            "true", session_dir=str(session_dir), guest_mount=GUEST_MOUNT
        )
        subprocess.run(  # noqa: S603 -- argv is test-constructed, no user input
        ["bash", "-c", wrapped],  # noqa: S607 -- bash via PATH is fine in tests
        check=True,
        timeout=30,
    )
    # No unshare processes left behind (per-exec namespaces die with the exec).
    ps = subprocess.run(  # noqa: S603 -- argv is test-constructed, no user input
        ["pgrep", "-f", str(session_dir)],  # noqa: S607 -- pgrep via PATH is fine in tests
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert ps.returncode != 0, f"residual processes: {ps.stdout}"


@pytest.mark.asyncio
@needs_mount_ns
async def test_exec_shell_mounted_mode_end_to_end(tmp_path) -> None:
    """_exec_shell in mounted mode: guest reads via /mnt/data, host paths
    never leak into outputs, LCA_GUEST_ROOT is the guest mount."""
    adapter = LocalSandboxAdapter(root=str(tmp_path), mount_namespace=True)
    (tmp_path / "marker.txt").write_text("hello-adapter")

    result = await adapter._exec_shell("cat /mnt/data/marker.txt")
    assert result.success, f"{result.exit_code} {result.stderr}"
    assert result.stdout.strip() == "hello-adapter"

    pwd_result = await adapter._exec_shell("pwd")
    assert pwd_result.success, pwd_result.stderr
    assert pwd_result.stdout.strip() == GUEST_MOUNT
    assert str(tmp_path) not in pwd_result.stdout

    root_result = await adapter._exec_shell("echo $LCA_GUEST_ROOT")
    assert root_result.success, root_result.stderr
    assert root_result.stdout.strip() == GUEST_MOUNT


@pytest.mark.asyncio
async def test_exec_shell_virtual_fallback_still_rewrites(tmp_path) -> None:
    """Explicit virtual mode: string rewriting, no unshare involved."""
    adapter = LocalSandboxAdapter(root=str(tmp_path), mount_namespace=False)
    (tmp_path / "marker.txt").write_text("hello-virtual")
    result = await adapter._exec_shell("cat /mnt/data/marker.txt")
    assert result.success, f"{result.exit_code} {result.stderr}"
    assert result.stdout.strip() == "hello-virtual"
