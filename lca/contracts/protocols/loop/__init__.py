"""Loop 机制层契约协议(ADR-0194 §3.1)。"""

from lca.contracts.protocols.loop.fact_gateway import (
    AppendReceipt,
    DiagnosticFact,
    FactGateway,
    SessionCatalogEvent,
    SpineExecutionPoint,
)

__all__ = [
    "AppendReceipt",
    "DiagnosticFact",
    "FactGateway",
    "SessionCatalogEvent",
    "SpineExecutionPoint",
]
