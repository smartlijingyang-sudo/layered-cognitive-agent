"""Host session-root paths are reverse-projected at the sandbox adapter exit.

``SandboxPaths`` is the single seam here: the adapter's ``_exec_shell``
rewrites guest references in the command text with
``paths.rewrite_command`` and projects the shell's stdout/stderr back with
``paths.present_text`` — so shell output that contains host absolute paths
is converted at the adapter exit to the guest view. The display projection
deliberately never rewrites free text (pinned by
``test_observation_surface_display_paths``), so the adapter exit is the one
place that converts them — the model never sees host absolute paths.
"""

from __future__ import annotations

import pytest

from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter
from lca.infrastructure.sandbox.paths.sandbox_paths import SandboxPaths


@pytest.mark.asyncio
async def test_shell_stdout_host_session_root_is_projected_to_guest_view(tmp_path) -> None:
    host_root = tmp_path / "host"
    host_root.mkdir()
    adapter = LocalSandboxAdapter(root=str(host_root))
    session = await adapter.create_session()
    assert session is not None

    result = await adapter.run_terminal("pwd", session_id=session.session_id)

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    session_root = str(host_root / ".sessions" / session.session_id)
    assert session_root not in result.stdout
    assert "/mnt/data" in result.stdout


@pytest.mark.asyncio
async def test_shell_stderr_host_session_root_is_projected_to_guest_view(tmp_path) -> None:
    host_root = tmp_path / "host"
    host_root.mkdir()
    adapter = LocalSandboxAdapter(root=str(host_root))
    session = await adapter.create_session()
    assert session is not None

    result = await adapter.run_terminal(
        "echo $LCA_GUEST_ROOT >&2",
        session_id=session.session_id,
    )

    session_root = str(host_root / ".sessions" / session.session_id)
    assert session_root not in result.stderr
    assert "/mnt/data" in result.stderr


def test_seam_present_text_leaves_sibling_prefix_paths_alone(tmp_path) -> None:
    """Boundary cases migrated 1:1 off the deleted adapter wrappers (RA-050).

    The wrappers were one-line delegates — ``SandboxPaths.for_local(root,
    guest_mount="/mnt/data").present_text(text)`` — so this drives the seam
    directly and keeps the coverage after the deletion.
    """
    root = str(tmp_path / "sess1")
    paths = SandboxPaths.for_local(root, guest_mount="/mnt/data")
    assert paths.present_text(f"{root}/x") == "/mnt/data/x"
    assert paths.present_text(root) == "/mnt/data"
    # Sibling paths that merely share the prefix are a different path.
    assert paths.present_text(f"{root}2/x") == f"{root}2/x"
    assert paths.present_text(f"{root}-backup") == f"{root}-backup"
    # No-op when the session root already is the guest mount.
    assert SandboxPaths.for_local("/mnt/data", guest_mount="/mnt/data").present_text("/mnt/data/x") == "/mnt/data/x"
    assert paths.present_text("") == ""
