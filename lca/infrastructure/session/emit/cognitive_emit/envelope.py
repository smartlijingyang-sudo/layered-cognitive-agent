"""Shared Session-bound envelope primitives for cognitive event families.

Re-exports the FactGateway envelope calls (``append_catalog_bound`` for
catalog facts, ``publish_ep_bound`` for spine EPs) that every cognitive
event-family emitter uses. All emitters no-op when no Session is bound
(tests / offline).
"""

from __future__ import annotations

from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound

__all__ = ["AppendReceipt", "append_catalog_bound", "publish_ep_bound"]
