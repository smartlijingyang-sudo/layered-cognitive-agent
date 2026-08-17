"""Auto-generated surface skeleton for upstream ``typert/protocol/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/protocol/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "InvocationDescriptor",
    "InvocationParameterDescriptor",
    "InvocationSourceLocation",
    "RemoteFailure",
    "RemoteResult",
    "TypertClientContextBinder",
    "TypertClientRemote",
    "TypertCodec",
    "TypertContext",
    "TypertContextMap",
    "TypertContextRegistry",
    "TypertContextWire",
    "TypertDisposer",
    "TypertForwardableEvent",
    "TypertHostContextProvider",
    "TypertHostContextResolver",
    "TypertLocalRegistry",
    "TypertLookup",
    "TypertLookupDefinition",
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
    "TypertSchema",
]

RemoteResult: TypeAlias = object  # port: surface stub

TypertCodec: TypeAlias = object  # port: surface stub

TypertContextWire: TypeAlias = object  # port: surface stub

TypertDisposer: TypeAlias = object  # port: surface stub

TypertForwardableEvent: TypeAlias = object  # port: surface stub

TypertHostContextResolver: TypeAlias = object  # port: surface stub

TypertLookupHost: TypeAlias = object  # port: surface stub

TypertLookupResolver: TypeAlias = object  # port: surface stub

TypertLookupWire: TypeAlias = object  # port: surface stub

TypertRegistryListener: TypeAlias = object  # port: surface stub

TypertRemoteEvent: TypeAlias = object  # port: surface stub

TypertRemoteNamespace: TypeAlias = object  # port: surface stub

TypertRemoteScopeApi: TypeAlias = object  # port: surface stub

TypertRemoteScopeNamespace: TypeAlias = object  # port: surface stub

class InvocationDescriptor(Protocol):
    """Surface stub for upstream interface ``InvocationDescriptor``."""
    pass

class InvocationParameterDescriptor(Protocol):
    """Surface stub for upstream interface ``InvocationParameterDescriptor``."""
    pass

class InvocationSourceLocation(Protocol):
    """Surface stub for upstream interface ``InvocationSourceLocation``."""
    pass

class RemoteFailure(Protocol):
    """Surface stub for upstream interface ``RemoteFailure``."""
    pass

class TypertClientContextBinder(Protocol):
    """Surface stub for upstream interface ``TypertClientContextBinder``."""
    pass

class TypertClientRemote(Protocol):
    """Surface stub for upstream interface ``TypertClientRemote``."""
    pass

class TypertContext(Protocol):
    """Surface stub for upstream interface ``TypertContext``."""
    pass

class TypertContextMap(Protocol):
    """Surface stub for upstream interface ``TypertContextMap``."""
    pass

class TypertContextRegistry(Protocol):
    """Surface stub for upstream interface ``TypertContextRegistry``."""
    pass

class TypertHostContextProvider(Protocol):
    """Surface stub for upstream interface ``TypertHostContextProvider``."""
    pass

class TypertLocalRegistry(Protocol):
    """Surface stub for upstream interface ``TypertLocalRegistry``."""
    pass

class TypertLookup(Protocol):
    """Surface stub for upstream interface ``TypertLookup``."""
    pass

class TypertLookupDefinition(Protocol):
    """Surface stub for upstream interface ``TypertLookupDefinition``."""
    pass

class TypertLookupMap(Protocol):
    """Surface stub for upstream interface ``TypertLookupMap``."""
    pass

class TypertLookupProvider(Protocol):
    """Surface stub for upstream interface ``TypertLookupProvider``."""
    pass

class TypertLookupRegistry(Protocol):
    """Surface stub for upstream interface ``TypertLookupRegistry``."""
    pass

class TypertRegistryChange(Protocol):
    """Surface stub for upstream interface ``TypertRegistryChange``."""
    pass

class TypertRegistryContract(Protocol):
    """Surface stub for upstream interface ``TypertRegistryContract``."""
    pass

class TypertRemoteContribution(Protocol):
    """Surface stub for upstream interface ``TypertRemoteContribution``."""
    pass

class TypertRemoteEventSelection(Protocol):
    """Surface stub for upstream interface ``TypertRemoteEventSelection``."""
    pass

class TypertRemoteMap(Protocol):
    """Surface stub for upstream interface ``TypertRemoteMap``."""
    pass

class TypertRemoteNamespaceMap(Protocol):
    """Surface stub for upstream interface ``TypertRemoteNamespaceMap``."""
    pass

class TypertRemoteRegistry(Protocol):
    """Surface stub for upstream interface ``TypertRemoteRegistry``."""
    pass

class TypertRemoteScopeMap(Protocol):
    """Surface stub for upstream interface ``TypertRemoteScopeMap``."""
    pass

class TypertSchema(Protocol):
    """Surface stub for upstream interface ``TypertSchema``."""
    pass
