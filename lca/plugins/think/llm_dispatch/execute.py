"""phase.think.llm_dispatch.llm_call — typed writer→LLM→writer boundary.

think.llm.dispatch 图节点 1:从 ``ModelVisibleRequest`` 调 LLM adapter,
经 persist-before-execute 把 assistant row + tool_calls 写到
``RunSessionWriter``,然后把 ``LLMResponse`` + ``TokenUsage`` 透传到
think.decision.parse(spec §E,ADR-0226 §4)。
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
from lca.contracts.models.core.conversation.llm import LLMResponse, TokenUsage
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
from lca.framework.graph.nodes.llm_dispatch import llm_dispatch
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class LLMDispatchExecutor:
    """think.llm.dispatch 节点 1:(state, writer, request) → LLMResponse + usage。"""

    semantic_name: str = "llm.call"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("state", "writer", "model_visible_request")
    declared_outputs: tuple[PortName, ...] = ("llm_response", "usage")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """llm.call 入口。

        inputs 端口(yaml): state (AgentState),
        writer (RunSessionWriterProtocol), model_visible_request
        (ModelVisibleRequest)
        outputs 端口(yaml): llm_response (LLMResponse), usage (TokenUsage)

        LLM adapter 取自 ``context.runtime.llm_adapter``(typed-boundary
        seam,与 history_assemble/decision_parse 守护风格一致)。
        writer / model_visible_request 缺失时与 history_assemble 行为
        对齐:writer 缺失抛 TypeError;model_visible_request 缺失抛
        TypeError,确保 fail-loud。
        """
        state = input.port_values.get("state")
        if state is None:
            state = context.runtime.get("state") if hasattr(context, "runtime") else None
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                f"llm.call: 'state' port must be an AgentState instance, got {type(state).__name__}"
            )
        writer = input.port_values.get("writer")
        if writer is None:
            writer = context.runtime.get("writer") if hasattr(context, "runtime") else None
        if writer is None:
            raise TypeError(
                "llm.call: 'writer' port must be a RunSessionWriterProtocol instance; got None"
            )
        request = input.port_values.get("model_visible_request")
        if request is None:
            raise TypeError(
                "llm.call: 'model_visible_request' port must be a "
                "ModelVisibleRequest instance; got None"
            )
        adapter = context.runtime.get("llm_adapter") if hasattr(context, "runtime") else None
        if adapter is None:
            raise TypeError(
                "llm.call: 'llm_adapter' must be supplied via context.runtime.llm_adapter; got None"
            )
        response, usage = await llm_dispatch(
            state=state,
            writer=writer,
            model_visible_request=request,
            adapter=adapter,
        )
        assert isinstance(response, LLMResponse)  # noqa: S101
        assert isinstance(usage, TokenUsage)  # noqa: S101
        return NodeOutput(port_values={"llm_response": response, "usage": usage})


@plugin(
    id="phase.think.llm_dispatch.llm_call",
    Config=None,
    provides=("think::llm.call",),
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
                "phase_think_llm_dispatch_llm_call.checked",
                "phase_think_llm_dispatch_llm_call.served",
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
    executor = LLMDispatchExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["LLMDispatchExecutor", "setup"]
