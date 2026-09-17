"""A staged attachment must open at the path the tool surface advertises.

``SandboxRuntime._stage_files`` writes run attachments to the guest mount
root and ``activate_skill`` tells the model they are ready at
``/mnt/data/<name>``. The local adapter used to rewrite every mount
reference in a *shell command* onto the per-session cwd, so ``runCommand``
answered ``File not found`` for a path ``executeCode`` (whose paths live in
the code body, which is never rewritten) read fine — ``run_b695b0b85115``
burned a turn on exactly that.

The production local layout has the host directory *be* the guest mount
(``default_local_root()`` prefers a writable ``/mnt/data``), so the
path-resolution cases below pin that shape; the session-scoping case keeps
the fallback shape where host root and mount differ and rewriting is needed.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.state.guest_layout import GuestLayout
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter

ATTACHMENT = "快乐通宝会员标签模型定义3.0.xlsx"


def _mount_backed_adapter(tmp_path) -> LocalSandboxAdapter:
    """Production shape: the host directory backing the guest mount is ``tmp_path``."""
    return LocalSandboxAdapter(root=str(tmp_path), layout=GuestLayout.from_root(str(tmp_path)))


@pytest.mark.asyncio
async def test_run_command_opens_attachment_staged_at_the_mount_root(tmp_path) -> None:
    adapter = _mount_backed_adapter(tmp_path)
    session = await adapter.create_session()
    assert session is not None

    staged = await adapter.write_files({ATTACHMENT: b"workbook-bytes"}, base_dir=str(tmp_path))
    assert staged.success, staged.error

    result = await adapter.run_terminal(
        f"cat {tmp_path}/{ATTACHMENT}", session_id=session.session_id
    )

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    assert "workbook-bytes" in result.stdout


@pytest.mark.asyncio
async def test_shell_and_code_agree_on_the_same_absolute_path(tmp_path) -> None:
    """``runCommand`` and ``executeCode`` must resolve one advertised path identically."""
    adapter = _mount_backed_adapter(tmp_path)
    session = await adapter.create_session()
    assert session is not None
    await adapter.write_files({ATTACHMENT: b"workbook-bytes"}, base_dir=str(tmp_path))

    shell = await adapter.run_terminal(
        f"cat {tmp_path}/{ATTACHMENT}", session_id=session.session_id
    )
    code = await adapter.run_in_session(
        session.session_id,
        f"print(open({str(tmp_path / ATTACHMENT)!r},'rb').read().decode())",
        language="python",
    )

    assert shell.success, f"{shell.exit_code} {shell.stderr} {shell.error}"
    assert code.success, f"{code.exit_code} {code.stderr} {code.error}"
    assert "workbook-bytes" in shell.stdout
    assert "workbook-bytes" in code.stdout


@pytest.mark.asyncio
async def test_session_root_still_scopes_relative_writes(tmp_path) -> None:
    """The fix must not merge per-session workspaces: relative paths stay session-scoped.

    Fallback shape (host root != guest mount): the mount reference in the
    command is rewritten onto the host root, while the cwd stays the session
    directory so ``outputs/`` harvests per run.
    """
    adapter = LocalSandboxAdapter(root=str(tmp_path))
    session = await adapter.create_session()
    assert session is not None

    result = await adapter.run_terminal(
        "pwd && touch outputs/report.pdf && ls outputs", session_id=session.session_id
    )

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    assert str(tmp_path / ".sessions" / session.session_id) in result.stdout
    assert "report.pdf" in result.stdout


@pytest.mark.asyncio
async def test_mount_reference_in_command_maps_onto_host_root_not_session(tmp_path) -> None:
    """Fallback shape: a staged mount-root file stays openable from a session command."""
    adapter = LocalSandboxAdapter(root=str(tmp_path))
    session = await adapter.create_session()
    assert session is not None
    staged = await adapter.write_files({ATTACHMENT: b"workbook-bytes"}, base_dir="/mnt/data")
    assert staged.success, staged.error

    result = await adapter.run_terminal(
        f"cat /mnt/data/{ATTACHMENT}", session_id=session.session_id
    )

    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"
    assert "workbook-bytes" in result.stdout
