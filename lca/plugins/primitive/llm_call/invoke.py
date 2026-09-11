"""phase.primitive.llm_call.llm_invoke — typed LLM call primitive.

primitive.llm.call 图唯一节点 plugin:typed ``ReasonerTurnRender`` +
``ForkedTools`` → ``LLMResponse`` (ADR-0220 §3.2 + §6.3)。

节点职责:ModelVisible ``CurrentReasonerPrompt`` ContextVar 在 LLM 调用前后
的 bind / reset;把 ``execute_llm_turn`` 的 seam 收口到 typed boundary,不再
让 ``PromptReasoner.complete_turn`` 持有 ContextVar。所有 LLM 调用未来都
走本节点(per ADR §6.3 P4) → 完全可观察、可在 spine EP 上挂 model_visible
hook。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from lca.contracts.models.cognition.boundary import ForkedTools
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import LLMAdapter
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
class LlmInvokeExecutor:
    """primitive.llm.call 节点:ReasonerTurnRender + ForkedTools → LLMResponse。"""

    semantic_name: str = "llm.invoke"
    region: str = "primitive"
    declared_inputs: tuple[PortName, ...] = ("render", "tools", "state")
    declared_outputs: tuple[PortName, ...] = ("response",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """llm.invoke 入口。

        inputs 端口(yaml):render (ReasonerTurnRender), tools (ForkedTools),
        state (AgentState)
        outputs 端口(yaml):response (LLMResponse)

        typed contract:每个 typed input port 验证类型,缺失 / 类型错 → TypeError
        让 fail-loud 在图驱动里捕获(而非在 LLM 内部悄悄降级)。
        """
        render = input.port_values.get("render")
        tools = input.port_values.get("tools")
        state = input.port_values.get("state")
        if not isinstance(render, ReasonerTurnRender):
            raise TypeError(
                "llm.invoke: 'render' port must be a ReasonerTurnRender instance, "
                f"got {type(render).__name__}"
            )
        if not isinstance(tools, ForkedTools):
            raise TypeError(
                "llm.invoke: 'tools' port must be a ForkedTools instance, "
                f"got {type(tools).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "llm.invoke: 'state' port must be an AgentState instance or None, "
                f"got {type(state).__name__}"
            )

        llm = _resolve_llm(context)
        if llm is None:
            raise RuntimeError(
                "llm.invoke: 'llm_adapter' capability missing from runtime scope — "
                "wire phase.think.reasoner.credentials before primitive.llm.call."
            )

        from lca.cognition.brain.llm_turn import execute_llm_turn
        from lca.infrastructure.observability.loop_cursor.coordinator.adapter import (
            get_current_cursor,
        )
        from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
            CurrentReasonerPrompt,
            bind_current_reasoner_prompt,
            reset_current_reasoner_prompt,
        )

        token: Any = None
        if render.trace is not None:
            cursor = get_current_cursor()
            if cursor is None:
                step_id = f"step-unknown-{render.trace.template_id}"
            else:
                try:
                    step_id = f"step-{cursor.snapshot.step_index + 1:03d}"
                except Exception:
                    step_id = f"step-unknown-{render.trace.template_id}"
            token = bind_current_reasoner_prompt(
                CurrentReasonerPrompt(
                    step_id=step_id,
                    template_id=render.trace.template_id,
                    selector_decision_path=render.trace.selector_decision_path,
                    system_prompt_text=render.trace.system_prompt_text,
                    prompt_trace=render.trace,
                    context_manifest=render.manifest,
                )
            )
        try:
            step_index = getattr(state, "step", 0) if state is not None else 0
            task_text = getattr(state, "task", "") if state is not None else ""
            response: LLMResponse = await execute_llm_turn(
                llm,
                list(tools.items),
                render.prompt,
                step=step_index,
                state=state if state is not None else _empty_state(),
                task=task_text or "",
            )
        finally:
            if token is not None:
                reset_current_reasoner_prompt(token)

        return NodeOutput(port_values={"response": response})


def _resolve_llm(context: NodeContext) -> LLMAdapter | None:
    """Resolve the LLMAdapter from the node context's runtime.

    Cordis capability ``llm_adapter`` (or ``llm`` alias for back-compat
    with the ``phase.think.reasoner.compose`` plugin) is the boot-time
    seam. The runtime attribute on the node context is whichever the
    SubgraphRuntime exposes; both names are tried because the legacy
    inner-subgraph tests still inject ``runtime.llm``.
    """
    runtime = context.runtime
    llm = getattr(runtime, "llm_adapter", None)
    if llm is None:
        llm = getattr(runtime, "llm", None)
    return llm if isinstance(llm, LLMAdapter) else None


def _empty_state() -> AgentState:
    from lca.contracts.models.core.state.state import (
        AgentState as _AgentState,
    )
    from lca.contracts.models.core.state.state import (
        Budget as _Budget,
    )

    return _AgentState(trace_id="llm-invoke", task="", budget=_Budget())


@plugin(
    id="phase.primitive.llm_call.llm_invoke",
    Config=None,
    provides=("primitive::llm.invoke",),
    requires=("llm_adapter",),
    layer="L1",
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
                "phase_primitive_llm_call_llm_invoke.checked",
                "phase_primitive_llm_call_llm_invoke.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "llm_adapter"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = LlmInvokeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["LlmInvokeExecutor", "setup"]
