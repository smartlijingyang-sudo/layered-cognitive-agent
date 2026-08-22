"""Compatibility exports for team transport assembly."""

from lca.plugins.composer.team_transport import (
    build_default_transport_registry,
    build_team_transport,
    call_member_for_channel,
)

__all__ = ["build_default_transport_registry", "build_team_transport", "call_member_for_channel"]
