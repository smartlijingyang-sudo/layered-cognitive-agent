"""默认声明式 control contribution。

此模块持有标准 Profile 的安全策略，但不参与运行编排；Profile 可以以同一
capability 被替换，或通过 PhaseGraph 增加更专用的 govern contribution。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.atoms.enums import ActionType
from lca.contracts.protocols.declarative_phase_graph import (
    CapabilityDeclaration,
    ContributionRole,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PhaseContribution,
    PhaseResult,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    SemanticPhase,
    VerificationDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class StandardControlConfig(BaseModel):
    """标准 control contribution 的显式空配置。"""


class StandardControlContribution:
    """执行与阶段相邻的通用安全检查并返回可聚合的 policy PhaseResult。"""

    async def execute(self, context: Any, _input: Any) -> PhaseResult:
        phase = str(context.node_ref).split(".", 1)[0]
        state = context.state
        decision = context.artifacts.get("think")
        observation = context.artifacts.get("act")
        reflection = context.artifacts.get("reflect")

        if phase == SemanticPhase.ACT.value:
            return _act_verdict(state, decision)
        if phase == SemanticPhase.REMEMBER.value:
            if observation is None or reflection is None:
                return _deny("memory admission requires observation and reflection")
            if getattr(state.status, "value", state.status) != "working":
                return _deny("terminal run does not admit memory")
        if phase == SemanticPhase.STOP.value:
            if state.budget.exceeded():
                return _stop("run budget is exhausted")
            if decision is not None and _action_is(decision, ActionType.STOP):
                return _stop("decision requested terminal stop")
        if (
            phase == SemanticPhase.PERCEIVE.value
            and getattr(state.status, "value", state.status) != "working"
        ):
            return _stop("run state is not working")
        return _allow()


def _act_verdict(state: Any, decision: Any) -> PhaseResult:
    if decision is None or not _is_known_action(decision):
        return _deny("action type is not authorized")
    if state.budget.exceeded():
        return _stop("run budget is exhausted")
    if _action_is(decision, ActionType.STOP):
        return _stop("decision requested terminal stop")
    tool_calls = tuple(getattr(decision, "tool_calls", ()) or ())
    if _action_is(decision, ActionType.USE_TOOL):
        if not tool_calls:
            return _deny("tool action has no tool call")
        if any(not str(getattr(call, "tool_name", "")).strip() for call in tool_calls):
            return _deny("tool action has an unnamed tool")
    call_ids = [str(getattr(call, "call_id", "")) for call in tool_calls]
    if any(not call_id.strip() for call_id in call_ids):
        return _deny("tool call id is required")
    if len(call_ids) != len(set(call_ids)):
        return _deny("tool call ids must be unique")
    if any(
        getattr(call, "timeout_s", None) is not None and call.timeout_s <= 0 for call in tool_calls
    ):
        return _deny("tool timeout must be positive")
    if (
        _action_is(decision, ActionType.DELEGATE) or _action_is(decision, ActionType.HANDOFF)
    ) and not tuple(getattr(decision, "delegations", ()) or ()):
        return _deny("delegation execution has no target")
    return _allow()


def _action_is(decision: Any, action: ActionType) -> bool:
    return (
        getattr(decision, "action_type", None) == action
        or getattr(decision, "action_type", None) == action.value
    )


def _is_known_action(decision: Any) -> bool:
    try:
        ActionType(getattr(decision, "action_type", None))
    except ValueError:
        return False
    return True


def _allow() -> PhaseResult:
    return PhaseResult(result_kind="policy", payload={"verdict": "allow"})


def _deny(reason: str) -> PhaseResult:
    return PhaseResult(result_kind="policy", payload={"verdict": "deny", "reason": reason})


def _stop(reason: str) -> PhaseResult:
    return PhaseResult(result_kind="policy", payload={"verdict": "stop", "reason": reason})


def _standard_control_spec() -> PluginSpec:
    capability = "control.standard"
    phases = tuple(
        PhaseContribution(
            phase=phase,
            role=ContributionRole.GOVERN,
            executor=capability,
            output=f"control.{phase.value}",
            aggregation="deny-on-any-deny",
            order=0,
        )
        for phase in (
            SemanticPhase.PERCEIVE,
            SemanticPhase.ACT,
            SemanticPhase.REMEMBER,
            SemanticPhase.STOP,
        )
    )
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id="control.standard",
        revision="1.0.0",
        kind=PluginSpecKind.PROVIDER,
        layer="L2",
        functional_group="runtime-control",
        implementation=PluginImplementation(
            module="lca.plugins.control_contributions.standard",
            setup="setup",
            factory="create_contribution",
        ),
        configuration=PluginConfiguration(
            schema="lca.plugins.control_contributions.standard.StandardControlConfig"
        ),
        provides=(
            CapabilityDeclaration(
                key=capability,
                cardinality="one",
                protocol="PhaseExecutor",
                scope="run",
            ),
        ),
        requires=(),
        effects=("none",),
        ownership=OwnershipDeclaration(
            reads=("state.view", "phase.artifact"), state_mutation="forbidden"
        ),
        lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
        relations=(),
        evidence=EvidenceDeclaration(emits=("ControlVerdict",), replay="required"),
        verification=VerificationDeclaration(
            test_suite="tests/declarative/test_standard_control_contribution.py",
            properties=("policy_result_contract", "no_runtime_dispatch"),
        ),
        contributes=phases,
    )


SPEC = _standard_control_spec()


@plugin(
    id="control.standard",
    Config=StandardControlConfig,
    provides=("control.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_standard_control_contribution.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, _config: StandardControlConfig) -> None:
    ctx.provide("control.standard", StandardControlContribution())


def create_contribution() -> StandardControlContribution:
    return StandardControlContribution()


__all__ = ["SPEC", "StandardControlConfig", "StandardControlContribution", "create_contribution"]
