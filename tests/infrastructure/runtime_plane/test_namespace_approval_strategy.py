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


def test_unloaded_shell_name_does_not_ask_for_approval() -> None:
    """A hidden run_command is not an execution. The gate answers it.

    Approving the unloaded name pauses the run before the model can load
    the file tools and write.
    """
    from lca.infrastructure.tool_defer.policy import DeferPolicy
    from lca.infrastructure.tool_defer.session import (
        ToolDeferSession,
        reset_current_defer_session,
        set_current_defer_session,
    )

    class _Tool:
        def __init__(self, name: str, namespace: str) -> None:
            self.name = name
            self.namespace = namespace
            self.description = name
            self.parameters = {"type": "object", "properties": {}}

        async def execute(self, args: dict[str, object]) -> dict[str, object]:
            return {"ok": True}

    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn(
        (
            _Tool("tool_search", "core"),
            _Tool("runCommand", "shell"),
            _Tool("writeFile", "file"),
        )
    )
    token = set_current_defer_session(session)
    try:
        hidden = NamespaceApprovalStrategy().evaluate(
            [ToolCall(tool_name="run_command", call_id="c1", arguments={"command": "mkdir"})]
        )
        assert hidden is None
        session.load_namespace("shell")
        shown = NamespaceApprovalStrategy().evaluate(
            [ToolCall(tool_name="run_command", call_id="c2", arguments={"command": "mkdir"})]
        )
        assert shown is not None and shown.required is True
    finally:
        reset_current_defer_session(token)


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
