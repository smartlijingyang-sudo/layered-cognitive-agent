"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``hooks/hook-protocol/src/index.ts``
"""


from __future__ import annotations

from typing import TypeAlias

__all__: list[str] = [
    "DEFAULT_HOOK_TIMEOUT_MS",
    "DEFAULT_STDERR_SUMMARY_MAX_CHARS",
    "CommandHook",
    "DetachedRuns",
    "HookDialect",
    "HookInvocation",
    "HookOutput",
    "HookResultRecord",
    "MatcherGroup",
    "MatcherMode",
    "MergedDecision",
    "MergedHookOutcome",
    "RunHookOptions",
    "RunHookResult",
    "appendHookInvoked",
    "appendHookResult",
    "createDetachedRuns",
    "matcherDiagnostic",
    "matchesMatcher",
    "mergeHookOutputs",
    "parseHookOutput",
    "runHook",
    "summarizeStderr",
]

CommandHook: TypeAlias = object  # port: surface stub

DetachedRuns: TypeAlias = object  # port: surface stub

HookDialect: TypeAlias = object  # port: surface stub

HookInvocation: TypeAlias = object  # port: surface stub

HookOutput: TypeAlias = object  # port: surface stub

HookResultRecord: TypeAlias = object  # port: surface stub

MatcherGroup: TypeAlias = object  # port: surface stub

MatcherMode: TypeAlias = object  # port: surface stub

MergedDecision: TypeAlias = object  # port: surface stub

MergedHookOutcome: TypeAlias = object  # port: surface stub

RunHookOptions: TypeAlias = object  # port: surface stub

RunHookResult: TypeAlias = object  # port: surface stub

DEFAULT_HOOK_TIMEOUT_MS = None  # port: surface stub (reexport)

DEFAULT_STDERR_SUMMARY_MAX_CHARS = None  # port: surface stub (reexport)

appendHookInvoked = None  # port: surface stub (reexport)

appendHookResult = None  # port: surface stub (reexport)

createDetachedRuns = None  # port: surface stub (reexport)

matcherDiagnostic = None  # port: surface stub (reexport)

matchesMatcher = None  # port: surface stub (reexport)

mergeHookOutputs = None  # port: surface stub (reexport)

parseHookOutput = None  # port: surface stub (reexport)

runHook = None  # port: surface stub (reexport)

summarizeStderr = None  # port: surface stub (reexport)
