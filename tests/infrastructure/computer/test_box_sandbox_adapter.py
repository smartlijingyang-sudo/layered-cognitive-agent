"""Tests for BoxExecutionPort and Box Sandbox Adapters (ADR-0248 §3.2 / s04).

Invariants tested:
- INV-04: 沙箱文件读写与命令执行严格隔离，非 root 用户，越界抛 PermissionError。
"""

import pytest

from lca.infrastructure.computer.box_sandbox_adapter import LocalBoxAdapter


@pytest.mark.asyncio
async def test_box_adapter_isolation_and_containment(tmp_path):
    sandbox_dir = tmp_path / "sandbox_box"
    adapter = LocalBoxAdapter(root_dir=sandbox_dir)

    # 1. 验证正常文件读写
    written_path = await adapter.write_file("nested/test.txt", "hello sandbox")
    assert "nested/test.txt" in written_path
    content = await adapter.read_file("nested/test.txt")
    assert content == "hello sandbox"

    # 2. 验证越界访问必定拦截抛出 PermissionError（INV-04）
    with pytest.raises(PermissionError, match="超出员工电脑沙箱范围"):
        await adapter.read_file("../../etc/passwd")

    with pytest.raises(PermissionError, match="超出员工电脑沙箱范围"):
        await adapter.write_file("../escape.txt", "illegal")

    # 3. 验证列表目录
    entries = await adapter.list_files(".")
    assert "nested" in entries

    # 4. 验证命令执行严格在沙箱工作目录
    cmd_res = await adapter.run_command("pwd")
    assert cmd_res.returncode == 0
    assert str(sandbox_dir) in cmd_res.stdout.strip()

    # 5. 验证提权命令拦截
    with pytest.raises(PermissionError, match="禁止提权"):
        await adapter.run_command("sudo rm -rf /")
