"""Auto-generated surface skeleton for upstream ``typert/generator/src/analyzer.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``typert/generator/src/analyzer.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AnalysisMode",
    "DiscoveredTypertPackage",
    "PackageRegistration",
    "ParsedConfig",
    "TypertAnalysisError",
    "WorkspaceAnalyzer",
    "WorkspaceAnalyzerOptions",
    "WorkspaceCaches",
]

AnalysisMode: TypeAlias = object  # port: surface stub

class TypertAnalysisError:
    """Surface stub for upstream class ``TypertAnalysisError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TypertAnalysisError.__init__ from typert/generator/src/analyzer.ts")

class WorkspaceAnalyzer:
    """Surface stub for upstream class ``WorkspaceAnalyzer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceAnalyzer.__init__ from typert/generator/src/analyzer.ts")

class WorkspaceCaches:
    """Surface stub for upstream class ``WorkspaceCaches``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port WorkspaceCaches.__init__ from typert/generator/src/analyzer.ts")

class DiscoveredTypertPackage(Protocol):
    """Surface stub for upstream interface ``DiscoveredTypertPackage``."""
    pass

class PackageRegistration(Protocol):
    """Surface stub for upstream interface ``PackageRegistration``."""
    pass

class ParsedConfig(Protocol):
    """Surface stub for upstream interface ``ParsedConfig``."""
    pass

class WorkspaceAnalyzerOptions(Protocol):
    """Surface stub for upstream interface ``WorkspaceAnalyzerOptions``."""
    pass
