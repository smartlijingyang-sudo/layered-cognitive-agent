"""phase.concept.prompt_render.prompt_sections_assemble — fetch PromptTemplate.

concept.prompt.render 图节点 1:typed ``TemplateSelection`` → ``PromptTemplate``
(ADR-0220 §4.1)。

节点职责:从 ``PromptTemplateProvider`` 拿 ``PromptTemplate``。typed
``TemplateSelection.template_id`` 是稳定键,失败显式抛
``MissingPromptSectionError``,绝不走静默回退 —— 渲染静默是历史病灶
(``_legacy_select_template`` 的 fallback 链路),本节点关门。
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
from lca.contracts.models.cognition.boundary import TemplateSelection
from lca.contracts.models.cognition.prompt_assembly import (
    MissingPromptSectionError,
    PromptTemplateProvider,
)
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
class PromptSectionsAssembleExecutor:
    """concept.prompt.render 节点 1:TemplateSelection → PromptTemplate。"""

    semantic_name: str = "prompt.sections.assemble"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("template_selection",)
    declared_outputs: tuple[PortName, ...] = ("prompt_template",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """prompt.sections.assemble 入口。

        inputs 端口(yaml):template_selection (TemplateSelection)
        outputs 端口(yaml):prompt_template (PromptTemplate)
        """
        selection = input.port_values.get("template_selection")
        if not isinstance(selection, TemplateSelection):
            raise TypeError(
                "prompt.sections.assemble: 'template_selection' port must be a "
                f"TemplateSelection instance, got {type(selection).__name__}"
            )

        provider = getattr(context.runtime, "prompt_template_provider", None)
        if not isinstance(provider, PromptTemplateProvider):
            raise RuntimeError(
                "prompt.sections.assemble: 'prompt_template_provider' capability "
                "missing from runtime scope — wire PROMPT_TEMPLATE_PROVIDER before "
                "concept.prompt.render runs."
            )

        template = provider.get_template(selection.template_id)
        if template is None:
            raise MissingPromptSectionError(selection.template_id, "pure")
        return NodeOutput(port_values={"prompt_template": template})


@plugin(
    id="phase.concept.prompt_render.prompt_sections_assemble",
    Config=None,
    provides=("concept::prompt.sections.assemble",),
    requires=("prompt_template_provider",),
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
                "phase_concept_prompt_render_prompt_sections_assemble.checked",
                "phase_concept_prompt_render_prompt_sections_assemble.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "prompt_template_provider"),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = PromptSectionsAssembleExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PromptSectionsAssembleExecutor", "setup"]
