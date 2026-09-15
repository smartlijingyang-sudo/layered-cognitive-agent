"""phase.concept.act_subgraph.act_validate — Decision shape validator.

concept.act.subgraph 节点 1 (``concept.act.validate``):typed
``Decision`` → ``Decision``。从 ``control.act.authorize`` 和
``control.act.execute`` 提取的验证逻辑:

1. Decision 必须存在且是 Decision 实例
2. ``decision.action_type`` 必须在 ActionType 闭集中
3. ``ActionType.USE_TOOL``:检查 ``tool_calls`` 非空且每个 call 有 ``tool_name``
4. ``ActionType.DELEGATE`` / ``ActionType.HANDOFF``:检查 ``delegations`` 非空
5. 返回验证通过的 Decision
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ActValidateExecutor:
    """``concept.act.validate`` 节点:校验 Decision shape 后透传。"""

    semantic_name: str = "act.validate"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.validate 入口。

        inputs 端口(yaml): decision (Decision)
        outputs 端口(yaml): decision (Decision)
        """
        del context
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.validate: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )

        # action_type 必须在 ActionType 闭集中
        try:
            action_type = ActionType(decision.action_type)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"act.validate: action_type {decision.action_type!r} "
                "is not in the ActionType closed set"
            ) from exc

        # USE_TOOL: tool_calls 必须非空,且每个 call 有 tool_name
        if action_type == ActionType.USE_TOOL:
            if not decision.tool_calls:
                raise ValueError("act.validate: USE_TOOL action has no tool calls")
            if any(not call.tool_name.strip() for call in decision.tool_calls):
                raise ValueError("act.validate: USE_TOOL action has an unnamed tool call")

        # DELEGATE / HANDOFF: delegations 必须非空
        if action_type in {ActionType.DELEGATE, ActionType.HANDOFF} and not decision.delegations:
            raise ValueError("act.validate: DELEGATE/HANDOFF action has no delegations")

        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.concept.act_subgraph.act_validate",
    Config=None,
    provides=("concept::act.validate",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_act_subgraph_act_validate.checked",
                "phase_concept_act_subgraph_act_validate.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ActValidateExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActValidateExecutor", "setup"]
