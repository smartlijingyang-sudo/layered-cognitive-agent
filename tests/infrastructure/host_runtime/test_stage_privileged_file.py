"""RA-015: the privileged-file staging seam pins its sudo call sequence.

The tempfile -> sudo cp -> unlink -> chmod/chown ceremony lives exactly once,
in ``_stage_privileged_file``. A fake ``run_sudo`` records the sequence so any
future change to the ritual (backup-before-write, post-write verify) shows up
here first.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.host_runtime.providers.user_cli import _stage_privileged_file


class _FakeSudo:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> None:
        self.commands.append(cmd)


def _staging_tempfile(sudo: _FakeSudo) -> Path:
    """The tempfile named in the cp command."""
    assert sudo.commands[0][0] == "cp"
    return Path(sudo.commands[0][1])


def test_sequence_with_owner_and_mode(tmp_path: Path) -> None:
    sudo = _FakeSudo()
    dest = tmp_path / "tool"
    _stage_privileged_file(sudo, "#!/bin/sh\necho hi\n", dest, owner="alice:alice", mode="+x")
    assert sudo.commands == [
        ["cp", str(_staging_tempfile(sudo)), str(dest)],
        ["chown", "alice:alice", str(dest)],
        ["chmod", "+x", str(dest)],
    ]
    # unlink discipline: the staging tempfile never stays on disk
    assert not _staging_tempfile(sudo).exists()


def test_sequence_skips_owner_and_mode_when_none(tmp_path: Path) -> None:
    sudo = _FakeSudo()
    dest = tmp_path / "tool"
    _stage_privileged_file(sudo, "content", dest)
    assert [c[0] for c in sudo.commands] == ["cp"]
    assert not _staging_tempfile(sudo).exists()


def test_ensure_wrapper_delegates_to_seam(tmp_path: Path, monkeypatch) -> None:
    """_ensure_wrapper routes through the staging seam (fake run_sudo via seam)."""
    from lca.infrastructure.host_runtime.config import HostRuntimeConfig, UserConfig
    from lca.infrastructure.host_runtime.providers.user_cli import CLIProvider

    provider = CLIProvider(HostRuntimeConfig(), user=UserConfig(name="sandbox-user"))
    provider.config.paths.tool_dir = str(tmp_path)
    sudo = _FakeSudo()
    provider.run_sudo = sudo  # type: ignore[method-assign]

    provider._ensure_wrapper()

    dest = tmp_path / "lca"
    assert [c[0] for c in sudo.commands] == ["cp", "chmod"]
    assert sudo.commands[0][2] == str(dest)
    assert sudo.commands[1] == ["chmod", "+x", str(dest)]
    # wrapper content is staged intact through the tempfile
    assert sudo.commands[0][1].endswith(".sh")


def test_ensure_wrapper_skips_existing_wrapper(tmp_path: Path) -> None:
    from lca.infrastructure.host_runtime.config import HostRuntimeConfig, UserConfig
    from lca.infrastructure.host_runtime.providers.user_cli import CLIProvider

    provider = CLIProvider(HostRuntimeConfig(), user=UserConfig(name="sandbox-user"))
    provider.config.paths.tool_dir = str(tmp_path)
    (tmp_path / "lca").write_text("#!/bin/sh\n")
    sudo = _FakeSudo()
    provider.run_sudo = sudo  # type: ignore[method-assign]

    provider._ensure_wrapper()

    assert sudo.commands == []
