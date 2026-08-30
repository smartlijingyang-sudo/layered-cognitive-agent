"""Render contract definitions and registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Specification of a single field in a tool's contract."""

    python_key: str
    wire_key: str
    kind: Literal["string", "int", "bool", "json", "file_ref", "content_ref"]
    source: Literal["argument", "observation", "evidence_ref", "constant"]
    required: bool = True
    description: str = ""

    def rename(self, new_wire_key: str) -> FieldSpec:
        """Return a copy with wire_key replaced."""
        return FieldSpec(
            python_key=self.python_key,
            wire_key=new_wire_key,
            kind=self.kind,
            source=self.source,
            required=self.required,
            description=self.description,
        )

    def optional(self) -> FieldSpec:
        """Return a copy with required=False."""
        return FieldSpec(
            python_key=self.python_key,
            wire_key=self.wire_key,
            kind=self.kind,
            source=self.source,
            required=False,
            description=self.description,
        )


@dataclass(frozen=True, slots=True)
class RenderContract:
    """Contract describing how a tool's data maps to renderer expectations."""

    tool_name: str
    identifier: str
    api_name: str
    args: tuple[FieldSpec, ...] = ()
    state: tuple[FieldSpec, ...] = ()
    streaming: tuple[FieldSpec, ...] = ()
    content_field: str | None = None
    wait_for: tuple[str, ...] = ()


REGISTRY: dict[str, RenderContract] = {}


def contract(spec: RenderContract) -> Callable[[type], type]:
    """Decorator that registers a RenderContract in REGISTRY."""

    def decorator(cls: type) -> type:
        if spec.tool_name in REGISTRY:
            raise KeyError(f"Tool '{spec.tool_name}' already registered in contract registry")
        REGISTRY[spec.tool_name] = spec
        return cls

    return decorator


def get_contract(tool_name: str) -> RenderContract | None:
    """Retrieve a contract by tool_name, or None if not registered."""
    return REGISTRY.get(tool_name)
