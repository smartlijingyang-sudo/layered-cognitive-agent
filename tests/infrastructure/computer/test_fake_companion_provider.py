"""FakeCompanionProvider — ADR-0246 §6 M1 验收测试。

覆盖 M1 全流程要求：
- happy path
- offline (I-UMS-1)
- deny (本地策略拒绝)
- expired (I-UMS-3)
- timeout (执行超时)
- cancel (任务取消)
- scope_violation (I-UMS-3)
- duplicate job (I-UMS-6 幂等重放)
- provider replacement (Provider 替换一致性)
- target kind (I-UMS-5 目标区分)
"""

from __future__ import annotations

import time

import pytest

from lca.contracts.models.core.execution.local_exec import CapabilityGrant, TargetKind
from lca.infrastructure.computer.fake.companion import FakeCompanionProvider
from lca.infrastructure.computer.fake.sandbox import FakeSandboxProvider


def _grant(
    *,
    job_id: str = "j-1",
    idem: str = "k-1",
    path_prefixes: list[str] | None = None,
    expires_delta: int = 3600,
    operation: str = "read_file",
) -> CapabilityGrant:
    return CapabilityGrant(
        job_id=job_id,
        idempotency_key=idem,
        subject_user_id="u-1",
        subject_machine_id="m-1",
        operation=operation,
        path_prefixes=path_prefixes or ["/repo"],
        command_class=None,
        command_allowlist=[],
        expires_at=int(time.time()) + expires_delta,
        approval_id=None,
        request_digest="digest-1",
    )


@pytest.mark.asyncio
async def test_happy_path() -> None:
    provider = FakeCompanionProvider()
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant())
    assert receipt.success is True
    assert receipt.exit_code == 0
    assert receipt.error_kind is None


@pytest.mark.asyncio
async def test_offline_fail_loud() -> None:
    """I-UMS-1: offline 必须 fail-loud，禁止静默回落。"""
    provider = FakeCompanionProvider(mode="offline")
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "device_offline"


@pytest.mark.asyncio
async def test_deny_fail_loud() -> None:
    """本地策略拒绝必须 fail-loud。"""
    provider = FakeCompanionProvider(mode="deny")
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "local_policy_denied"


@pytest.mark.asyncio
async def test_grant_expired_fail_loud() -> None:
    """I-UMS-3: Grant 过期必须 fail-loud。"""
    provider = FakeCompanionProvider()
    receipt = await provider.execute(
        "read_file", {"path": "/repo/a.py"}, _grant(expires_delta=-1)
    )
    assert receipt.success is False
    assert receipt.error_kind == "grant_expired"


@pytest.mark.asyncio
async def test_timeout_fail_loud() -> None:
    """执行超时必须 fail-loud。"""
    provider = FakeCompanionProvider(mode="timeout")
    receipt = await provider.execute("run_command", {"command": "sleep 100"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "timeout"


@pytest.mark.asyncio
async def test_cancel_fail_loud() -> None:
    """任务取消必须返回 cancelled 回执。"""
    provider = FakeCompanionProvider(mode="cancel")
    receipt = await provider.execute("run_command", {"command": "sleep 100"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "cancelled"


@pytest.mark.asyncio
async def test_scope_violation_fail_loud() -> None:
    """I-UMS-3: 路径越界必须 fail-loud。"""
    provider = FakeCompanionProvider()
    receipt = await provider.execute("read_file", {"path": "/etc/passwd"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "scope_violation"


@pytest.mark.asyncio
async def test_idempotent_replay() -> None:
    """I-UMS-6: 重复投递必须返回原 receipt，只执行一次。"""
    provider = FakeCompanionProvider()
    grant = _grant(job_id="j-idem", idem="k-idem")
    r1 = await provider.execute("read_file", {"path": "/repo/a.py"}, grant)
    r2 = await provider.execute("read_file", {"path": "/repo/a.py"}, grant)
    assert r1 == r2
    assert provider.execution_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_error_kind"),
    [
        ("offline", "device_offline"),
        ("deny", "local_policy_denied"),
        ("timeout", "timeout"),
        ("cancel", "cancelled"),
    ],
)
async def test_provider_replacement_consistent_error_shapes(
    mode: str, expected_error_kind: str
) -> None:
    """替换测试：FakeCompanionProvider 与 FakeSandboxProvider 各种错误形状完全对称。"""
    grant = _grant(path_prefixes=["/repo"])
    companion = FakeCompanionProvider(mode=mode)  # type: ignore[arg-type]
    sandbox = FakeSandboxProvider(mode=mode)  # type: ignore[arg-type]
    r_c = await companion.execute("read_file", {"path": "/repo/a.py"}, grant)
    r_s = await sandbox.execute("read_file", {"path": "/repo/a.py"}, grant)
    assert r_c.error_kind == r_s.error_kind == expected_error_kind
    assert r_c.success is False
    assert r_s.success is False


@pytest.mark.asyncio
async def test_provider_replacement_scope_violation() -> None:
    """替换测试：路径越界在两个 Provider 间保持相同的 scope_violation 错误。"""
    grant = _grant(path_prefixes=["/repo"])
    companion = FakeCompanionProvider()
    sandbox = FakeSandboxProvider()
    r_c = await companion.execute("read_file", {"path": "/etc/passwd"}, grant)
    r_s = await sandbox.execute("read_file", {"path": "/etc/passwd"}, grant)
    assert r_c.error_kind == r_s.error_kind == "scope_violation"


@pytest.mark.asyncio
async def test_provider_replacement_grant_expired() -> None:
    """替换测试：Grant 过期在两个 Provider 间保持相同的 grant_expired 错误。"""
    grant = _grant(expires_delta=-1)
    companion = FakeCompanionProvider()
    sandbox = FakeSandboxProvider()
    r_c = await companion.execute("read_file", {"path": "/repo/a.py"}, grant)
    r_s = await sandbox.execute("read_file", {"path": "/repo/a.py"}, grant)
    assert r_c.error_kind == r_s.error_kind == "grant_expired"


def test_target_kind_is_user_machine() -> None:
    assert FakeCompanionProvider().target.kind == TargetKind.USER_MACHINE
    assert FakeSandboxProvider().target.kind == TargetKind.SANDBOX
