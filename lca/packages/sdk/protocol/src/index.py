"""Auto-generated surface skeleton for upstream ``sdk/protocol/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sdk/protocol/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "HarnessSdkNotificationMap",
    "HarnessSdkRequestMap",
    "InitializeParams",
    "InitializeResult",
    "JsonRpcLineTransport",
    "JsonRpcResponseError",
    "JsonRpcTransportPeer",
    "SdkRunStatus",
    "SessionEventNotification",
    "SessionPromptParams",
    "SessionPromptResult",
    "SessionStatusNotification",
    "SubagentFinishedNotification",
    "SubagentStartedNotification",
]

HarnessSdkNotificationMap: TypeAlias = object  # port: surface stub

HarnessSdkRequestMap: TypeAlias = object  # port: surface stub

InitializeParams: TypeAlias = object  # port: surface stub

InitializeResult: TypeAlias = object  # port: surface stub

JsonRpcTransportPeer: TypeAlias = object  # port: surface stub

SdkRunStatus: TypeAlias = object  # port: surface stub

SessionEventNotification: TypeAlias = object  # port: surface stub

SessionPromptParams: TypeAlias = object  # port: surface stub

SessionPromptResult: TypeAlias = object  # port: surface stub

SessionStatusNotification: TypeAlias = object  # port: surface stub

SubagentFinishedNotification: TypeAlias = object  # port: surface stub

SubagentStartedNotification: TypeAlias = object  # port: surface stub

JsonRpcLineTransport = None  # port: surface stub (reexport)

JsonRpcResponseError = None  # port: surface stub (reexport)
