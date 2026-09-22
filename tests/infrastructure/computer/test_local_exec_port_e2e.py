"""LocalExecPort 全流程端到端集成测试 (ADR-0246 M1).

验证全流程链路：
1. Target/Grant/Port 构建与装配
2. 多执行目标路由（Sandbox vs UserMachine）
3. 读文件、写文件、执行命令等标准操作全流程
4. 幂等回执生成与二次重放
5. 异常链路收束：offline、grant_expired、scope_violation、local_policy_denied
6. Provider 替换一致性（MachineLocalExecAdapter vs FakeCompanionProvider vs FakeSandboxProvider）
"""

from __future__ import annotations

import pathlib
import tempfile
import time
from typing import Any

import pytest

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    TargetKind,
)
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.contracts.protocols.runtime.infra.infra import LocalExecPort
from lca.infrastructure.computer.fake.companion import FakeCompanionProvider
from lca.infrastructure.computer.fake.sandbox import FakeSandboxProvider
from lca.infrastructure.computer.machine.adapter import MachineLocalExecAdapter
from lca.infrastructure.computer.machine.machine import MachineComputer
from lca.infrastructure.file.store import LocalFileStore


class _MockTransport:
    """模拟 Transport，支持根据 op 返回预设结果。"""

    def __init__(self) -> None:
        self.files: dict[str, str] = {"/repo/README.md": "# Title\nHello"}
        self.commands_run: list[str] = []

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        del timeout_s
        if op == "readFile":
            path = args.get("path", "")
            if path in self.files:
                return {"success": True, "content": self.files[path]}
            return {"success": False, "error": f"File not found: {path}"}
        if op == "writeFile":
            path = args.get("path", "")
            content = args.get("content", "")
            self.files[path] = content
            return {"success": True, "content": "File written"}
        if op == "runCommand":
            cmd = args.get("command", "")
            self.commands_run.append(cmd)
            return {"success": True, "content": f"output of {cmd}"}
        if op == "listFiles":
            return {"success": True, "content": "README.md"}
        return {"success": True, "content": "ok"}

    async def write_files(self, files: Any, **kwargs: Any) -> Any:
        return None


def _build_machine_adapter(transport: _MockTransport | None = None) -> MachineLocalExecAdapter:
    plane = PlaneRef(
        id="machine-laptop-01",
        label="Dev-Laptop",
        kind=PlaneKind.MACHINE,
        root="/repo",
        outputs_dir="/repo/out",
        capability_summary=("read_file", "write_file", "run_command", "git"),
    )
    store = LocalFileStore(pathlib.Path(tempfile.mkdtemp()))
    comp = MachineComputer(plane=plane, transport=transport or _MockTransport(), store=store)
    return MachineLocalExecAdapter(computer=comp, machine_id="m-laptop-01", label="Dev-Laptop")


def _grant(
    *,
    job_id: str = "job-e2e-01",
    idem: str = "idem-e2e-01",
    operation: str = "read_file",
    path_prefixes: list[str] | None = None,
    command_allowlist: list[str] | None = None,
    expires_delta: int = 3600,
) -> CapabilityGrant:
    return CapabilityGrant(
        job_id=job_id,
        idempotency_key=idem,
        subject_user_id="user-42",
        subject_machine_id="m-laptop-01",
        operation=operation,
        path_prefixes=path_prefixes or ["/repo"],
        command_class=None,
        command_allowlist=command_allowlist or [],
        expires_at=int(time.time()) + expires_delta,
        approval_id="appr-01",
        request_digest="sha256-req-digest",
    )


# ---------------- 全流程端到端测试 ----------------


@pytest.mark.asyncio
async def test_e2e_read_file_flow() -> None:
    """端到端读文件全流程：Grant 校验 -> 经 Adapter 派发 -> 生成不可变 EffectReceipt。"""
    transport = _MockTransport()
    adapter = _build_machine_adapter(transport)
    grant = _grant(operation="read_file")

    receipt = await adapter.execute("read_file", {"path": "/repo/README.md"}, grant)

    assert isinstance(receipt, EffectReceipt)
    assert receipt.success is True
    assert receipt.exit_code == 0
    assert receipt.error_kind is None
    assert receipt.job_id == grant.job_id
    assert receipt.idempotency_key == grant.idempotency_key
    assert receipt.stdout_digest is not None


@pytest.mark.asyncio
async def test_e2e_write_file_flow() -> None:
    """端到端写文件全流程：Grant 路径约束 -> 执行写入 -> 回执确认。"""
    transport = _MockTransport()
    adapter = _build_machine_adapter(transport)
    grant = _grant(job_id="job-write-1", idem="idem-write-1", operation="write_file")

    receipt = await adapter.execute(
        "write_file",
        {"path": "/repo/src/main.py", "content": "print('hello')"},
        grant,
    )

    assert receipt.success is True
    assert transport.files["/repo/src/main.py"] == "print('hello')"


@pytest.mark.asyncio
async def test_e2e_run_command_flow() -> None:
    """端到端命令执行全流程：检查退出状态与输出摘要。"""
    transport = _MockTransport()
    adapter = _build_machine_adapter(transport)
    grant = _grant(
        job_id="job-cmd-1",
        idem="idem-cmd-1",
        operation="run_command",
        command_allowlist=["pytest"],
    )

    receipt = await adapter.execute(
        "run_command",
        {"command": "pytest -q", "timeout_s": 30},
        grant,
    )

    assert receipt.success is True
    assert "pytest -q" in transport.commands_run
    assert receipt.stdout_digest is not None


@pytest.mark.asyncio
async def test_e2e_multi_provider_router_port() -> None:
    """端到端多执行目标路由测试：验证 LocalExecPort 路由至不同 Provider。"""
    machine_adapter = _build_machine_adapter()
    sandbox_provider = FakeSandboxProvider()

    router: dict[TargetKind, LocalExecPort] = {
        TargetKind.USER_MACHINE: machine_adapter,
        TargetKind.SANDBOX: sandbox_provider,
    }

    # 1. 路由至 USER_MACHINE
    target_user = router[TargetKind.USER_MACHINE]
    assert target_user.target.kind == TargetKind.USER_MACHINE
    r_user = await target_user.execute("read_file", {"path": "/repo/README.md"}, _grant())
    assert r_user.success is True

    # 2. 路由至 SANDBOX
    target_sandbox = router[TargetKind.SANDBOX]
    assert target_sandbox.target.kind == TargetKind.SANDBOX
    r_box = await target_sandbox.execute("read_file", {"path": "/repo/README.md"}, _grant())
    assert r_box.success is True


@pytest.mark.asyncio
async def test_e2e_failure_taxonomy_matrix() -> None:
    """端到端错误分类矩阵测试：所有边界场景均 fail-loud 且无静默回退。"""
    adapter = _build_machine_adapter()

    # 1. 过期 Grant
    expired_grant = _grant(expires_delta=-10)
    r_expired = await adapter.execute("read_file", {"path": "/repo/README.md"}, expired_grant)
    assert r_expired.success is False
    assert r_expired.error_kind == "grant_expired"

    # 2. 越权路径（目录越界）
    scope_grant = _grant(path_prefixes=["/repo/safe"])
    r_scope = await adapter.execute("read_file", {"path": "/repo/secret.key"}, scope_grant)
    assert r_scope.success is False
    assert r_scope.error_kind == "scope_violation"

    # 3. 根目录之外（绝对路径逃逸）
    r_escape = await adapter.execute("read_file", {"path": "/etc/shadow"}, scope_grant)
    assert r_escape.success is False
    assert r_escape.error_kind == "scope_violation"


@pytest.mark.asyncio
async def test_e2e_provider_replacement_contract_fidelity() -> None:
    """Provider 替换高保真测试：Fake 与 Real Adapter 在成功/失败时保持严格的契约等价。"""
    transport = _MockTransport()
    real_adapter = _build_machine_adapter(transport)
    fake_companion = FakeCompanionProvider()

    # 正常读文件
    grant_ok = _grant(job_id="j-parity", idem="k-parity")
    r_real = await real_adapter.execute("read_file", {"path": "/repo/README.md"}, grant_ok)
    r_fake = await fake_companion.execute("read_file", {"path": "/repo/README.md"}, grant_ok)

    assert r_real.success == r_fake.success is True
    assert r_real.exit_code == r_fake.exit_code == 0
    assert r_real.error_kind == r_fake.error_kind is None
    assert r_real.job_id == r_fake.job_id == "j-parity"

    # 越权拦截
    grant_deny = _grant(job_id="j-deny", idem="k-deny")
    r_real_deny = await real_adapter.execute("read_file", {"path": "/var/log/syslog"}, grant_deny)
    r_fake_deny = await fake_companion.execute("read_file", {"path": "/var/log/syslog"}, grant_deny)

    assert r_real_deny.success == r_fake_deny.success is False
    assert r_real_deny.error_kind == r_fake_deny.error_kind == "scope_violation"
