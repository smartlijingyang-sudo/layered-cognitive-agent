"""phase.think.reasoner.compose — assemble PromptReasoner from injected parts.

Consumes ``llm_adapter`` (from :mod:`lca.plugins.think.reasoner.credentials`),
``role_profile`` (from :mod:`lca.plugins.think.role_profile_provider`), and
``tools`` (from :mod:`lca.plugins.act.tools.seam`). Wires the assembler /
selector from their respective capability providers and constructs a
:class:`PromptReasoner` instance for the inner think subgraph to call.

The boot-time tools list is captured here as ``tools=`` on the constructor
so :meth:`PromptReasoner.complete_turn` can hand a stable tool set to
``execute_llm_turn``. Per-run tool resolution (P5) moves to
``primitive.llm.call`` graph node (ADR-0220 §6.2).

``RoleProfile`` 由上游 ``phase.think.role_profile`` provider 通过
``reasoner.role_profile`` capability 注入,本 plugin 不再持有默认字面量。
没有上游 provider 时 boot 会因 ``UndeclaredInteractionError`` /
``MissingCapabilityError`` 失败,而不是悄悄把 ``assistant`` 身份
写进 LLM prompt。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import (
    PROMPT_ASSEMBLER,
    PROMPT_TEMPLATE_SELECTOR,
    REASONER_ROLE_PROFILE,
    TOOLS,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="phase.think.reasoner.compose",
    provides=("reasoner",),
    requires=(
        "llm_adapter",
        REASONER_ROLE_PROFILE.key,
        TOOLS.key,
        PROMPT_ASSEMBLER.key,
        PROMPT_TEMPLATE_SELECTOR.key,
    ),
    implements=[Reasoner],
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Compose a PromptReasoner from the active llm_adapter, "
        "role_profile, tools list, assembler, and selector; publish "
        "as the ``reasoner`` capability for the inner think subgraph."
    ),
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_reasoner_compose.checked",
                "phase_think_reasoner_compose.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "llm_adapter", REASONER_ROLE_PROFILE.key, TOOLS.key),
        emits=("reasoner.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Assemble :class:`PromptReasoner` and publish as ``reasoner`` capability."""
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner

    del config

    adapter = ctx.require("llm_adapter")
    role_profile = ctx.require(REASONER_ROLE_PROFILE.key)
    if not isinstance(role_profile, RoleProfile):
        raise TypeError(
            "reasoner.role_profile must be a RoleProfile instance, got "
            f"{type(role_profile).__name__}"
        )
    tools_service = ctx.require(TOOLS.key)
    tools = tools_service.list_tools() if tools_service is not None else ()
    assembler = ctx.require(PROMPT_ASSEMBLER.key)
    selector = ctx.require(PROMPT_TEMPLATE_SELECTOR.key)

    reasoner = PromptReasoner(
        llm=adapter,
        role_profile=role_profile,
        assembler=assembler,
        selector=selector,
        tools=tools,
    )
    ctx.provide("reasoner", reasoner)


__all__ = ["Config", "setup"]
