"""Connector Pre-Execution Guard (INV-CONN-02).

Enforces fail-closed state verification at the tool execution boundary.
Raises ConnectionNotActiveError if the service is not active for the user.
"""

from __future__ import annotations

from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError
from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault


class ConnectorPreExecutionGuard:
    """Pre-execution guard verifying connector active status from SSOT vault."""

    def __init__(self, vault: ConnectorVault | None = None) -> None:
        self._vault = vault or ConnectorVault()

    @property
    def vault(self) -> ConnectorVault:
        return self._vault

    def ensure_active(self, service: str) -> None:
        """Verifies that the requested service is in ACTIVE state in the user's SSOT vault.

        Raises:
            ConnectionNotActiveError: if the connector is not currently ACTIVE.
        """
        service_norm = service.lower().strip()
        conn = self._vault.get_connection(service_norm)
        if conn is None or conn.state != ConnectionState.ACTIVE:
            state_str = conn.state.value if conn else ConnectionState.NOT_CONNECTED.value
            raise ConnectionNotActiveError(
                service=service_norm,
                user_id=self._vault.user_id,
                state=state_str,
            )
