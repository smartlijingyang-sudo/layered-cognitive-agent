"""Auto-generated surface skeleton for upstream ``skill/skill/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``skill/skill/src/index.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BUNDLED_SKILL_RANK",
    "Config",
    "SkillCandidate",
    "SkillCatalogSnapshot",
    "SkillDefinition",
    "SkillInvocationPolicy",
    "SkillInvocationSource",
    "SkillLookupOptions",
    "SkillProvider",
    "SkillProviderControl",
    "SkillProviderObservation",
    "SkillRegistration",
    "SkillRegistry",
    "SkillResourceBase",
    "SkillSource",
    "SkillSummary",
    "SkillViewOptions",
    "escapeText",
    "isModelInvocable",
    "isSkillName",
    "isUserInvocable",
    "renderSkillContent",
]

SkillRegistration: TypeAlias = object  # port: surface stub

SkillResourceBase: TypeAlias = object  # port: surface stub

SkillSource: TypeAlias = object  # port: surface stub

BUNDLED_SKILL_RANK = None  # port: surface stub

def escapeText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``escapeText``."""
    raise NotImplementedError("port escapeText from skill/skill/src/index.ts")

def isModelInvocable(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isModelInvocable``."""
    raise NotImplementedError("port isModelInvocable from skill/skill/src/index.ts")

def isSkillName(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isSkillName``."""
    raise NotImplementedError("port isSkillName from skill/skill/src/index.ts")

def isUserInvocable(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isUserInvocable``."""
    raise NotImplementedError("port isUserInvocable from skill/skill/src/index.ts")

def renderSkillContent(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderSkillContent``."""
    raise NotImplementedError("port renderSkillContent from skill/skill/src/index.ts")

class SkillRegistry:
    """Surface stub for upstream class ``SkillRegistry``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SkillRegistry.__init__ from skill/skill/src/index.ts")

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class SkillCandidate(Protocol):
    """Surface stub for upstream interface ``SkillCandidate``."""
    pass

class SkillCatalogSnapshot(Protocol):
    """Surface stub for upstream interface ``SkillCatalogSnapshot``."""
    pass

class SkillDefinition(Protocol):
    """Surface stub for upstream interface ``SkillDefinition``."""
    pass

class SkillInvocationPolicy(Protocol):
    """Surface stub for upstream interface ``SkillInvocationPolicy``."""
    pass

class SkillInvocationSource(Protocol):
    """Surface stub for upstream interface ``SkillInvocationSource``."""
    pass

class SkillLookupOptions(Protocol):
    """Surface stub for upstream interface ``SkillLookupOptions``."""
    pass

class SkillProvider(Protocol):
    """Surface stub for upstream interface ``SkillProvider``."""
    pass

class SkillProviderControl(Protocol):
    """Surface stub for upstream interface ``SkillProviderControl``."""
    pass

class SkillProviderObservation(Protocol):
    """Surface stub for upstream interface ``SkillProviderObservation``."""
    pass

class SkillSummary(Protocol):
    """Surface stub for upstream interface ``SkillSummary``."""
    pass

class SkillViewOptions(Protocol):
    """Surface stub for upstream interface ``SkillViewOptions``."""
    pass
