"""Shared shell for the plan-bound phase-composer provider registrations.

The three near-identical provider modules (think/brain, perceive, act/body)
differ only in data: plugin id, provides key, authority grants, composer
class, and the plane/interface nouns used in human-readable text. This
factory builds the ``@plugin``-decorated ``setup`` carrier plus the strict
``Config`` model from that data, so registering a fourth phase composer is
one call instead of a copied 66-line file.

Discovery note (RA-008 gate probe): ``lca/harness/profile/resolve`` reads
``module.setup`` -- a single attribute per module. A table-driven loop inside
ONE module cannot expose three registrations (only the last assignment
survives import), which is why the convergence keeps one thin module per
provider, each calling :func:`_register_composer_plugin` once.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from cordis.plugin import Plugin as CordisPlugin


def _register_composer_plugin(
    *,
    plane_key: str,
    plane_noun: str,
    interface: str,
    grants: tuple[str, ...],
    composer_cls: Callable[[], Any],
) -> tuple[CordisPlugin, type[BaseModel]]:
    """Build the ``(setup, Config)`` pair for one phase-composer provider module.

    ``plane_key`` feeds the machine-derived fields: plugin id
    (``lca-plan-<key>-composer``), provides key (``composer.<key>``),
    observability descriptors and ownership reads/emits. ``plane_noun`` and
    ``interface`` only feed human-readable text. Authority grants stay
    per-provider data (perceive uses ``context.read``, the others
    ``plugin.serve``).
    """
    plugin_id = f"lca-plan-{plane_key}-composer"
    provides_key = f"composer.{plane_key}"

    class Config(BaseModel):
        model_config = ConfigDict(extra="forbid")

    Config.__doc__ = f"Strict configuration for the built-in {plane_key} composer provider."

    async def setup(ctx: PluginContext, config: Config) -> None:
        del config
        ctx.provide(provides_key, composer_cls())

    setup.__doc__ = f"Provide only the profile-selected {plane_noun} graph composer."

    decorated = plugin(
        id=plugin_id,
        provides=[provides_key],
        requires=[],
        implements=["AgentGraphComposer"],
        layer="L4",
        effects="none",
        description=f"Plan-bound {plane_noun} composer with a narrow {interface} interface.",
        test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
        kind=PluginKind.PROVIDER,
        contract=PluginContract(
            identity=PluginIdentity(version="v1"),
            architecture=ArchitectureContract(
                group=FunctionalGroup.G10_COMPOSITION,
                control_slots=(ControlSlot.OBSERVE_WILDCARD,),
            ),
            lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
            authority=AuthorityContract(grants=grants),
            observability=EvidenceContract(
                descriptors=(f"{plugin_id}.checked", f"{plugin_id}.served")
            ),
        ),
        relations=(),
        ownership=OwnershipDeclaration(
            reads=(provides_key,),
            emits=(f"{provides_key}.checked",),
            state_mutation="forbidden",
        ),
    )(setup)

    return decorated, Config


__all__ = ["_register_composer_plugin"]
