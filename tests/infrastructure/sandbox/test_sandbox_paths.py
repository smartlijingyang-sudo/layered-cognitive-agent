"""Property tests pinning the SandboxPaths invariants (todo-81).

The single seam between the agent-visible guest namespace (``/mnt/data``)
and the host layout. Three invariants, tested — not hoped:

- round-trip: ``present(resolve(p)) == p``
- containment: ``resolve`` never escapes the session host root (fail-closed)
- totality: paths outside the guest namespace raise, never pass through
"""

from __future__ import annotations

import pytest

from lca.infrastructure.sandbox.paths import (
    PathEscapeError,
    SandboxPaths,
    UnresolvableAgentPathError,
)

_HOST = "/fake/host/sess-1"


def _local() -> SandboxPaths:
    return SandboxPaths.for_local(_HOST)


# ----------------------------------------------------------------------
# round-trip
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_path",
    [
        "/mnt/data",
        "/mnt/data/file.txt",
        "/mnt/data/sub/dir/file.txt",
        "/mnt/data/.lca/background/job.json",
        "/mnt/data/outputs/report.pdf",
        # CJK names ride through unchanged (todo-79 regression area).
        "/mnt/data/\u5feb\u4e50\u901a\u5b9d\u4f1a\u5458\u6807\u7b7e\u6a21\u578b\u5b9a\u4e493.0.xlsx",
        "/mnt/data/a b/c+d/e_f.txt",
    ],
)
def test_round_trip(agent_path: str) -> None:
    paths = _local()
    assert paths.present(paths.resolve(agent_path)) == agent_path


def test_round_trip_mount_itself() -> None:
    paths = _local()
    assert paths.present(paths.resolve("/mnt/data")) == "/mnt/data"
    assert paths.present(paths.resolve("/mnt/data/")) == "/mnt/data"


def test_identity_round_trip() -> None:
    paths = SandboxPaths.identity()
    assert paths.present(paths.resolve("/mnt/data/a/b")) == "/mnt/data/a/b"


# ----------------------------------------------------------------------
# containment (fail-closed)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_path",
    [
        "/mnt/data/sub/../../..",
        "/mnt/data/../etc",
        "/mnt/data/a/../../../../etc/passwd",
    ],
)
def test_resolve_never_escapes_host_root(agent_path: str) -> None:
    with pytest.raises(PathEscapeError):
        _local().resolve(agent_path)


# ----------------------------------------------------------------------
# totality (explicit error, no silent passthrough)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_path",
    [
        "/etc/passwd",
        "/fake/evil",
        "/mnt/data2/x",  # sibling prefix is a different namespace
        "/",
        "relative/path",
        "",
    ],
)
def test_resolve_rejects_outside_guest_namespace(agent_path: str) -> None:
    with pytest.raises(UnresolvableAgentPathError):
        _local().resolve(agent_path)


# ----------------------------------------------------------------------
# present (observation side)
# ----------------------------------------------------------------------


def test_present_maps_host_root_and_children() -> None:
    paths = _local()
    assert paths.present(_HOST) == "/mnt/data"
    assert paths.present(f"{_HOST}/a/b.txt") == "/mnt/data/a/b.txt"


def test_present_leaves_foreign_paths_alone() -> None:
    paths = _local()
    assert paths.present("/fake/host/sess-12/x") == "/fake/host/sess-12/x"
    assert paths.present("/etc/passwd") == "/etc/passwd"


# ----------------------------------------------------------------------
# text-level adapters
# ----------------------------------------------------------------------


def test_rewrite_command_rewrites_guest_mount_tokens() -> None:
    paths = _local()
    assert paths.rewrite_command("cat /mnt/data/foo.txt") == f"cat {_HOST}/foo.txt"
    assert paths.rewrite_command('echo "/mnt/data/a" \'/mnt/data/b\'') == f"echo \"{_HOST}/a\" '{_HOST}/b'"
    assert paths.rewrite_command("cat /mnt/data") == f"cat {_HOST}"
    assert paths.rewrite_command("") == ""


def test_rewrite_command_leaves_sibling_prefix_tokens_alone() -> None:
    # The old blind str.replace turned /mnt/data2 into <root>2. Token-aware
    # rewriting must not.
    paths = _local()
    assert paths.rewrite_command("cat /mnt/data2/x") == "cat /mnt/data2/x"
    assert paths.rewrite_command("ls /mnt/data-backup") == "ls /mnt/data-backup"


def test_rewrite_command_identity_is_noop() -> None:
    paths = SandboxPaths.identity()
    assert paths.rewrite_command("cat /mnt/data/foo") == "cat /mnt/data/foo"


def test_present_text_projects_host_root_back() -> None:
    paths = _local()
    assert paths.present_text(f"wrote {_HOST}/out.txt") == "wrote /mnt/data/out.txt"
    assert paths.present_text(_HOST) == "/mnt/data"
    assert paths.present_text("") == ""


def test_present_text_leaves_sibling_prefix_paths_alone() -> None:
    paths = _local()
    assert paths.present_text(f"{_HOST}2/x") == f"{_HOST}2/x"
    assert paths.present_text(f"{_HOST}-backup") == f"{_HOST}-backup"


def test_present_text_identity_is_noop() -> None:
    paths = SandboxPaths.identity()
    assert paths.present_text("wrote /mnt/data/out.txt") == "wrote /mnt/data/out.txt"


# ----------------------------------------------------------------------
# construction
# ----------------------------------------------------------------------


def test_host_root_is_normalized() -> None:
    paths = SandboxPaths.for_local("/fake/host/sess-1/")
    assert str(paths.host_root) == "/fake/host/sess-1"
    assert paths.guest_mount == "/mnt/data"


def test_relative_host_root_rejected() -> None:
    with pytest.raises(ValueError):
        SandboxPaths.for_local("relative/dir")


def test_relative_guest_mount_rejected() -> None:
    with pytest.raises(ValueError):
        SandboxPaths.for_local("/fake/x", guest_mount="mnt/data")
