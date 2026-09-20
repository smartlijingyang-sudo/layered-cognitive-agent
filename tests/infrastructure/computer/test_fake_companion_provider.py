"""FakeCompanionProvider — ADR-0246 §6 M1 验收测试。"""

from __future__ import annotations

import time

import pytest

from lca.contracts.models.core.execution.local_exec import CapabilityGrant, TargetKind
from lca.infrastructure.computer.fake.companion import FakeCompanionProvider


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


@pytest.mark.asyncio
async def test_offline_fail_loud() -> None:
    """I-UMS-1: offline 必须 fail-loud，禁止静默回落。"""
    provider = FakeCompanionProvider(mode="offline")
    receipt = await provider.execute("read_file", {"path": "/repo/a.py"}, _grant())
    assert receipt.success is False
    assert receipt.error_kind == "device_offline"


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
async def test_provider_replacement_consistent_error_shape() -> None:
    """替换测试：FakeCompanionProvider 与 FakeSandboxProvider 错误形状一致。"""
    from lca.infrastructure.computer.fake.sandbox import FakeSandboxProvider

    grant = _grant(path_prefixes=["/repo"])
    companion = FakeCompanionProvider()
    sandbox = FakeSandboxProvider()
    r_c = await companion.execute("read_file", {"path": "/etc/passwd"}, grant)
    r_s = await sandbox.execute("read_file", {"path": "/etc/passwd"}, grant)
    assert r_c.error_kind == r_s.error_kind == "scope_violation"


def test_target_kind_is_user_machine() -> None:
    assert FakeCompanionProvider().target.kind == TargetKind.USER_MACHINE
