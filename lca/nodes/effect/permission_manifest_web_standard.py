"""phase.concept.effect.permission_manifest_web_standard — allowlist provider.

Profile-level counterpart to ``permission_manifest_default``: ships an
allowlist covering the envelope effect operations registered by the
standard handlers (``body.act`` for tool execution, ``memory.update``
for state observation append). The ``web-app`` bundle installs this
plugin; ``web-standard`` profile patches out the deny-by-default so
the resolver picks the allowlist as the first ``permission_manifest.*``
match (pre_dispatch_envelope_check picks via ``next(iter(matches))``).

Boundary discipline (AGENTS.md §3):

- Pure construction: no I/O, no ``AgentState`` reads, no env access.
- Capability, not behavior: this plugin decides nothing — the gate at
  ``effect.pre_dispatch.envelope_check`` owns the permission verdict.
- AGENTS.md §3 C13: ``ToolPermissionManifest`` is the existing
  Pydantic-frozen DTO; we re-export it under the
  ``permission_manifest.web_standard`` key without inventing a parallel
  schema.
- Per-tool permission scope (which concrete tool name a role may
  invoke) remains on ``RoleProfile.tool_permission_manifest``; this
  provider only declares the effect-op allowlist the envelope gate
  reads. Role and profile are two distinct policy layers.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_PROVIDES_KEY = "permission_manifest.web_standard"

# Envelope effect operations shipped by ``lca-effect-handler-provider``
# (``body.act`` / ``memory.update``). Keep in sync with that registry.
_DEFAULT_ALLOWED_OPERATIONS: tuple[str, ...] = (
    "body.act",
    "memory.update",
)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_operations: tuple[str, ...] = _DEFAULT_ALLOWED_OPERATIONS


@plugin(
    id="lca-effect-permission-manifest-web-standard",
    Config=Config,
    provides=(_PROVIDES_KEY,),
    requires=(),
    layer="L2",
    effects="none",
    description=(
        "Web-standard allowlist ToolPermissionManifest for the "
        "envelope-check permission gate. Installed by web-app bundle; "
        "web-standard profile patches out the deny-by-default."
    ),
    test_suite="tests/architecture/test_permission_manifest_web_standard.py",
    kind=PluginKind.PROVIDER,
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
                "lca-effect-permission-manifest-web-standard.checked",
                "lca-effect-permission-manifest-web-standard.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the web-standard allowlist ``ToolPermissionManifest``."""
    manifest = ToolPermissionManifest(allowed_tools=list(config.allowed_operations))
    ctx.provide(_PROVIDES_KEY, manifest)


__all__ = ["Config"]
