"""回归测试：ToolPermissionManifest.add_permitted/revoke_permitted 公共接口。

确认 allowed_tools 的所有变更均通过受管接口而非直接列表操作完成（C4 guardrail）。
"""

from lca.contracts.models.team.role.team import ToolPermissionManifest


def test_add_permitted_is_idempotent():
    manifest = ToolPermissionManifest(allowed_tools=["bash", "file_write"])
    manifest.add_permitted("cordis_control")
    assert "cordis_control" in manifest.allowed_tools
    # 幂等：重复添加不产生重复项
    manifest.add_permitted("cordis_control")
    assert manifest.allowed_tools.count("cordis_control") == 1


def test_add_permitted_does_not_break_existing():
    manifest = ToolPermissionManifest(allowed_tools=["bash"])
    manifest.add_permitted("new_tool")
    assert "bash" in manifest.allowed_tools
    assert "new_tool" in manifest.allowed_tools


def test_revoke_permitted_removes_tool():
    manifest = ToolPermissionManifest(allowed_tools=["bash", "file_write", "cordis_control"])
    manifest.revoke_permitted("file_write")
    assert "file_write" not in manifest.allowed_tools
    assert "bash" in manifest.allowed_tools
    assert "cordis_control" in manifest.allowed_tools


def test_revoke_permitted_is_idempotent():
    manifest = ToolPermissionManifest(allowed_tools=["bash"])
    manifest.revoke_permitted("nonexistent_tool")  # 不应 raise
    assert "bash" in manifest.allowed_tools


def test_add_then_revoke_round_trip():
    manifest = ToolPermissionManifest(allowed_tools=[])
    manifest.add_permitted("dynamic_tool_xyz")
    assert "dynamic_tool_xyz" in manifest.allowed_tools
    manifest.revoke_permitted("dynamic_tool_xyz")
    assert "dynamic_tool_xyz" not in manifest.allowed_tools
    assert manifest.allowed_tools == []
