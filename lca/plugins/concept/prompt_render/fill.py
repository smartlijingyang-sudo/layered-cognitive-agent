"""phase.concept.prompt_render.prompt_sections_fill — pure typed DTO render.

concept.prompt.render 图节点 2:typed ``PromptTemplate`` +
``ReasonerContext`` + ``RoleSnapshot`` → ``(prompt, PromptTrace)``
(ADR-0220 §6.1)。

节点职责:把 ``render_template(...)`` 包成 typed-DTO 入口。不读
``AgentState``,不调 LLM,不碰 EP —— 纯变换。这一节点是 ADR §2.2
"事实/状态/决策/许可/回执/投影"分类下"投影"的具体落点。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.cognition.brain.sections.assembler import render_template
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
from lca.contracts.models.cognition.boundary import (
    ReasonerContext,
    RoleSnapshot,
)
from lca.contracts.models.cognition.prompt_assembly import PromptTemplate
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
class PromptSectionsFillExecutor:
    """concept.prompt.render 节点 2:PromptTemplate + ReasonerContext + RoleSnapshot → (prompt, trace)。"""

    semantic_name: str = "prompt.sections.fill"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("prompt_template", "context", "role")
    declared_outputs: tuple[PortName, ...] = ("prompt_text", "prompt_trace")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """prompt.sections.fill 入口。

        inputs 端口(yaml):prompt_template (PromptTemplate), context (ReasonerContext),
        role (RoleSnapshot)
        outputs 端口(yaml):prompt_text (str), prompt_trace (PromptTrace)
        """
        template = input.port_values.get("prompt_template")
        ctx_dto = input.port_values.get("context")
        role = input.port_values.get("role")
        if not isinstance(template, PromptTemplate):
            raise TypeError(
                "prompt.sections.fill: 'prompt_template' port must be a "
                f"PromptTemplate instance, got {type(template).__name__}"
            )
        if not isinstance(ctx_dto, ReasonerContext):
            raise TypeError(
                "prompt.sections.fill: 'context' port must be a ReasonerContext "
                f"instance, got {type(ctx_dto).__name__}"
            )
        if not isinstance(role, RoleSnapshot):
            raise TypeError(
                "prompt.sections.fill: 'role' port must be a RoleSnapshot "
                f"instance, got {type(role).__name__}"
            )

        tools_provider = getattr(context.runtime, "tools_provider", None)
        tools_seq: tuple[Any, ...] = ()
        if tools_provider is not None:
            listed = getattr(tools_provider, "list_tools", None)
            if callable(listed):
                tools_seq = tuple(listed())

        registry = getattr(context.runtime, "prompt_section_registry", None)

        prompt, trace = render_template(
            template=template,
            registry=registry,
            role_profile=role.profile,
            awareness=role.team_awareness,
            manifest=ctx_dto.manifest,
            tools=tools_seq,
            activated_skills=ctx_dto.activated_skills,
        )
        return NodeOutput(port_values={"prompt_text": prompt, "prompt_trace": trace})


@plugin(
    id="phase.concept.prompt_render.prompt_sections_fill",
    Config=None,
    provides=("concept::prompt.sections.fill",),
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
                "phase_concept_prompt_render_prompt_sections_fill.checked",
                "phase_concept_prompt_render_prompt_sections_fill.served",
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
    executor = PromptSectionsFillExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PromptSectionsFillExecutor", "setup"]
