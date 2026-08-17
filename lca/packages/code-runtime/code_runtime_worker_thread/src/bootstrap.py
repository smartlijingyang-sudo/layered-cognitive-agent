"""Auto-generated surface skeleton for upstream ``code-runtime/code-runtime-worker-thread/src/bootstrap.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``code-runtime/code-runtime-worker-thread/src/bootstrap.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "BindingErrorConstructor",
    "BootstrapPort",
    "LogBuffer",
    "PatchableStream",
    "PendingCall",
    "captureStreamWrites",
    "makeBindingErrorClasses",
    "makeConsoleShim",
    "makeNamespaces",
    "prepareCompletion",
    "prepareException",
    "runWorkerMain",
    "wireReplies",
]

BindingErrorConstructor: TypeAlias = object  # port: surface stub

def captureStreamWrites(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``captureStreamWrites``."""
    raise NotImplementedError("port captureStreamWrites from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def makeBindingErrorClasses(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``makeBindingErrorClasses``."""
    raise NotImplementedError("port makeBindingErrorClasses from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def makeConsoleShim(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``makeConsoleShim``."""
    raise NotImplementedError("port makeConsoleShim from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def makeNamespaces(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``makeNamespaces``."""
    raise NotImplementedError("port makeNamespaces from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def prepareCompletion(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``prepareCompletion``."""
    raise NotImplementedError("port prepareCompletion from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def prepareException(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``prepareException``."""
    raise NotImplementedError("port prepareException from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def runWorkerMain(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``runWorkerMain``."""
    raise NotImplementedError("port runWorkerMain from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

def wireReplies(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``wireReplies``."""
    raise NotImplementedError("port wireReplies from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

class LogBuffer:
    """Surface stub for upstream class ``LogBuffer``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port LogBuffer.__init__ from code-runtime/code-runtime-worker-thread/src/bootstrap.ts")

class BootstrapPort(Protocol):
    """Surface stub for upstream interface ``BootstrapPort``."""
    pass

class PatchableStream(Protocol):
    """Surface stub for upstream interface ``PatchableStream``."""
    pass

class PendingCall(Protocol):
    """Surface stub for upstream interface ``PendingCall``."""
    pass
