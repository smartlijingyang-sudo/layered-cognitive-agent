"""phase.concept.prompt_render.prompt_trace_compile — typed ReasonerTurnRender.

concept.prompt.render 图节点 3:``(prompt_text, PromptTrace)`` →
``ReasonerTurnRender`` typed boundary (ADR-0220 §4.1)。

节点职责:把 ``(prompt, trace)`` 包成 ``ReasonerTurnRender`` DTO,供
下游 ``primitive.llm.call`` 节点读。section_outputs 用 sha256 派生
content_digest,与 P9 ``PromptReasoner.render_turn`` 行为一致。
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
from lca.contracts.models.cognition.prompt_assembly import PromptTrace
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.observability import sha256_payload_digest as _sha256_digest
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


def _section_output_dicts(trace: PromptTrace) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "name": s.name,
            "kind": s.kind,
            "optional": s.optional,
            "used_fallback": s.used_fallback,
            "skipped_empty": s.skipped_empty,
            "text_chars": s.text_chars,
            "text": s.text,
            "content_digest": _sha256_digest(s.text) if s.text else None,
        }
        for s in trace.sections
    )


@dataclass(frozen=True, slots=True)
class PromptTraceCompileExecutor:
    """concept.prompt.render 节点 3:(prompt_text, PromptTrace) → ReasonerTurnRender。"""

    semantic_name: str = "prompt.trace.compile"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("prompt_text", "prompt_trace")
    declared_outputs: tuple[PortName, ...] = ("render",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """prompt.trace.compile 入口。

        inputs 端口(yaml):prompt_text (str), prompt_trace (PromptTrace)
        outputs 端口(yaml):render (ReasonerTurnRender)
        """
        del context
        prompt = input.port_values.get("prompt_text")
        trace = input.port_values.get("prompt_trace")
        if not isinstance(prompt, str):
            raise TypeError(
                f"prompt.trace.compile: 'prompt_text' port must be str, got {type(prompt).__name__}"
            )
        if trace is not None and not isinstance(trace, PromptTrace):
            raise TypeError(
                "prompt.trace.compile: 'prompt_trace' port must be a "
                f"PromptTrace or None, got {type(trace).__name__}"
            )
        if trace is None:
            render = ReasonerTurnRender(
                prompt=prompt,
                trace=None,
                section_count=0,
                manifest=None,
                activated_skill_ids=(),
                section_outputs=None,
                total_chars=None,
                variant=None,
            )
            return NodeOutput(port_values={"render": render})

        render = ReasonerTurnRender(
            prompt=prompt,
            trace=trace,
            section_count=len(trace.sections),
            manifest=None,
            activated_skill_ids=trace.activated_skill_ids,
            section_outputs=_section_output_dicts(trace),
            total_chars=trace.total_chars,
            variant=trace.variant,
        )
        return NodeOutput(port_values={"render": render})


@plugin(
    id="phase.concept.prompt_render.prompt_trace_compile",
    Config=None,
    provides=("concept::prompt.trace.compile",),
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
                "phase_concept_prompt_render_prompt_trace_compile.checked",
                "phase_concept_prompt_render_prompt_trace_compile.served",
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
    executor = PromptTraceCompileExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PromptTraceCompileExecutor", "setup"]
