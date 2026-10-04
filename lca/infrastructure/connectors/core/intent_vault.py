"""Connector auth intent vault — Zero Model Exposure (ADR-0280 / INV-CAP-02).

In-memory safe holding area for high-privilege authorization URLs.
Issues short-lived capability tickets (intent_id) so that sensitive URLs
never enter LLM context, prompts, or traces.
"""

from __future__ import annotations

import threading
import time
from typing import ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.connectors.intent import ConnectorAuthIntent


class ConnectorAuthIntentVault:
    """Thread-safe TTL holding vault for connector authorization intents."""

    DEFAULT_TTL_SECONDS: ClassVar[float] = 300.0  # 5 minutes

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._intents: dict[str, ConnectorAuthIntent] = {}

    def _purge_expired_locked(self, now: float) -> None:
        """Evicts expired intents from memory."""
        expired = [k for k, v in self._intents.items() if v.is_expired(now)]
        for k in expired:
            self._intents.pop(k, None)

    def create_intent(
        self,
        *,
        service: str,
        app_name: str,
        auth_url: str,
        connection_id: str,
        user_id: str,
        ttl_seconds: float | None = None,
    ) -> str:
        """Stores an authorization URL and returns a unique intent_id (e.g. cai_xxx)."""
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.DEFAULT_TTL_SECONDS
        intent_id = new_id("cai")

        intent = ConnectorAuthIntent(
            intent_id=intent_id,
            service=service,
            app_name=app_name,
            auth_url=auth_url,
            connection_id=connection_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + ttl,
            consumed=False,
        )

        with self._lock:
            self._purge_expired_locked(now)
            self._intents[intent_id] = intent

        return intent_id

    def resolve_intent(
        self,
        intent_id: str,
        *,
        user_id: str,
    ) -> ConnectorAuthIntent | None:
        """Resolves a valid intent ticket for the specified user.

        Returns None if the intent does not exist, is expired, or belongs to another user.
        Marks the intent as consumed on first resolution.
        """
        if not user_id:
            return None

        now = time.time()
        with self._lock:
            self._purge_expired_locked(now)
            intent = self._intents.get(intent_id)
            if intent is None:
                return None

            # Multi-tenant user isolation check
            if intent.user_id != user_id:
                return None

            # Mark consumed on resolution
            if not intent.consumed:
                intent = intent.mark_consumed()
                self._intents[intent_id] = intent

            return intent


_DEFAULT_INTENT_VAULT: ConnectorAuthIntentVault | None = None


def get_default_intent_vault() -> ConnectorAuthIntentVault:
    """Returns the singleton default ConnectorAuthIntentVault."""
    global _DEFAULT_INTENT_VAULT
    if _DEFAULT_INTENT_VAULT is None:
        _DEFAULT_INTENT_VAULT = ConnectorAuthIntentVault()
    return _DEFAULT_INTENT_VAULT


def set_default_intent_vault(vault: ConnectorAuthIntentVault) -> None:
    """Sets the singleton default ConnectorAuthIntentVault (for testing/mocking)."""
    global _DEFAULT_INTENT_VAULT
    _DEFAULT_INTENT_VAULT = vault


__all__ = [
    "ConnectorAuthIntentVault",
    "get_default_intent_vault",
    "set_default_intent_vault",
]
