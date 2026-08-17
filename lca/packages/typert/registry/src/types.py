"""Auto-generated surface skeleton for upstream ``typert/registry/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/registry/src/types.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "TypertContribution",
    "TypertDocTag",
    "TypertDocumentation",
    "TypertEventModel",
    "TypertFace",
    "TypertMemberModel",
    "TypertObjectModel",
    "TypertPackageFilter",
    "TypertPackageModel",
    "TypertPackageRecord",
    "TypertSchema",
    "TypertSchemaFilter",
    "TypertSchemaRecord",
    "TypertServiceModel",
    "TypertTypeModel",
]

TypertFace: TypeAlias = object  # port: surface stub

class TypertContribution(Protocol):
    """Surface stub for upstream interface ``TypertContribution``."""
    pass

class TypertDocTag(Protocol):
    """Surface stub for upstream interface ``TypertDocTag``."""
    pass

class TypertDocumentation(Protocol):
    """Surface stub for upstream interface ``TypertDocumentation``."""
    pass

class TypertEventModel(Protocol):
    """Surface stub for upstream interface ``TypertEventModel``."""
    pass

class TypertMemberModel(Protocol):
    """Surface stub for upstream interface ``TypertMemberModel``."""
    pass

class TypertObjectModel(Protocol):
    """Surface stub for upstream interface ``TypertObjectModel``."""
    pass

class TypertPackageFilter(Protocol):
    """Surface stub for upstream interface ``TypertPackageFilter``."""
    pass

class TypertPackageModel(Protocol):
    """Surface stub for upstream interface ``TypertPackageModel``."""
    pass

class TypertPackageRecord(Protocol):
    """Surface stub for upstream interface ``TypertPackageRecord``."""
    pass

class TypertSchema(Protocol):
    """Surface stub for upstream interface ``TypertSchema``."""
    pass

class TypertSchemaFilter(Protocol):
    """Surface stub for upstream interface ``TypertSchemaFilter``."""
    pass

class TypertSchemaRecord(Protocol):
    """Surface stub for upstream interface ``TypertSchemaRecord``."""
    pass

class TypertServiceModel(Protocol):
    """Surface stub for upstream interface ``TypertServiceModel``."""
    pass

class TypertTypeModel(Protocol):
    """Surface stub for upstream interface ``TypertTypeModel``."""
    pass
