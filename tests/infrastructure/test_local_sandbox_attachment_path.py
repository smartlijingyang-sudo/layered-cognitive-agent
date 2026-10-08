"""A staged attachment must open at the path the tool surface advertises.

``SandboxRuntime._stage_files`` stages run attachments under the run's
session root, and the local adapter rewrites guest ``/mnt/data`` references
in shell commands onto that same session root — so the agent's ``/mnt/data``
is its own assistant directory and the shared host mount stays invisible.
``activate_skill`` still advertises ``/mnt/data/<name>`` as the virtual name;
the command rewrite (and the ``LCA_GUEST_ROOT`` knob for code) resolves it.

The cases below pin the session-root contract on both the production shape
(host dir == guest mount) and the fallback shape (host root != mount):
staging lands in ``.sessions/<sid>/``, never at the shared mount root, and
per-session workspaces stay isolated from each other.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.state.guest_layout import GuestLayout
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter

ATTACHMENT = "快乐通宝会员标签模型定义3.0.xlsx"


def _mount_backed_adapter(tmp_path) -> LocalSandboxAdapter:
    """Production shape: the host directory backing the guest mount is ``tmp_path``."""
    return LocalSandboxAdapter(root=str(tmp_path), layout=GuestLayout.from_root(str(tmp_path)))


def _session_root(tmp_path, session_id: str):
    return tmp_path / ".sessions" / session_id


@pytest.mark.asyncio
async def test_run_command_opens_attachment_staged_in_session_root(tmp_path) -> None:
    """Staging follows the session: the file lands under the session root,
    the shared mount root stays clean, and the mount reference in the shell
    command round-trips through the rewrite onto the staged file."""
    adapter = _mount_backed_adapter(tmp_path)
    session = await adapter.create_session()
    assert session is not None
    session_root = _session_root(tmp_path, session.session_id)

    staged = await adapter.write_files(
        {ATTACHMENT: b"workbook-bytes"},
        base_dir=str(tmp_path),
        session_id=session.session_id,
    )
    assert staged.success, staged.error

    # New contract: session-root staging; the shared mount root is invisible.
    assert (session_root / ATTACHMENT).is_file()
    assert not (tmp_path / ATTACHMENT).exists()

    result = await adapter.run_terminal(
        f"cat {tmp_path}/{ATTACHMENT}", session_id=session.session_id
    )

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    assert "workbook-bytes" in result.stdout


@pytest.mark.asyncio
async def test_shell_and_code_agree_on_the_session_root(tmp_path) -> None:
    """``runCommand`` (via the mount-reference rewrite) and ``executeCode``
    (via ``LCA_GUEST_ROOT``) must resolve the advertised attachment path to
    the same session-root file."""
    adapter = _mount_backed_adapter(tmp_path)
    session = await adapter.create_session()
    assert session is not None
    await adapter.write_files(
        {ATTACHMENT: b"workbook-bytes"},
        base_dir=str(tmp_path),
        session_id=session.session_id,
    )

    shell = await adapter.run_terminal(
        f"cat {tmp_path}/{ATTACHMENT}", session_id=session.session_id
    )
    code = await adapter.run_in_session(
        session.session_id,
        "import os\n"
        "root = os.environ['LCA_GUEST_ROOT']\n"
        f"data = open(os.path.join(root, {ATTACHMENT!r}), 'rb').read()\n"
        "print(data.decode())\n",
        language="python",
    )

    assert shell.success, f"{shell.exit_code} {shell.stderr} {shell.error}"
    assert code.success, f"{code.exit_code} {code.stderr} {code.error}"
    assert "workbook-bytes" in shell.stdout
    assert "workbook-bytes" in code.stdout


@pytest.mark.asyncio
async def test_session_root_scopes_relative_writes_and_hides_host_paths(tmp_path) -> None:
    """Per-session isolation survives the display projection: relative writes
    stay in the session's own tree (harvestable per run), the host session
    path never leaks into what the agent sees, and sibling sessions stay
    isolated from each other."""
    adapter = LocalSandboxAdapter(root=str(tmp_path))
    session = await adapter.create_session()
    assert session is not None
    session_root = _session_root(tmp_path, session.session_id)

    result = await adapter.run_terminal(
        "pwd && touch outputs/report.pdf && ls outputs", session_id=session.session_id
    )

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    # RA-040 projects the host session path back to the guest view, so the
    # agent sees /mnt/data — never the real host directory.
    assert str(session_root) not in result.stdout
    assert "/mnt/data" in result.stdout
    assert "report.pdf" in result.stdout
    # ...but on the host the file really landed in this session's tree.
    assert (session_root / "outputs" / "report.pdf").is_file()

    other = await adapter.create_session()
    assert other is not None
    assert not (_session_root(tmp_path, other.session_id) / "outputs" / "report.pdf").exists()


@pytest.mark.asyncio
async def test_mount_reference_in_command_maps_onto_session_root(tmp_path) -> None:
    """Fallback shape (host root != guest mount): a session-staged file is
    openable from a session command via the advertised ``/mnt/data`` path,
    and never lands on the shared host root."""
    adapter = LocalSandboxAdapter(root=str(tmp_path))
    session = await adapter.create_session()
    assert session is not None
    session_root = _session_root(tmp_path, session.session_id)

    staged = await adapter.write_files(
        {ATTACHMENT: b"workbook-bytes"},
        base_dir="/mnt/data",
        session_id=session.session_id,
    )
    assert staged.success, staged.error

    assert (session_root / ATTACHMENT).is_file()
    assert not (tmp_path / ATTACHMENT).exists()

    result = await adapter.run_terminal(
        f"cat /mnt/data/{ATTACHMENT}", session_id=session.session_id
    )

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    assert "workbook-bytes" in result.stdout
