"""phase.think.role_profile — ``RoleProfile`` provider for inner think subgraph.

构造 :class:`RoleProfile` 实例并注册到 ``reasoner.role_profile`` capability 键。
``phase.think.reasoner`` 在 boot 时通过 ``ctx.require("reasoner.role_profile")``
取这个实例,而不是在源码里硬编码 role / goal / backstory。

Profile YAML 通过 ``config:`` 字段覆盖默认值:

```yaml
- id: phase.think.role_profile
  $module: lca.plugins.think.role_profile_provider
  config:
    role: research_agent
    goal: reason about the current step with concrete evidence
    backstory: inner think subgraph reasoner
    allowed_tools: []
```
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import REASONER_ROLE_PROFILE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Profile-configurable role identity consumed by ``phase.think.reasoner``."""

    model_config = ConfigDict(extra="forbid")
    role: str = "assistant"
    goal: str = "answer user questions"
    backstory: str = "LCA inner think subgraph reasoner"
    allowed_tools: tuple[str, ...] = ()


@plugin(
    id="phase.think.role_profile",
    Config=Config,
    provides=[REASONER_ROLE_PROFILE.key],
    requires=(),
    implements=[],
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the RoleProfile instance consumed by phase.think.reasoner. "
        "All fields are profile-configurable; no defaults are baked into the plugin."
    ),
    test_suite="tests/architecture/test_reasoner_role_profile_capability.py",
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
                "phase_think_role_profile.checked",
                "phase_think_role_profile.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("reasoner.role_profile.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Bind the configured ``RoleProfile`` to the ``reasoner.role_profile`` capability."""

    profile = RoleProfile(
        role=config.role,
        goal=config.goal,
        backstory=config.backstory,
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=list(config.allowed_tools)),
    )
    ctx.provide(REASONER_ROLE_PROFILE.key, profile)


__all__ = ["Config", "setup"]
