"""Connected external services prompt section — Muse 7-layer architecture.

Provides prior knowledge of authorized and active third-party integrations
so that the agent is aware of its connectivity without metadata overflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.infrastructure.connectors.core.vault import ConnectorVault


def render_connected_services_text(
    vault: ConnectorVault | None = None,
    max_services: int = 5,
) -> str:
    """Renders a concise summary of active third-party services with budget protection (max 100 tokens)."""
    active_vault = vault or ConnectorVault()
    active_services = active_vault.list_active_services()

    lines = ["## Connected External Services"]
    if not active_services:
        lines.append("No external services are currently connected.")
        lines.append(
            "When external services are needed, check status and use interactive authorization cards."
        )
    else:
        lines.append(
            "The following external integrations are currently authorized and ACTIVE for this agent:"
        )
        sorted_services = sorted(active_services)
        displayed = sorted_services[:max_services]
        for svc in displayed:
            lines.append(f"- {svc} (status: ACTIVE)")
        if len(sorted_services) > max_services:
            remaining = len(sorted_services) - max_services
            lines.append(f"- ... and {remaining} more active services")
        lines.append(
            "You can directly read, search, and perform allowed actions with these connected services."
        )

    return "\n".join(lines)


class ConnectedServicesSection:
    """Prompt section injecting active external connector metadata."""

    name: ClassVar[str] = "connected_services"

    def __init__(self, vault: ConnectorVault | None = None) -> None:
        self._vault = vault

    def render(self, *, role_profile: RoleProfile, tools: Sequence[Tool]) -> SectionOutput:
        del role_profile, tools
        return SectionOutput(text=render_connected_services_text(vault=self._vault))


def build_connected_services(config: BaseModel) -> ConnectedServicesSection:
    del config
    return ConnectedServicesSection()


__all__ = [
    "ConnectedServicesSection",
    "build_connected_services",
    "render_connected_services_text",
]
