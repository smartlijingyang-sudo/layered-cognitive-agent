"""Auto-generated surface skeleton for upstream ``test-support/client-runtime/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``test-support/client-runtime/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "FeatureHandle",
    "FixtureSession",
    "SessionBehaviorOverrides",
    "SessionFixture",
    "SlotTestRuntime",
    "SlotView",
    "Stabilizer",
    "StubSettingsScope",
    "TestRemote",
    "TestRoot",
    "TestSessions",
    "TestWorkspaces",
    "conversationSnapshot",
    "domSnapshotSerializer",
    "makeTranslate",
    "registerDomSnapshotSerializer",
    "stubSettingsScope",
    "usePinnedBrowserLanguages",
    "workspaceListState",
]

SessionBehaviorOverrides: TypeAlias = object  # port: surface stub

SessionFixture: TypeAlias = object  # port: surface stub

Stabilizer: TypeAlias = object  # port: surface stub

StubSettingsScope: TypeAlias = object  # port: surface stub

class SlotTestRuntime:
    """Surface stub for upstream class ``SlotTestRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port SlotTestRuntime.__init__ from test-support/client-runtime/src/index.ts")

class TestRoot:
    """Surface stub for upstream class ``TestRoot``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port TestRoot.__init__ from test-support/client-runtime/src/index.ts")

FixtureSession = None  # port: surface stub (reexport)

TestRemote = None  # port: surface stub (reexport)

TestSessions = None  # port: surface stub (reexport)

TestWorkspaces = None  # port: surface stub (reexport)

conversationSnapshot = None  # port: surface stub (reexport)

domSnapshotSerializer = None  # port: surface stub (reexport)

makeTranslate = None  # port: surface stub (reexport)

registerDomSnapshotSerializer = None  # port: surface stub (reexport)

stubSettingsScope = None  # port: surface stub (reexport)

usePinnedBrowserLanguages = None  # port: surface stub (reexport)

workspaceListState = None  # port: surface stub (reexport)

class FeatureHandle(Protocol):
    """Surface stub for upstream interface ``FeatureHandle``."""
    pass

class SlotView(Protocol):
    """Surface stub for upstream interface ``SlotView``."""
    pass
