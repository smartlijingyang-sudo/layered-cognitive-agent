"""DaemonService.stop 必须通过 sudo 终止 sandbox-user 的 daemon 进程。

回归：2026-10-06 之前，``stop()`` 用无 sudo 的 ``pkill``。调用用户
（lichao）无权信号 sandbox-user 进程，pkill 静默失败，导致
``daemon restart`` 后旧 daemon 残留，新旧两个进程抢同一 device id，
旧进程在 gateway 重启时崩溃。``stop()`` 必须走 ``Sudo.run``。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from lca.infrastructure.cli.config.config import DaemonConfig, KernelServeConfig
from lca.infrastructure.cli.services.daemon.daemon import DaemonService


def test_stop_kills_daemon_via_sudo(tmp_path: Path) -> None:
    sudo = MagicMock()
    svc = DaemonService(
        config=DaemonConfig(),
        kernel_serve=KernelServeConfig(),
        state_dir=tmp_path,
        root=tmp_path,
        sudo=sudo,
    )
    # No pid file recorded -> _kill_existing skips the wait-for-exit poll.
    sudo.read_text.return_value = None

    svc.stop()

    sudo.run.assert_called_once_with(
        ["pkill", "-u", "sandbox-user", "-f", "node.*index.js.*connect"],
        timeout=10,
    )
    sudo.rm.assert_called_once_with(Path("/home/sandbox-user/.lca/connect.pid"))
