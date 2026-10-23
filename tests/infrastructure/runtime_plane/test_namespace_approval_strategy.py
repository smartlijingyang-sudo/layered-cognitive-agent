from __future__ import annotations

from lca.contracts.models.core.execution.approval import ApprovalReasonKind
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
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


def test_namespace_approval_override_allows_shell() -> None:
    """Per-assistant override ``{"shell": "allow"}`` 让 shell 工具免审批。

    覆盖合并进 DeferPolicy.namespace_approval 后，NamespaceApprovalStrategy
    读到非 ``require_approval`` 的值，直接放行；全局默认不受影响。
    """
    from lca.infrastructure.tool_defer.session import (
        new_defer_session,
        reset_current_defer_session,
        set_current_defer_session,
    )

    session = new_defer_session("direct", namespace_approval={"shell": "allow"})
    assert dict(session.policy.namespace_approval) == {"shell": "allow"}

    class _Tool:
        def __init__(self, name: str, namespace: str) -> None:
            self.name = name
            self.namespace = namespace
            self.description = name
            self.parameters = {"type": "object", "properties": {}}

        async def execute(self, args: dict[str, object]) -> dict[str, object]:
            return {"ok": True}

    session.update_turn([_Tool("runCommand", "shell")])
    session.load_namespace("shell")
    token = set_current_defer_session(session)
    try:
        strategy = NamespaceApprovalStrategy()
        req = strategy.evaluate(
            [
                ToolCall(
                    tool_name="runCommand",
                    call_id="c1",
                    arguments={"command": "pdftotext file.pdf -"},
                )
            ]
        )
        assert req is None
    finally:
        reset_current_defer_session(token)


def test_default_policy_still_requires_shell_approval() -> None:
    """无 override 时全局默认保持 fail-closed（shell=require_approval）。"""
    from lca.infrastructure.tool_defer.session import new_defer_session

    session = new_defer_session("direct")
    assert dict(session.policy.namespace_approval) == {"shell": "require_approval"}


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


def test_no_session_fallback_resourced_from_ssot(monkeypatch) -> None:
    """RA-174: 无 defer session 时的 fallback 必须派生自 DEFAULT_NAMESPACE_APPROVAL。

    默认 fail-closed（shell 域工具要求审批）；monkeypatch SSOT 后 fallback
    跟随变化——证明 fallback 不是手写字面量的第二份拷贝。
    """
    import lca.infrastructure.tool_defer.policy as policy_mod
    from lca.infrastructure.tool_defer.session import current_defer_session

    assert current_defer_session() is None  # 本测试不绑 session，断言前提

    strategy = NamespaceApprovalStrategy(tool_namespaces={"runCommand": "shell"})
    call = ToolCall(tool_name="runCommand", call_id="c1", arguments={"command": "ls"})
    req = strategy.evaluate([call])
    assert req is not None and req.required is True

    # SSOT 跟随：fallback 是派生而非手写拷贝
    monkeypatch.setattr(policy_mod, "DEFAULT_NAMESPACE_APPROVAL", {"shell": "allow"})
    req2 = strategy.evaluate([call])
    assert req2 is None


def _isolated_sandbox_plane() -> PlaneRef:
    return PlaneRef(
        id="onlyboxes-sandbox",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
        platform="linux",
        isolated=True,
    )


def _local_sandbox_plane() -> PlaneRef:
    return PlaneRef(
        id="local-sandbox",
        label="Local sandbox",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
        platform="linux",
        isolated=False,
    )


def _machine_plane() -> PlaneRef:
    return PlaneRef(
        id="machine-default",
        label="Local Machine",
        kind=PlaneKind.MACHINE,
        root="",
        outputs_dir="outputs",
        platform="",
    )


def test_isolated_sandbox_skips_namespace_approval() -> None:
    """Onlyboxes 容器级隔离沙箱内执行 shell 工具不再要求人工审批。

    业界范式：隔离沙箱本身就是安全边界，沙箱内代码/命令执行自动放行。
    """
    from lca.infrastructure.tool_defer.session import reset_current_defer_session

    token = _loaded_shell_session(["executeCode", "runCommand"])
    try:
        strategy = NamespaceApprovalStrategy()
        for tool_name in ("executeCode", "runCommand"):
            req = strategy.evaluate(
                [ToolCall(tool_name=tool_name, call_id="c1", arguments={"command": "ls"})],
                plane=_isolated_sandbox_plane(),
            )
            assert req is None, tool_name
    finally:
        reset_current_defer_session(token)


def test_non_isolated_local_sandbox_keeps_approval() -> None:
    """本地回退沙箱与宿主机共享进程空间，保持 fail-closed 审批。"""
    from lca.infrastructure.tool_defer.session import reset_current_defer_session

    token = _loaded_shell_session(["executeCode"])
    try:
        strategy = NamespaceApprovalStrategy()
        req = strategy.evaluate(
            [ToolCall(tool_name="executeCode", call_id="c1", arguments={})],
            plane=_local_sandbox_plane(),
        )
        assert req is not None and req.required is True
    finally:
        reset_current_defer_session(token)


def test_machine_plane_keeps_namespace_approval() -> None:
    """机器平面（宿主机）执行 shell 工具仍要求审批。"""
    from lca.infrastructure.tool_defer.session import reset_current_defer_session

    token = _loaded_shell_session(["runCommand"])
    try:
        strategy = NamespaceApprovalStrategy()
        req = strategy.evaluate(
            [ToolCall(tool_name="runCommand", call_id="c1", arguments={"command": "rm x"})],
            plane=_machine_plane(),
        )
        assert req is not None and req.required is True
        assert req.reason_kind == ApprovalReasonKind.ELEVATED_COMMAND
    finally:
        reset_current_defer_session(token)


def test_unknown_plane_keeps_namespace_approval() -> None:
    """无 plane（未知执行环境）保持 fail-closed 审批。"""
    from lca.infrastructure.tool_defer.session import reset_current_defer_session

    token = _loaded_shell_session(["runCommand"])
    try:
        strategy = NamespaceApprovalStrategy()
        req = strategy.evaluate(
            [ToolCall(tool_name="runCommand", call_id="c1", arguments={"command": "ls"})],
            plane=None,
        )
        assert req is not None and req.required is True
    finally:
        reset_current_defer_session(token)
