"""phase.concept.effect.permission_manifest_default — typed-port permission manifest provider.

PR-2 (commit 39fa69654, ADR-0234) extracted the 5-gate envelope check into
a typed-port graph node and declared ``requires=("permission_manifest",)``
on the plugin, but never wired a producer for that capability into the
resolved profile. The kernel only fails loud when the plugin reaches
``setup()`` — i.e. after plan_lift, when the undeclared-interaction
guard trips. Without this producer every profile fails boot with
``Missing capability: permission_manifest``.

This adapter ships a deny-by-default ``ToolPermissionManifest`` so the
envelope-check permission gate is fail-loud in the absence of profile
policy (the executor raises ``ValueError("permission denied ...")``
when ``allowed_tools`` is empty / unset, which is the safe default
and matches the executor's "manifest is None → deny" branch).
Production profiles that need allowlist semantics should override this
provider with a profile-bundled adapter that ships the actual policy.

Boundary discipline (AGENTS.md §3):

- Pure construction: no I/O, no ``AgentState`` reads, no env access.
- Capability, not behavior: this plugin decides nothing — it hands the
  manifest to ``effect.pre_dispatch.envelope_check`` which owns the
  permission decision.
- AGENTS.md §3 C13: ``ToolPermissionManifest`` is the existing
  Pydantic-frozen DTO under ``lca.contracts.models.team.role.team``;
  we re-export it under the plugin-graph ``permission_manifest.default``
  key without inventing a parallel schema.
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

_PROVIDES_KEY = "permission_manifest.default"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-effect-permission-manifest-default",
    Config=None,
    provides=(_PROVIDES_KEY,),
    requires=(),
    layer="L2",
    effects="none",
    description=(
        "Deny-by-default ToolPermissionManifest for the envelope-check "
        "permission gate (PR-2 close-out; ships empty allowed_tools)."
    ),
    test_suite="tests/architecture/test_permission_manifest_default.py",
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
                "lca-effect-permission-manifest-default.checked",
                "lca-effect-permission-manifest-default.served",
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
    """Provide a deny-by-default ``ToolPermissionManifest``.

    ``allowed_tools = ()`` makes the permission gate reject every
    envelope, which is the safe default until a profile bundles a
    policy-aware adapter. Profiles that need allowlist semantics
    should ship their own ``permission_manifest.<name>`` provider
    in ``bundles/<profile>/...`` and disable this one.
    """
    del config
    manifest = ToolPermissionManifest(allowed_tools=())
    ctx.provide(_PROVIDES_KEY, manifest)


__all__ = ["Config", "setup"]