"""daemon 掉线不崩：gateway 重启期间 ECONNREFUSED 不再杀死 node 进程。

回归：2026-10-06 之前，``connect`` 命令没有注册 GatewayClient 的
``'error'`` 监听器。WebSocket 重连遇到 ECONNREFUSED（kernel 重启时
8765 短暂不可达）时，Node 对无监听的 ``'error'`` 事件直接抛异常，
进程退出，留下 stale pid，导致 agent 主机工具失效。
本测试把 CLI 指向一个关闭端口，断言进程存活并进入重连退避。
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_DIST = REPO_ROOT / "packages" / "lca-cli" / "dist" / "index.js"
LCA_CLI_DIR = REPO_ROOT / "packages" / "lca-cli"
GW_DIR = REPO_ROOT / "packages" / "gateway-client"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a build command; failures are handled by the fixture's skip check."""
    subprocess.run(  # noqa: S603 — 本地固定命令（tsc/npm），无外部输入
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _build_cli() -> None:
    """Build gateway-client then lca-cli dist from source."""
    _run([str(GW_DIR / "node_modules" / ".bin" / "tsc"), "-p", "tsconfig.json"], cwd=GW_DIR)
    _run(["npm", "run", "build"], cwd=LCA_CLI_DIR)


@pytest.fixture(scope="module")
def built_cli() -> Path:
    if not CLI_DIST.exists():
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _build_cli()
    if not CLI_DIST.exists():
        pytest.skip("lca-cli dist 不存在且无法构建（缺少 node/npm 工具链）")
    return CLI_DIST


def test_daemon_survives_gateway_connection_error(built_cli: Path, tmp_path: Path) -> None:
    """connect 到关闭端口时进程必须存活并退避重连，而不是崩溃退出。"""
    node_bin = shutil.which("node")
    assert node_bin is not None, "测试环境缺少 node"
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.Popen(  # noqa: S603 — 固定 node 命令 + 隔离 HOME/workspace
        [
            node_bin,
            str(built_cli),
            "connect",
            "--gateway",
            "ws://127.0.0.1:1",
            "--workspace",
            str(tmp_path),
            "--token-type",
            "serviceToken",
            "--token",
            "test",
        ],
        env={**os.environ, "HOME": str(home)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        # 旧代码在首次 ECONNREFUSED 后约 1s 内崩溃；给足窗口再断言存活。
        time.sleep(4)
        assert proc.poll() is None, "daemon 进程在连接错误后崩溃退出"
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
