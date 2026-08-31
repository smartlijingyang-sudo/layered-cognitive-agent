"""ArtifactClosure Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.artifact_closure import ArtifactClosure
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.workspace import get_run_workspace


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class DefaultArtifactClosure(ArtifactClosure):
    """Default ArtifactClosure implementation.

    Synthesizes artifact closure text from the workspace ledger through the
    profile-selected ``artifact_closure`` seam.
    """

    def synthesize(self, *, fallback: str = "") -> str | None:
        """Synthesize artifact closure text.

        Args:
            fallback: Fallback text if no closure can be synthesized.

        Returns:
            Closure text or None if not available.
        """
        workspace = get_run_workspace()
        if workspace is None:
            return fallback or None
        text = workspace.artifacts.closure_text()
        return text or fallback or None


@plugin(
    id="lca-artifact-closure-provider",
    provides=["artifact_closure"],
    implements=[ArtifactClosure],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description="Provide the default ArtifactClosure implementation.",
    test_suite="tests/test_plugin_alignment.py::test_tier2_plugin_shape",
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-artifact-closure-provider.checked", "lca-artifact-closure-provider.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("artifact_closure",),
        emits=("artifact_closure.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("artifact_closure", DefaultArtifactClosure())


__all__ = ["DefaultArtifactClosure", "setup"]
