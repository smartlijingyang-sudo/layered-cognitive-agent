# PR-D final — transport provider (lazy composition)
"""lab.transport provider — InternalTransport + lab_echo agent registration.

Replaces the PR-B marker. The transport is built lazily at call time
so cordis-dependent transitive imports only fire when actually needed.
"""

from __future__ import annotations


def get_transport():
    """Return the lab InternalTransport with lab_echo registered."""
    from lca.infrastructure.transport.agent_transport import InternalTransport
    from lca.contracts.atoms.ids.ids import new_id
    from lca.contracts.models.core.execution.decision import Observation

    transport = InternalTransport()

    async def _echo(subtask):
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=f"echo:{subtask}",
        )

    transport.register_agent("lab_echo", _echo)
    return transport


def reset_for_tests():
    """Test helper — currently a no-op (transport is built fresh each call)."""
    return None


__all__ = ["get_transport", "reset_for_tests"]

# Register loader marker for the capability closure.
from lca.plugins.lab.internal.loader import _LAB_HOOKS
_LAB_HOOKS["lab.transport.provider"] = {"id": "provider", "stage": "composition"}