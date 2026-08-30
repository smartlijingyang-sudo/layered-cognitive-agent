"""Plan-bound composition for the organization and interaction cluster."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.capabilities import STRATEGIES, TEAM_SEAM
from lca.contracts.harness.composer import TeamGraph
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols import TeamAssembly, TeamStage
from lca.contracts.protocols.spec import LeadSpec, TeamSpec, strategy_key_for_governance
from lca.plugins.composer.agent_assembly import AgentAssemblyPort
from lca.plugins.composer.internal.team import resolve_team_observability

if TYPE_CHECKING:
    from cordis import Context


class TeamComposer:
    """Compose collaboration through the explicit Agent assembly seam.

    This organization-plane module owns team-scoped ordering: resolve shared
    memory before a single member assembly pass, close the profile-selected
    communication seam, then create the governance strategy. It does not
    select or construct any backend itself.
    """

    key = "team"

    def __init__(self, agent_assembler: AgentAssemblyPort) -> None:
        self._agent_assembler = agent_assembler

    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph:
        """Return a complete TeamGraph using only booted profile capabilities."""

        observability = resolve_team_observability(spec, scope)
        seam_factory = require_capability(scope, TEAM_SEAM.key)
        shared_store = seam_factory.resolve_shared_memory(spec)
        members = tuple(
            self._agent_assembler.assemble_member(
                member,
                shared_store=shared_store,
                observability=observability,
                scope=scope,
            )
            for member in spec.members
        )
        roles = [member.role_profile.role for member in members]
        if any(not role for role in roles) or len(set(roles)) != len(roles):
            raise ValueError("team member roles must be non-empty and unique")
        seam = seam_factory.build(spec, members=members, shared_memory=shared_store)
        if seam.shared_memory is not shared_store:
            raise ValueError("team seam must retain the shared memory it resolved")
        stage = TeamStage(members=members, invoker=seam.invoker)
        lead = (
            self._agent_assembler.assemble_lead(
                spec.governance.agent,
                transport=seam.transport,
                mandate=spec.governance.mandate,
                observability=observability,
                scope=scope,
            )
            if isinstance(spec.governance, LeadSpec)
            else None
        )
        assembly = TeamAssembly(
            governance=spec.governance,
            stage=stage,
            lead=lead,
            delegate_max_attempts=spec.delegate_max_attempts,
        )
        return TeamGraph(
            members=members,
            strategy=require_capability(scope, STRATEGIES.key).create(
                strategy_key_for_governance(spec.governance), assembly
            ),
            stage=stage,
            transport=seam.transport,
            observability=observability,
            lead=lead,
            metadata={"composer": self.key},
        )


__all__ = ["TeamComposer"]
