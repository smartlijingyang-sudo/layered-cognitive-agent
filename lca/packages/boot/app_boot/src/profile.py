"""Auto-generated surface skeleton for upstream ``boot/app-boot/src/profile.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``boot/app-boot/src/profile.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_PROFILE_BUNDLES",
    "DshBundleManifest",
    "DshManifestSection",
    "DshProfileManifest",
    "PROFILES_DIR",
    "PROFILE_PATCH_FILENAME",
    "PROFILE_TEMPLATES",
    "Profile",
    "ProfileLayer",
    "ProfileManifest",
    "composeEntries",
    "healProfilesModuleFallback",
    "initProfile",
    "loadProfile",
    "readProfileManifest",
    "resolveBundleDir",
    "resolveProfileDir",
    "writeProfileManifest",
]

DEFAULT_PROFILE_BUNDLES = None  # port: surface stub

PROFILES_DIR = None  # port: surface stub

PROFILE_PATCH_FILENAME = None  # port: surface stub

PROFILE_TEMPLATES = None  # port: surface stub

def composeEntries(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``composeEntries``."""
    raise NotImplementedError("port composeEntries from boot/app-boot/src/profile.ts")

def healProfilesModuleFallback(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``healProfilesModuleFallback``."""
    raise NotImplementedError("port healProfilesModuleFallback from boot/app-boot/src/profile.ts")

def initProfile(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``initProfile``."""
    raise NotImplementedError("port initProfile from boot/app-boot/src/profile.ts")

def loadProfile(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadProfile``."""
    raise NotImplementedError("port loadProfile from boot/app-boot/src/profile.ts")

def readProfileManifest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``readProfileManifest``."""
    raise NotImplementedError("port readProfileManifest from boot/app-boot/src/profile.ts")

def resolveBundleDir(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveBundleDir``."""
    raise NotImplementedError("port resolveBundleDir from boot/app-boot/src/profile.ts")

def resolveProfileDir(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveProfileDir``."""
    raise NotImplementedError("port resolveProfileDir from boot/app-boot/src/profile.ts")

def writeProfileManifest(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``writeProfileManifest``."""
    raise NotImplementedError("port writeProfileManifest from boot/app-boot/src/profile.ts")

class DshBundleManifest(Protocol):
    """Surface stub for upstream interface ``DshBundleManifest``."""
    pass

class DshManifestSection(Protocol):
    """Surface stub for upstream interface ``DshManifestSection``."""
    pass

class DshProfileManifest(Protocol):
    """Surface stub for upstream interface ``DshProfileManifest``."""
    pass

class Profile(Protocol):
    """Surface stub for upstream interface ``Profile``."""
    pass

class ProfileLayer(Protocol):
    """Surface stub for upstream interface ``ProfileLayer``."""
    pass

class ProfileManifest(Protocol):
    """Surface stub for upstream interface ``ProfileManifest``."""
    pass
