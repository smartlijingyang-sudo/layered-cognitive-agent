"""Wire tool call to access decision — one anti-corruption layer.

The model emits wire tool names (``local_readFile``) whose argument keys are
camelCase or snake_case depending on the manifest. The access policy speaks
operation names (``read_file``) and path lists. This module owns that single
translation, so neither the manifest nor the policy grows a second vocabulary
and neither has to know the other's spelling.

Pure. The plane is a parameter, not an ambient read, so the classification is
testable without binding a run scope. Callers that have a run in flight pass
``current_primary()``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lca.contracts.models.core.execution.local_exec import (
    AccessDecision,
    AccessVerdict,
)
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access.grant import default_access_scope
from lca.infrastructure.runtime_plane.access.policy import decide_access
from lca.infrastructure.runtime_plane.bindings.bindings import current_primary

MACHINE_TOOL_PREFIX = "local_"

#: wire apiName to ``(policy operation, argument keys carrying a path)``.
#: ``moveFiles`` and ``runCommand`` carry no plain path key and are read below.
_OPERATION_ARGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "listFiles": ("list_files", ("directoryPath", "directory_path")),
    "readFile": ("read_file", ("path",)),
    "writeFile": ("write_file", ("path",)),
    "editFile": ("edit_file", ("path",)),
    "searchFiles": ("search_files", ("directory",)),
    "grepContent": ("grep_content", ("directory",)),
    "globFiles": ("glob_files", ("directory", "directoryPath", "directory_path")),
    "moveFiles": ("move_files", ()),
    "runCommand": ("run_command", ()),
    "getCommandOutput": ("get_command_output", ()),
    "killCommand": ("kill_command", ()),
}

#: Reverse index so ``call_paths`` does not scan the table above.
_PATH_KEYS_BY_OPERATION: dict[str, tuple[str, ...]] = dict(_OPERATION_ARGS.values())


def machine_operation(tool_name: str) -> str | None:
    """The policy operation a wire tool name maps to, or None if it is not one.

    The prefix is required, not merely stripped. The sandbox face uses bare
    apiNames (``readFile``) and the machine face uses ``local_``-prefixed ones,
    so an unprefixed name must not resolve to a machine operation.
    """
    if not tool_name.startswith(MACHINE_TOOL_PREFIX):
        return None
    entry = _OPERATION_ARGS.get(tool_name.removeprefix(MACHINE_TOOL_PREFIX))
    return entry[0] if entry is not None else None


def _first_str(arguments: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _move_paths(arguments: Mapping[str, Any]) -> list[str]:
    operations = arguments.get("operations")
    if not isinstance(operations, (list, tuple)):
        return []
    paths: list[str] = []
    for item in operations:
        if not isinstance(item, Mapping):
            continue
        for key in ("source", "destination"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
    return paths


def call_paths(operation: str, arguments: Mapping[str, Any]) -> list[str]:
    """Every path one tool call touches, so the stricter verdict can win."""
    if operation == "move_files":
        return _move_paths(arguments)
    path = _first_str(arguments, _PATH_KEYS_BY_OPERATION.get(operation, ()))
    return [path] if path else []


def decide_tool_call(
    tool_name: str, arguments: Mapping[str, Any], *, plane: PlaneRef | None
) -> AccessDecision | None:
    """The access decision for one wire tool call, or None when it is not gated.

    ``None`` means the call is not a machine computer tool, so this layer has
    no opinion and the caller falls back to its own classification.
    """
    operation = machine_operation(tool_name)
    if operation is None or plane is None:
        return None
    return decide_access(
        operation,
        scope=default_access_scope(plane, operation),
        plane=plane,
        paths=call_paths(operation, arguments),
        command=_first_str(arguments, ("command",)),
    )


def tool_calls_need_approval(tool_calls: object, plane: PlaneRef | None) -> bool:
    """True when any call must pause for consent before it may be dispatched.

    Composes with ``requires_human_input`` at the call site: that predicate owns
    the HITL tool names, this one owns machine-plane access. Neither replaces
    the other, and ADR-0246 §1.1 keeps authorization and consent separate.
    """
    if plane is None or plane.kind is not PlaneKind.MACHINE:
        return False
    if not isinstance(tool_calls, (list, tuple)):
        return False
    for call in tool_calls:
        tool_name = getattr(call, "tool_name", None)
        arguments = getattr(call, "arguments", None)
        if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
            continue
        decision = decide_tool_call(tool_name, arguments, plane=plane)
        if decision is not None and decision.verdict is not AccessVerdict.ALLOW:
            return True
    return False


def machine_calls_need_approval(tool_calls: object) -> bool:
    """Ambient entry point for Decision producers.

    Owns the one ambient plane read so ``think.decision.parse`` and the
    classifier provider classify identically without each reaching for the
    binding scope. The pure predicate below stays the testable core.
    """
    return tool_calls_need_approval(tool_calls, current_primary())


__all__ = [
    "MACHINE_TOOL_PREFIX",
    "call_paths",
    "decide_tool_call",
    "machine_calls_need_approval",
    "machine_operation",
    "tool_calls_need_approval",
]
