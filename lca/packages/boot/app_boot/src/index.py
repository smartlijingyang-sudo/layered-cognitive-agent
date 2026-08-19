"""Auto-generated surface skeleton for upstream ``boot/app-boot/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``boot/app-boot/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "DEFAULT_PROFILE_BUNDLES",
    "FAIL_LOUD_RELEASE_TIMEOUT_MS",
    "HARNESS_SOURCE_SECTION",
    "PROFILES_DIR",
    "PROFILE_PATCH_FILENAME",
    "PROFILE_TEMPLATES",
    "ConfigDumpLayer",
    "DshBundleManifest",
    "DshManifestSection",
    "DshProfileManifest",
    "FailLoudProcess",
    "Profile",
    "ProfileLayer",
    "ProfileManifest",
    "UserPatchWatchOptions",
    "addHarnessSourceSection",
    "assertEntriesActivated",
    "assertEntriesLoaded",
    "boot",
    "composeEntries",
    "healProfilesModuleFallback",
    "initProfile",
    "installFailLoud",
    "loadEnv",
    "loadLayeredEnv",
    "loadOptionalPatches",
    "loadOverlayPatches",
    "loadProfile",
    "mountRootInclude",
    "readProfileManifest",
    "renderConfigDump",
    "resolveBundleDir",
    "resolveConfigPath",
    "resolveProfileDir",
    "watchUserPatches",
    "writeProfileManifest",
]

DshBundleManifest: TypeAlias = object  # port: surface stub

DshManifestSection: TypeAlias = object  # port: surface stub

DshProfileManifest: TypeAlias = object  # port: surface stub

Profile: TypeAlias = object  # port: surface stub

ProfileLayer: TypeAlias = object  # port: surface stub

ProfileManifest: TypeAlias = object  # port: surface stub

FAIL_LOUD_RELEASE_TIMEOUT_MS = None  # port: surface stub

HARNESS_SOURCE_SECTION = None  # port: surface stub

def addHarnessSourceSection(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``addHarnessSourceSection``."""
    raise NotImplementedError("port addHarnessSourceSection from boot/app-boot/src/index.ts")

def assertEntriesActivated(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertEntriesActivated``."""
    raise NotImplementedError("port assertEntriesActivated from boot/app-boot/src/index.ts")

def assertEntriesLoaded(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertEntriesLoaded``."""
    raise NotImplementedError("port assertEntriesLoaded from boot/app-boot/src/index.ts")

def boot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``boot``."""
    raise NotImplementedError("port boot from boot/app-boot/src/index.ts")

def installFailLoud(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``installFailLoud``."""
    raise NotImplementedError("port installFailLoud from boot/app-boot/src/index.ts")

def loadEnv(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadEnv``."""
    raise NotImplementedError("port loadEnv from boot/app-boot/src/index.ts")

def loadLayeredEnv(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadLayeredEnv``."""
    raise NotImplementedError("port loadLayeredEnv from boot/app-boot/src/index.ts")

def loadOptionalPatches(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadOptionalPatches``."""
    raise NotImplementedError("port loadOptionalPatches from boot/app-boot/src/index.ts")

def loadOverlayPatches(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``loadOverlayPatches``."""
    raise NotImplementedError("port loadOverlayPatches from boot/app-boot/src/index.ts")

def mountRootInclude(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``mountRootInclude``."""
    raise NotImplementedError("port mountRootInclude from boot/app-boot/src/index.ts")

def renderConfigDump(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderConfigDump``."""
    raise NotImplementedError("port renderConfigDump from boot/app-boot/src/index.ts")

def resolveConfigPath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveConfigPath``."""
    raise NotImplementedError("port resolveConfigPath from boot/app-boot/src/index.ts")

def watchUserPatches(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``watchUserPatches``."""
    raise NotImplementedError("port watchUserPatches from boot/app-boot/src/index.ts")

DEFAULT_PROFILE_BUNDLES = None  # port: surface stub (reexport)

PROFILES_DIR = None  # port: surface stub (reexport)

PROFILE_PATCH_FILENAME = None  # port: surface stub (reexport)

PROFILE_TEMPLATES = None  # port: surface stub (reexport)

composeEntries = None  # port: surface stub (reexport)

healProfilesModuleFallback = None  # port: surface stub (reexport)

initProfile = None  # port: surface stub (reexport)

loadProfile = None  # port: surface stub (reexport)

readProfileManifest = None  # port: surface stub (reexport)

resolveBundleDir = None  # port: surface stub (reexport)

resolveProfileDir = None  # port: surface stub (reexport)

writeProfileManifest = None  # port: surface stub (reexport)

class ConfigDumpLayer(Protocol):
    """Surface stub for upstream interface ``ConfigDumpLayer``."""
    pass

class FailLoudProcess(Protocol):
    """Surface stub for upstream interface ``FailLoudProcess``."""
    pass

class UserPatchWatchOptions(Protocol):
    """Surface stub for upstream interface ``UserPatchWatchOptions``."""
    pass
