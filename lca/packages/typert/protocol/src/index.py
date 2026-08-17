"""Auto-generated surface skeleton for upstream ``typert/protocol/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/protocol/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "InvocationDescriptor",
    "InvocationParameterDescriptor",
    "InvocationSourceLocation",
    "Remote",
    "RemoteFailure",
    "RemoteInvocationMarker",
    "RemoteMethodMarker",
    "RemoteResult",
    "RemoteScope",
    "TypertClientContextBinder",
    "TypertClientRemote",
    "TypertCodec",
    "TypertContext",
    "TypertContextMap",
    "TypertContextRegistry",
    "TypertContextWire",
    "TypertDisposer",
    "TypertForwardableEvent",
    "TypertGatewayBinding",
    "TypertGatewayBindingOptions",
    "TypertHostContextProvider",
    "TypertHostContextResolver",
    "TypertLocalRegistry",
    "TypertLookup",
    "TypertLookupDefinition",
    "TypertLookupFailure",
    "TypertLookupHost",
    "TypertLookupMap",
    "TypertLookupProvider",
    "TypertLookupRegistry",
    "TypertLookupResolver",
    "TypertLookupWire",
    "TypertRegistryChange",
    "TypertRegistryContract",
    "TypertRegistryListener",
    "TypertRemoteContribution",
    "TypertRemoteEvent",
    "TypertRemoteEventSelection",
    "TypertRemoteMap",
    "TypertRemoteNamespace",
    "TypertRemoteNamespaceMap",
    "TypertRemoteRegistry",
    "TypertRemoteScopeApi",
    "TypertRemoteScopeMap",
    "TypertRemoteScopeNamespace",
    "TypertRemoteService",
    "TypertSchema",
    "bindTypertRemote",
    "isTypertRemoteSegment",
    "remoteMethods",
]

InvocationDescriptor: TypeAlias = object  # port: surface stub

InvocationParameterDescriptor: TypeAlias = object  # port: surface stub

InvocationSourceLocation: TypeAlias = object  # port: surface stub

RemoteFailure: TypeAlias = object  # port: surface stub

RemoteInvocationMarker: TypeAlias = object  # port: surface stub

RemoteResult: TypeAlias = object  # port: surface stub

TypertClientContextBinder: TypeAlias = object  # port: surface stub

TypertClientRemote: TypeAlias = object  # port: surface stub

TypertCodec: TypeAlias = object  # port: surface stub

TypertContext: TypeAlias = object  # port: surface stub

TypertContextMap: TypeAlias = object  # port: surface stub

TypertContextRegistry: TypeAlias = object  # port: surface stub

TypertContextWire: TypeAlias = object  # port: surface stub

TypertDisposer: TypeAlias = object  # port: surface stub

TypertForwardableEvent: TypeAlias = object  # port: surface stub

TypertHostContextProvider: TypeAlias = object  # port: surface stub

TypertHostContextResolver: TypeAlias = object  # port: surface stub

TypertLocalRegistry: TypeAlias = object  # port: surface stub

TypertLookup: TypeAlias = object  # port: surface stub

TypertLookupDefinition: TypeAlias = object  # port: surface stub

TypertLookupHost: TypeAlias = object  # port: surface stub

TypertLookupMap: TypeAlias = object  # port: surface stub

TypertLookupProvider: TypeAlias = object  # port: surface stub

TypertLookupRegistry: TypeAlias = object  # port: surface stub

TypertLookupResolver: TypeAlias = object  # port: surface stub

TypertLookupWire: TypeAlias = object  # port: surface stub

TypertRegistryChange: TypeAlias = object  # port: surface stub

TypertRegistryContract: TypeAlias = object  # port: surface stub

TypertRegistryListener: TypeAlias = object  # port: surface stub

TypertRemoteContribution: TypeAlias = object  # port: surface stub

TypertRemoteEvent: TypeAlias = object  # port: surface stub

TypertRemoteEventSelection: TypeAlias = object  # port: surface stub

TypertRemoteMap: TypeAlias = object  # port: surface stub

TypertRemoteNamespace: TypeAlias = object  # port: surface stub

TypertRemoteNamespaceMap: TypeAlias = object  # port: surface stub

TypertRemoteRegistry: TypeAlias = object  # port: surface stub

TypertRemoteScopeApi: TypeAlias = object  # port: surface stub

TypertRemoteScopeMap: TypeAlias = object  # port: surface stub

TypertRemoteScopeNamespace: TypeAlias = object  # port: surface stub

TypertSchema: TypeAlias = object  # port: surface stub

def Remote(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``Remote``."""
    raise NotImplementedError("port Remote from typert/protocol/src/index.ts")

def RemoteScope(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``RemoteScope``."""
    raise NotImplementedError("port RemoteScope from typert/protocol/src/index.ts")

def bindTypertRemote(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``bindTypertRemote``."""
    raise NotImplementedError("port bindTypertRemote from typert/protocol/src/index.ts")

def isTypertRemoteSegment(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isTypertRemoteSegment``."""
    raise NotImplementedError("port isTypertRemoteSegment from typert/protocol/src/index.ts")

def remoteMethods(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``remoteMethods``."""
    raise NotImplementedError("port remoteMethods from typert/protocol/src/index.ts")

class TypertLookupFailure:
    """Surface stub for upstream class ``TypertLookupFailure``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TypertLookupFailure.__init__ from typert/protocol/src/index.ts")

class TypertRemoteService:
    """Surface stub for upstream class ``TypertRemoteService``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TypertRemoteService.__init__ from typert/protocol/src/index.ts")

class RemoteMethodMarker(Protocol):
    """Surface stub for upstream interface ``RemoteMethodMarker``."""
    pass

class TypertGatewayBinding(Protocol):
    """Surface stub for upstream interface ``TypertGatewayBinding``."""
    pass

class TypertGatewayBindingOptions(Protocol):
    """Surface stub for upstream interface ``TypertGatewayBindingOptions``."""
    pass
