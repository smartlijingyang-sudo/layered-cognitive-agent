"""Auto-generated surface skeleton for upstream ``host/apiproxy/src/api/rpc.schema.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``host/apiproxy/src/api/rpc.schema.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "Wire",
    "clientRequestSchema",
    "clientResponseSchema",
    "rpcErrorSchema",
    "rpcIdSchema",
    "rpcMessageSchema",
    "rpcReceiptSchema",
    "rpcResultSchema",
    "serverRequestSchema",
    "serverResponseSchema",
]

Wire: TypeAlias = object  # port: surface stub

clientRequestSchema = None  # port: surface stub

clientResponseSchema = None  # port: surface stub

rpcErrorSchema = None  # port: surface stub

rpcIdSchema = None  # port: surface stub

rpcMessageSchema = None  # port: surface stub

rpcReceiptSchema = None  # port: surface stub

serverRequestSchema = None  # port: surface stub

serverResponseSchema = None  # port: surface stub

def rpcResultSchema(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``rpcResultSchema``."""
    raise NotImplementedError("port rpcResultSchema from host/apiproxy/src/api/rpc.schema.ts")
