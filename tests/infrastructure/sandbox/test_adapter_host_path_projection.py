"""Host session-root paths are reverse-projected at the sandbox adapter exit.

``LocalSandboxAdapter._rewrite_command`` maps the guest mount (``/mnt/data``)
onto the host session root inside the command text, so the shell's
stdout/stderr come back containing host absolute paths. The display
projection deliberately never rewrites free text (pinned by
``test_observation_surface_display_paths``), so the adapter exit projects
them back to the guest view — the model never sees host absolute paths.
"""

from __future__ import annotations

import pytest

from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter


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


def test_project_host_to_guest_leaves_sibling_prefix_paths_alone(tmp_path) -> None:
    adapter = LocalSandboxAdapter(root=str(tmp_path / "host"))
    root = str(tmp_path / "sess1")
    assert adapter._project_host_to_guest(f"{root}/x", root) == "/mnt/data/x"
    assert adapter._project_host_to_guest(root, root) == "/mnt/data"
    # Sibling paths that merely share the prefix are a different path.
    assert adapter._project_host_to_guest(f"{root}2/x", root) == f"{root}2/x"
    assert adapter._project_host_to_guest(f"{root}-backup", root) == f"{root}-backup"
    # No-op when the session root already is the guest mount.
    assert adapter._project_host_to_guest("/mnt/data/x", "/mnt/data") == "/mnt/data/x"
    assert adapter._project_host_to_guest("", root) == ""
