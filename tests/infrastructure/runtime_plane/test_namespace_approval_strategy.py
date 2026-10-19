from __future__ import annotations

from lca.contracts.models.core.execution.approval import ApprovalReasonKind
from lca.contracts.models.core.execution.decision import ToolCall
from lca.infrastructure.runtime_plane.access.approval_engine import NamespaceApprovalStrategy


def _loaded_shell_session(tool_names: list[str]):
    """Defer session with the given tools registered in the shell namespace (loaded).

    RA-167: the defer catalog is the namespace SSOT — the deleted
    _STANDARD_SHELL_TOOLS backstop is replaced by the session lookup.
    """
    from lca.infrastructure.tool_defer.policy import DeferPolicy
    from lca.infrastructure.tool_defer.session import (
        ToolDeferSession,
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
    session.update_turn([_Tool(name, "shell") for name in tool_names])
    session.load_namespace("shell")
    return set_current_defer_session(session)


def test_shell_namespace_triggers_approval() -> None:
    """ADR-0256: shell domain tools require approval (namespace from defer catalog)."""
    from lca.infrastructure.tool_defer.session import reset_current_defer_session

    token = _loaded_shell_session(["runCommand"])
    try:
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
    finally:
        reset_current_defer_session(token)


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
    """S6 回归（todo-10a）+ RA-167：_STANDARD_SHELL_TOOLS 已删除，其 13 个成员
    在新双拼写策略下仍全部要求审批（8c1624fc7 的回归网）。

    仓库内不存在独立的文件删除工具——删文件的唯一模型可达向量是 shell 命名
    空间。defer catalog 是命名空间 SSOT：evaluate 按 wire gate 的顺序试
    （raw, canonical alternate）两种拼写查 namespace_of_tool。
    """
    from lca.infrastructure.runtime_plane.access.approval_engine import (
        build_default_approval_engine,
    )
    from lca.infrastructure.tool_defer.names import canonical_tool_name
    from lca.infrastructure.tool_defer.session import reset_current_defer_session

    # 已删除的 _STANDARD_SHELL_TOOLS 全体成员
    members = (
        "runCommand",
        "run_command",
        "execScript",
        "exec_script",
        "executeCode",
        "execute_code",
        "getCommandOutput",
        "get_command_output",
        "killCommand",
        "kill_command",
        "box_run_command",
        "bash",
        "run_skill_script",
    )
    # catalog 按 canonical 拼写注册；另一拼写走 alternate 查到 shell
    canonicals = sorted({canonical_tool_name(m) for m in members})
    token = _loaded_shell_session(canonicals)
    try:
        engine = build_default_approval_engine()
        for tool_name in members:
            requirement = engine.evaluate(
                [
                    ToolCall(
                        tool_name=tool_name,
                        call_id="c1",
                        arguments={"command": "rm /tmp/lca-mt-test/shopping.txt"},
                    )
                ]
            )
            assert requirement is not None and requirement.required is True, tool_name
    finally:
        reset_current_defer_session(token)
