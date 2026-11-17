"""Tests for Mangli enterprise tool contract and execution (INV-05)."""

import pytest

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.tools.mangli_enterprise_tools import MangliWorkspaceExportTool


@pytest.mark.asyncio
async def test_tool_conforms_to_lca_contract(tmp_path):
    file_store = LocalFileStore(tmp_path / "files")
    tool = MangliWorkspaceExportTool(
        file_store=file_store,
        user_id="U888",
        project_id="proj_reserved_01",
        session_id="sess_01",
    )

    # 1. 契约符合性（7 项 ClassVar 必验）
    assert isinstance(tool, Tool)
    assert tool.name == "mangli_workspace_export"
    assert tool.namespace == "workspace"
    assert isinstance(tool.description, str)
    assert isinstance(tool.parameters, dict)
    assert isinstance(tool.is_idempotent, bool)
    assert tool.effect_kind in ("ephemeral", "persistent", "stateful_once")
    assert isinstance(tool.default_timeout_s, int)

    # 2. 租户参数严禁暴露在模型参数中
    assert "project_id" not in tool.parameters["properties"]
    assert "session_id" not in tool.parameters["properties"]

    # 3. 执行并生成 Observation 与 FileStore 凭证
    obs = await tool.execute({"path": "report.txt", "content": "hello mangli"})
    assert isinstance(obs, Observation)
    assert obs.payload["status"] == "ok"
    assert "attachment_id" in obs.payload
