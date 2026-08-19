"""Auto-generated surface skeleton for upstream ``test-support/loader-smoke/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/loader-smoke/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EXAMPLE_MODE_ENV",
    "LOADER_SMOKE_TEST_TIMEOUT_MS",
    "ExampleLaunch",
    "ExampleLaunchOptions",
    "ExampleMode",
    "FixtureTurnOptions",
    "FixtureTurnResult",
    "LoaderSmokeOptions",
    "LoaderSmokeResult",
    "resolveExampleLaunch",
    "resolveExampleMode",
    "runFixtureTurn",
    "runLoaderSmoke",
]

ExampleMode: TypeAlias = object  # port: surface stub

FixtureTurnOptions: TypeAlias = object  # port: surface stub

FixtureTurnResult: TypeAlias = object  # port: surface stub

EXAMPLE_MODE_ENV = None  # port: surface stub

LOADER_SMOKE_TEST_TIMEOUT_MS = None  # port: surface stub

def resolveExampleLaunch(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveExampleLaunch``."""
    raise NotImplementedError("port resolveExampleLaunch from test-support/loader-smoke/src/index.ts")

def resolveExampleMode(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveExampleMode``."""
    raise NotImplementedError("port resolveExampleMode from test-support/loader-smoke/src/index.ts")

def runLoaderSmoke(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runLoaderSmoke``."""
    raise NotImplementedError("port runLoaderSmoke from test-support/loader-smoke/src/index.ts")

runFixtureTurn = None  # port: surface stub (reexport)

class ExampleLaunch(Protocol):
    """Surface stub for upstream interface ``ExampleLaunch``."""
    pass

class ExampleLaunchOptions(Protocol):
    """Surface stub for upstream interface ``ExampleLaunchOptions``."""
    pass

class LoaderSmokeOptions(Protocol):
    """Surface stub for upstream interface ``LoaderSmokeOptions``."""
    pass

class LoaderSmokeResult(Protocol):
    """Surface stub for upstream interface ``LoaderSmokeResult``."""
    pass
