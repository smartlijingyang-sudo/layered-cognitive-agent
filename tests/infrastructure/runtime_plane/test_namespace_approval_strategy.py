from __future__ import annotations

from lca.contracts.models.core.execution.approval import ApprovalReasonKind
from lca.contracts.models.core.execution.decision import ToolCall
from lca.infrastructure.runtime_plane.access.approval_engine import NamespaceApprovalStrategy


def test_shell_namespace_triggers_approval() -> None:
    strategy = NamespaceApprovalStrategy()
    tool_calls = [
        ToolCall(
            tool_name="runCommand",
            call_id="c1",
            arguments={"command": "ls"},
        )
    ]
    requirement = strategy.evaluate(tool_calls)
    assert requirement is not None
    assert requirement.required is True
    assert requirement.reason_kind == ApprovalReasonKind.ELEVATED_COMMAND


def test_file_namespace_auto_pass() -> None:
    strategy = NamespaceApprovalStrategy()
    tool_calls = [
        ToolCall(
            tool_name="readFile",
            call_id="c2",
            arguments={"path": "workspace/file.txt"},
        )
    ]
    requirement = strategy.evaluate(tool_calls)
    assert requirement is None
def test_shell_delete_vectors_require_approval_via_default_engine() -> None:
    """S6 回归（todo-10a）：仓库内不存在独立的文件删除工具——删文件的唯一
    模型可达向量是 shell 命名空间（runCommand/rm 等）。默认审批引擎必须对
    全部 shell 工具变体要求审批，对标 ADR-0256 shell 域 REQUIRE_APPROVAL。"""
    from lca.infrastructure.runtime_plane.access.approval_engine import (
        build_default_approval_engine,
    )

    engine = build_default_approval_engine()
    for tool_name in (
        "runCommand",
        "run_command",
        "box_run_command",
        "execute_code",
        "executeCode",
        "exec_script",
    ):
        requirement = engine.evaluate(
            [
                ToolCall(
                    tool_name=tool_name,
                    call_id="c1",
                    arguments={"command": "rm /tmp/lca-mt-test/shopping.txt"},
                )
            ]
        )
        assert requirement.required is True, tool_name
