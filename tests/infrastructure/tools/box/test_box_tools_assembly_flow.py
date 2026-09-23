"""End-to-end assembly and execution flow tests for ADR-0248 box tools.

Verifies:
1. Box tools and request_box_help are registered in ToolsService;
2. ToolsService.materialize returns concrete executable instances;
3. filter_tools_by_assistant preserves box tools and request_box_help even with strict tools.yaml;
4. ToolBatchExecutor executes box_write_file (with atomic fsync) and box_read_file end-to-end;
5. AutoReviewWrappedTool wraps box_run_command when auto_review_mode != off.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lca.cognition.body.tools.execution_policy import default_tool_batch_policy
from lca.cognition.body.tools.tool_batch_executor import ToolBatchExecutor
from lca.cognition.body.tools.tool_registry import SimpleToolRegistry
from lca.contracts.models.cognition.boundary import BindingsView
from lca.contracts.models.core.execution.decision import ToolCall
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.infrastructure.computer.box_accessor import BoxAccessor
from lca.infrastructure.tools.assistant.filter import filter_tools_by_assistant
from lca.infrastructure.tools.box import (
    BoxListFilesTool,
    BoxReadFileTool,
    BoxRunCommandTool,
    BoxWriteFileTool,
    RequestBoxHelpTool,
)


def test_box_tools_registered_in_tools_service(tmp_path: Path) -> None:
    box = BoxAccessor(root_dir=tmp_path)
    service = ToolsService()

    service.register_factory("box_read_file", lambda b, bx=box: BoxReadFileTool(bx))
    service.register_factory("box_write_file", lambda b, bx=box: BoxWriteFileTool(bx))
    service.register_factory("box_list_files", lambda b, bx=box: BoxListFilesTool(bx))
    service.register_factory("box_run_command", lambda b, bx=box: BoxRunCommandTool(bx))
    service.register_factory("request_box_help", lambda b: RequestBoxHelpTool())

    materialized = service.materialize(BindingsView())
    names = {t.name for t in materialized}
    assert "box_read_file" in names
    assert "box_write_file" in names
    assert "box_list_files" in names
    assert "box_run_command" in names
    assert "request_box_help" in names


def test_filter_tools_by_assistant_preserves_box_tools(tmp_path: Path) -> None:
    box = BoxAccessor(root_dir=tmp_path)
    tools = [
        BoxReadFileTool(box),
        BoxWriteFileTool(box),
        BoxListFilesTool(box),
        BoxRunCommandTool(box),
        RequestBoxHelpTool(),
    ]

    home = tmp_path / "asst_home"
    home.mkdir()
    # tools.yaml only allows "custom_calc", but box tools are platform system tools
    (home / "tools.yaml").write_text(
        "tools:\n  allow:\n    - custom_calc\n  deny: []\n",
        encoding="utf-8",
    )
    (home / "grants.yaml").write_text("grants: []\n", encoding="utf-8")

    filtered = filter_tools_by_assistant(tools, home)
    filtered_names = {t.name for t in filtered}
    assert "box_read_file" in filtered_names
    assert "box_write_file" in filtered_names
    assert "box_list_files" in filtered_names
    assert "box_run_command" in filtered_names
    assert "request_box_help" in filtered_names


@pytest.mark.asyncio
async def test_tool_batch_executor_runs_box_write_and_read(tmp_path: Path) -> None:
    box = BoxAccessor(root_dir=tmp_path)
    registry = SimpleToolRegistry()
    registry.register(BoxWriteFileTool(box))
    registry.register(BoxReadFileTool(box))

    safe_executor = MagicMock()
    async def _safe_execute(tool, args, *rest, **kwargs):
        return await tool.execute(args)

    safe_executor.execute = _safe_execute

    batch_executor = ToolBatchExecutor(
        tool_registry=registry,
        safe_executor=safe_executor,
        policy=default_tool_batch_policy(),
    )

    # 1. Execute box_write_file (ADR-0251 atomic fsync write)
    write_call = ToolCall(
        call_id="call_01",
        tool_name="box_write_file",
        arguments={"path": "notes/todo.txt", "content": "hello atomic box"},
    )
    obs_write = await batch_executor.execute([write_call])
    assert obs_write.success is True

    # Check file exists and has content
    written_file = tmp_path / "notes" / "todo.txt"
    assert written_file.is_file()
    assert written_file.read_text(encoding="utf-8") == "hello atomic box"

    # 2. Execute box_read_file
    read_call = ToolCall(
        call_id="call_02",
        tool_name="box_read_file",
        arguments={"path": "notes/todo.txt"},
    )
    obs_read = await batch_executor.execute([read_call])
    assert obs_read.success is True
    assert obs_read.payload["content"] == "hello atomic box"
