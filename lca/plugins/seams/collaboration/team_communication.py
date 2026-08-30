"""Default provider for the Team communication assembly capability.

A communication assembler closes the compatible transport and member-invoker
pair after Team members exist.  The implementation is deliberately registered
as its own capability provider, so a profile can replace it without changing
``TeamComposer`` or ``TeamSeamFactory``.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import TEAM_COMMUNICATION
from lca.contracts.protocols.collaboration.agent import AgentUnit
from lca.contracts.protocols.collaboration.team_seam import (
    TeamCommunication,
    TeamCommunicationAssemblerProtocol,
)
from lca.contracts.protocols.journal.spec import TeamSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default in-process communication pair has no configuration."""

    model_config = {"extra": "forbid"}


class DefaultTeamCommunicationAssembler(TeamCommunicationAssemblerProtocol):
    """Build the compatible default transport and member-invoker pair."""

    def assemble(
        self,
        spec: TeamSpec,
        *,
        members: tuple[AgentUnit, ...],
    ) -> TeamCommunication:
        """Close the default communication pair after all members exist."""

        del spec
        from lca.agent.member_invoke import TransportMemberInvoker
        from lca.plugins.composer.team_transport import build_team_transport

        transport = build_team_transport(members)
        return TeamCommunication(
            transport=transport,
            invoker=TransportMemberInvoker(transport),
        )


@plugin(
    id="lca-team-communication-default",
    provides=[TEAM_COMMUNICATION.key],
    requires=[],
    implements=[TeamCommunicationAssemblerProtocol],
    layer="L3",
    effects="none",
    description="Provide the default in-process Team transport and invoker pair.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default communication assembler to the Team seam factory."""

    del config
    ctx.provide(TEAM_COMMUNICATION.key, DefaultTeamCommunicationAssembler())


__all__ = ["Config", "DefaultTeamCommunicationAssembler", "setup"]
