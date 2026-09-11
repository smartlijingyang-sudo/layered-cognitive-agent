"""phase.concept.act_subgraph.act_authorize — policy-level authorization.

concept.act.subgraph 节点 2 (``concept.act.authorize``):typed
``Decision`` + ``AgentState`` → ``Decision``。从 ``control.act.budget``,
``control.act.constrain`` 和 ``control.act.safe-boundary`` 提取的授权逻辑。

执行三类策略检查:
1. Budget:steps / tokens / cost_usd 任一超限拒绝
2. Constraint:USE_TOOL tool_calls call_ids 必须唯一
3. Safety boundary:拒绝明显危险的 tool_name(本地确定性检查)
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
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
from lca.contracts.models.core.state.state import AgentState
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
class ActAuthorizeExecutor:
    """``concept.act.authorize`` 节点:策略级授权检查 (policy-level authorization)。"""

    semantic_name: str = "act.authorize"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision", "state")
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.authorize 入口。

        inputs 端口(yaml): decision (Decision), state (AgentState)
        outputs 端口(yaml): decision (Decision)
        """
        del context
        decision = input.port_values.get("decision")
        state = input.port_values.get("state")
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.authorize: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "act.authorize: 'state' port must be an AgentState or None, "
                f"got {type(state).__name__}"
            )

        # Budget check: refuse if any resource is exhausted.
        budget = getattr(state, "budget", None) if state is not None else None
        if budget is not None:
            if budget.exceeded("steps"):
                raise ValueError(
                    "act.authorize: budget step limit exceeded "
                    f"(used={budget.used_steps}, max={budget.max_steps})"
                )
            if budget.exceeded("tokens"):
                raise ValueError(
                    "act.authorize: budget token limit exceeded "
                    f"(used={budget.used_tokens}, max={budget.max_tokens})"
                )
            if budget.exceeded("cost_usd"):
                raise ValueError(
                    "act.authorize: budget cost limit exceeded "
                    f"(used={budget.used_cost_usd}, max={budget.max_cost_usd})"
                )

        # Constraint check: USE_TOOL tool_calls must have unique call_ids.
        if decision.action_type == "use_tool" and decision.tool_calls:
            call_ids = [call.call_id for call in decision.tool_calls]
            if len(call_ids) != len(set(call_ids)):
                duplicates = sorted({cid for cid in call_ids if call_ids.count(cid) > 1})
                raise ValueError(f"act.authorize: duplicate tool call_ids {duplicates}")

        # Safety boundary: USE_TOOL must not include self-destructive patterns
        # in the tool_name (deterministic local check; deeper policy lives in
        # the runtime capability seam).
        if decision.action_type == "use_tool":
            for call in decision.tool_calls:
                name = call.tool_name.strip().lower()
                if name.startswith("self_destruct") or name.startswith("rm_rf_root"):
                    raise ValueError(
                        f"act.authorize: unsafe tool name rejected: {call.tool_name!r}"
                    )

        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.concept.act_subgraph.act_authorize",
    Config=None,
    provides=("concept::act.authorize",),
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
                "phase_concept_act_subgraph_act_authorize.checked",
                "phase_concept_act_subgraph_act_authorize.served",
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
    executor = ActAuthorizeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActAuthorizeExecutor", "setup"]
