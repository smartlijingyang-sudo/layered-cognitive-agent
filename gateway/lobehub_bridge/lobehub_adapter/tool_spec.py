"""Tool wire specification types and declarative builders.

Core abstractions for mapping LCA tool invocations to LobeHub's frontend protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from gateway.lobehub_bridge.lobehub_adapter.protocol import PLUGIN_SCHEMA_SEPARATOR

# ── Protocols (Strategy interfaces) ─────────────────────────


class ArgsTransform(Protocol):
    """Strategy: adapt LCA tool arguments → LobeHub wire arguments."""

    def __call__(self, args: dict[str, Any]) -> dict[str, Any]: ...


class StateBuilder(Protocol):
    """Strategy: build LobeHub pluginState from LCA tool result."""

    def __call__(
        self, args: dict[str, Any], payload: dict[str, Any], ok: bool, error: str
    ) -> dict[str, Any]: ...


# ── ToolWireSpec ────────────────────────────────────────────


@dataclass(frozen=True)
class ToolWireSpec:
    """Declarative mapping from an LCA tool to LobeHub's wire protocol.

    Attributes:
        lca_name: The LCA internal tool name (e.g. ``execute_code``).
        identifier: LobeHub plugin identifier (e.g. ``lobe-cloud-sandbox``).
        api_name: LobeHub API method name (e.g. ``executeCode``).
        transform_args: Strategy to adapt LCA args → LobeHub wire args.
        build_state: Strategy to build LobeHub pluginState from LCA result.
    """

    lca_name: str
    identifier: str
    api_name: str
    transform_args: ArgsTransform
    build_state: StateBuilder

    @property
    def wire_name(self) -> str:
        """OpenAI function.name wire form: ``identifier____apiName``."""
        return wire_tool_name(self.identifier, self.api_name)


# ── Wire name helpers ───────────────────────────────────────


def wire_tool_name(identifier: str, api_name: str) -> str:
    """Build the ``identifier____apiName`` wire format LobeHub expects."""
    return f"{identifier}{PLUGIN_SCHEMA_SEPARATOR}{api_name}"


def split_wire_name(wire_name: str) -> tuple[str, str]:
    """Split ``identifier____apiName`` back into LobeHub plugin coordinates."""
    if PLUGIN_SCHEMA_SEPARATOR in wire_name:
        identifier, api_name = wire_name.split(PLUGIN_SCHEMA_SEPARATOR, 1)
        return identifier, api_name
    return wire_name, ""


# ── FieldMapper: declarative arg transform builder ──────────


class FieldMapper:
    """Declarative argument transform — maps fields by type.

    Replaces repetitive ``first_str`` / ``copy_fields`` boilerplate with
    a single configuration object.

    Example::

        _transform_read_file = FieldMapper(
            strings=[("path", "path")],
            ints=[("startLine", "startLine"), ("endLine", "endLine")],
        )

    This is equivalent to a 15-line function that manually extracts each field.
    """

    def __init__(
        self,
        *,
        strings: Sequence[tuple[str, str]] = (),
        ints: Sequence[tuple[str, str]] = (),
        floats: Sequence[tuple[str, str]] = (),
        bools: Sequence[tuple[str, str]] = (),
        lists: Sequence[tuple[str, str]] = (),
    ) -> None:
        self._strings = list(strings)
        self._ints = list(ints)
        self._floats = list(floats)
        self._bools = list(bools)
        self._lists = list(lists)

    def __call__(self, args: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        # String fields: take first non-empty string
        for src, dst in self._strings:
            val = args.get(src)
            if isinstance(val, str) and val.strip():
                out[dst] = val.strip()
        # Integer fields
        for src, dst in self._ints:
            val = args.get(src)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[dst] = int(val)
        # Float fields
        for src, dst in self._floats:
            val = args.get(src)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[dst] = float(val)
        # Boolean fields
        for src, dst in self._bools:
            val = args.get(src)
            if isinstance(val, bool):
                out[dst] = val
        # List fields
        for src, dst in self._lists:
            val = args.get(src)
            if isinstance(val, list):
                out[dst] = val
        return out


# ── Spec factory ────────────────────────────────────────────


def make_spec(
    lca_name: str,
    identifier: str,
    api_name: str,
    transform_args: ArgsTransform,
    build_state: StateBuilder | None = None,
) -> ToolWireSpec:
    """Create a ToolWireSpec with a default state builder if none provided."""
    from gateway.lobehub_bridge.lobehub_adapter.build_state import merge_success_state

    return ToolWireSpec(
        lca_name=lca_name,
        identifier=identifier,
        api_name=api_name,
        transform_args=transform_args,
        build_state=build_state or merge_success_state,
    )
