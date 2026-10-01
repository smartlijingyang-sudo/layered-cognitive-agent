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
