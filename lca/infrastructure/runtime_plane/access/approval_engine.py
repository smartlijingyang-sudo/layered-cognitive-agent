"""Approval Policy Engine & Standard Strategies implementing Strategy and Chain of Responsibility patterns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lca.contracts.models.core.execution.approval import (
    ApprovalReasonKind,
    ApprovalRequirement,
    RiskLevel,
)
from lca.contracts.models.core.execution.decision import (
    HITL_TOOL_NAMES,
    ToolCall,
)
from lca.contracts.models.core.execution.local_exec import AccessVerdict
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.contracts.protocols.execution.approval_strategy import ApprovalStrategy
from lca.infrastructure.runtime_plane.access.classify import (
    call_paths,
    decide_tool_call,
    machine_operation,
)

_SENSITIVE_SUBSTRINGS = frozenset(
    {".ssh", "id_rsa", "id_ed25519", "credentials", "token", "secret", "passwd", "shadow"}
)


class HITLInteractionStrategy:
    """Strategy identifying interactive HITL tool requests like askUserQuestion."""

    strategy_name = "hitl_interaction"

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall],
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement | None:
        if not isinstance(tool_calls, (list, tuple)):
            return None
        for call in tool_calls:
            tool_name = getattr(call, "tool_name", None)
            if tool_name in HITL_TOOL_NAMES:
                return ApprovalRequirement(
                    required=True,
                    reason_kind=ApprovalReasonKind.HUMAN_INTERACTION,
                    risk_level=RiskLevel.LOW,
                    summary="等待用户回答交互问题",
                    target_resource=tool_name,
                    details={"tool_name": tool_name},
                )
        return None


class MachineAccessStrategy:
    """Strategy inspecting machine-plane operations for sensitive or unauthorized access."""

    strategy_name = "machine_access"

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall],
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement | None:
        if plane is None or plane.kind is not PlaneKind.MACHINE:
            return None
        if not isinstance(tool_calls, (list, tuple)):
            return None

        for call in tool_calls:
            tool_name = getattr(call, "tool_name", None)
            arguments = getattr(call, "arguments", None)
            if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
                continue
            decision = decide_tool_call(tool_name, arguments, plane=plane)
            if decision is not None and decision.verdict is not AccessVerdict.ALLOW:
                op = machine_operation(tool_name) or ""
                paths = call_paths(op, arguments)
                target_resource = paths[0] if paths else None
                cmd = arguments.get("command") if isinstance(arguments.get("command"), str) else None

                # Determine reason and risk level
                if target_resource and any(sub in target_resource for sub in _SENSITIVE_SUBSTRINGS):
                    reason_kind = ApprovalReasonKind.SENSITIVE_RESOURCE
                    risk_level = RiskLevel.HIGH
                elif target_resource and (".." in target_resource or decision.verdict is AccessVerdict.DENY):
                    reason_kind = ApprovalReasonKind.UNAUTHORIZED_PATH
                    risk_level = RiskLevel.HIGH if ".." in target_resource else RiskLevel.CRITICAL
                elif cmd:
                    reason_kind = ApprovalReasonKind.ELEVATED_COMMAND
                    risk_level = RiskLevel.HIGH
                else:
                    reason_kind = ApprovalReasonKind.UNAUTHORIZED_PATH
                    risk_level = RiskLevel.MEDIUM

                summary = f"机器访问拦截: {tool_name} {target_resource or cmd or ''}".strip()
                return ApprovalRequirement(
                    required=True,
                    reason_kind=reason_kind,
                    risk_level=risk_level,
                    summary=summary,
                    target_resource=target_resource or (cmd[:32] if cmd else None),
                    details={
                        "tool_name": tool_name,
                        "verdict": decision.verdict.value,
                        "reason": decision.reason,
                    },
                )
        return None


class DefaultAllowStrategy:
    """Fallback strategy terminating the chain with allow requirement."""

    strategy_name = "default_allow"

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall],
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement | None:
        return ApprovalRequirement(
            required=False,
            reason_kind=ApprovalReasonKind.NONE,
            risk_level=RiskLevel.LOW,
            summary="",
        )


class ApprovalPolicyEngine:
    """Chain of Responsibility engine evaluating approval strategies in order."""

    def __init__(self, strategies: Sequence[ApprovalStrategy]) -> None:
        self._strategies = list(strategies)

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall] | object,
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement:
        if not isinstance(tool_calls, (list, tuple)):
            return ApprovalRequirement(required=False, reason_kind=ApprovalReasonKind.NONE)

        for strategy in self._strategies:
            req = strategy.evaluate(tool_calls, plane=plane)
            if req is not None:
                if req.required:
                    return req
                # If a strategy explicitly returned an allow requirement, continue or return
                if getattr(strategy, "strategy_name", None) == "default_allow":
                    return req

        return ApprovalRequirement(required=False, reason_kind=ApprovalReasonKind.NONE)


class ApprovalPolicyRegistry:
    """Registry maintaining ordered approval strategies for extensible rule injection."""

    def __init__(self) -> None:
        self._strategies: list[tuple[int, ApprovalStrategy]] = []

    def register(self, strategy: ApprovalStrategy, priority: int = 100) -> None:
        self._strategies.append((priority, strategy))
        self._strategies.sort(key=lambda item: item[0])

    def list_strategies(self) -> list[ApprovalStrategy]:
        return [strat for _, strat in self._strategies]


_STANDARD_SHELL_TOOLS: frozenset[str] = frozenset(
    {
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
    }
)


class NamespaceApprovalStrategy:
    """Strategy inspecting tool namespace approval requirements (e.g. shell domain)."""

    strategy_name = "namespace_approval"

    def __init__(
        self,
        tool_namespaces: Mapping[str, str] | None = None,
        approval_mapping: Mapping[str, str] | None = None,
    ) -> None:
        self._tool_namespaces = tool_namespaces
        self._approval_mapping = approval_mapping

    def evaluate(
        self,
        tool_calls: Sequence[ToolCall],
        plane: PlaneRef | None = None,
    ) -> ApprovalRequirement | None:
        del plane
        if not isinstance(tool_calls, (list, tuple)):
            return None

        # Build dynamic tool -> namespace map from defer session if present
        from lca.infrastructure.tool_defer.session import current_defer_session

        defer_session = current_defer_session()
        policy = defer_session.policy if defer_session is not None else None
        approval_rules = (
            self._approval_mapping
            if self._approval_mapping is not None
            else (policy.namespace_approval if policy is not None else {"shell": "require_approval"})
        )

        session_tool_to_ns: dict[str, str] = {}
        if defer_session is not None:
            for ns_obj in defer_session.namespaces:
                for tname in ns_obj.tool_names:
                    session_tool_to_ns[tname] = ns_obj.name

        for call in tool_calls:
            tool_name = getattr(call, "tool_name", None)
            if not isinstance(tool_name, str) or not tool_name:
                continue

            ns: str | None = None
            if self._tool_namespaces and tool_name in self._tool_namespaces:
                ns = self._tool_namespaces[tool_name]
            elif tool_name in session_tool_to_ns:
                ns = session_tool_to_ns[tool_name]
            elif tool_name in _STANDARD_SHELL_TOOLS:
                ns = "shell"

            if ns and approval_rules.get(ns) == "require_approval":
                return ApprovalRequirement(
                    required=True,
                    reason_kind=ApprovalReasonKind.ELEVATED_COMMAND,
                    risk_level=RiskLevel.HIGH,
                    summary=f"高危命令或脚本调用需用户授权: {tool_name} (命名空间: {ns})",
                    target_resource=tool_name,
                    details={"tool_name": tool_name, "namespace": ns},
                )
        return None


def build_default_approval_engine() -> ApprovalPolicyEngine:
    """Build standard default approval engine with built-in strategy chain."""
    return ApprovalPolicyEngine(
        strategies=[
            HITLInteractionStrategy(),
            MachineAccessStrategy(),
            NamespaceApprovalStrategy(),
            DefaultAllowStrategy(),
        ]
    )
