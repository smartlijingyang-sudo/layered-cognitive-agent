"""Auto-generated surface skeleton for upstream ``sandbox/sandbox-windows-acl/src/ffi.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``sandbox/sandbox-windows-acl/src/ffi.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "PROCESS_INFORMATION",
    "STARTUPINFOW",
    "NativePtr",
    "ProcessInfoOutput",
    "StartupInfoInput",
    "Win32Bindings",
    "allocBytes",
    "allocOverlapped",
    "allocProcessInfo",
    "allocPtrSlot",
    "allocStartupInfo",
    "allocUint32",
    "decodeProcessInfo",
    "decodePtr",
    "decodePtrAt",
    "decodeUint8At",
    "decodeUint16At",
    "decodeUint32",
    "decodeUint32At",
    "encodeStartupInfo",
    "encodeUint32",
    "errorText",
    "getTempPath",
    "isInvalidHandle",
    "isNullPtr",
    "ptrAddress",
    "sameSidAt",
    "throwLastError",
    "throwWin32",
    "win32",
    "win32Sync",
]

NativePtr: TypeAlias = object  # port: surface stub

PROCESS_INFORMATION = None  # port: surface stub

STARTUPINFOW = None  # port: surface stub

def allocBytes(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocBytes``."""
    raise NotImplementedError("port allocBytes from sandbox/sandbox-windows-acl/src/ffi.ts")

def allocOverlapped(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocOverlapped``."""
    raise NotImplementedError("port allocOverlapped from sandbox/sandbox-windows-acl/src/ffi.ts")

def allocProcessInfo(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocProcessInfo``."""
    raise NotImplementedError("port allocProcessInfo from sandbox/sandbox-windows-acl/src/ffi.ts")

def allocPtrSlot(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocPtrSlot``."""
    raise NotImplementedError("port allocPtrSlot from sandbox/sandbox-windows-acl/src/ffi.ts")

def allocStartupInfo(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocStartupInfo``."""
    raise NotImplementedError("port allocStartupInfo from sandbox/sandbox-windows-acl/src/ffi.ts")

def allocUint32(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocUint32``."""
    raise NotImplementedError("port allocUint32 from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodeProcessInfo(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeProcessInfo``."""
    raise NotImplementedError("port decodeProcessInfo from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodePtr(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodePtr``."""
    raise NotImplementedError("port decodePtr from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodePtrAt(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodePtrAt``."""
    raise NotImplementedError("port decodePtrAt from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodeUint16At(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeUint16At``."""
    raise NotImplementedError("port decodeUint16At from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodeUint32(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeUint32``."""
    raise NotImplementedError("port decodeUint32 from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodeUint32At(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeUint32At``."""
    raise NotImplementedError("port decodeUint32At from sandbox/sandbox-windows-acl/src/ffi.ts")

def decodeUint8At(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeUint8At``."""
    raise NotImplementedError("port decodeUint8At from sandbox/sandbox-windows-acl/src/ffi.ts")

def encodeStartupInfo(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``encodeStartupInfo``."""
    raise NotImplementedError("port encodeStartupInfo from sandbox/sandbox-windows-acl/src/ffi.ts")

def encodeUint32(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``encodeUint32``."""
    raise NotImplementedError("port encodeUint32 from sandbox/sandbox-windows-acl/src/ffi.ts")

def errorText(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``errorText``."""
    raise NotImplementedError("port errorText from sandbox/sandbox-windows-acl/src/ffi.ts")

def getTempPath(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``getTempPath``."""
    raise NotImplementedError("port getTempPath from sandbox/sandbox-windows-acl/src/ffi.ts")

def isInvalidHandle(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isInvalidHandle``."""
    raise NotImplementedError("port isInvalidHandle from sandbox/sandbox-windows-acl/src/ffi.ts")

def isNullPtr(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isNullPtr``."""
    raise NotImplementedError("port isNullPtr from sandbox/sandbox-windows-acl/src/ffi.ts")

def ptrAddress(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``ptrAddress``."""
    raise NotImplementedError("port ptrAddress from sandbox/sandbox-windows-acl/src/ffi.ts")

def sameSidAt(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``sameSidAt``."""
    raise NotImplementedError("port sameSidAt from sandbox/sandbox-windows-acl/src/ffi.ts")

def throwLastError(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``throwLastError``."""
    raise NotImplementedError("port throwLastError from sandbox/sandbox-windows-acl/src/ffi.ts")

def throwWin32(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``throwWin32``."""
    raise NotImplementedError("port throwWin32 from sandbox/sandbox-windows-acl/src/ffi.ts")

def win32(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``win32``."""
    raise NotImplementedError("port win32 from sandbox/sandbox-windows-acl/src/ffi.ts")

def win32Sync(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``win32Sync``."""
    raise NotImplementedError("port win32Sync from sandbox/sandbox-windows-acl/src/ffi.ts")

class ProcessInfoOutput(Protocol):
    """Surface stub for upstream interface ``ProcessInfoOutput``."""
    pass

class StartupInfoInput(Protocol):
    """Surface stub for upstream interface ``StartupInfoInput``."""
    pass

class Win32Bindings(Protocol):
    """Surface stub for upstream interface ``Win32Bindings``."""
    pass
