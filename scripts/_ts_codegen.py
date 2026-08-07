"""Shared Python → TypeScript type mapping for contract generators."""

from __future__ import annotations

import dataclasses
import enum
import typing

_PY_TO_TS: dict[type, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


def ts_type(field_type: object, *, event_base: type | None = None) -> str:
    if isinstance(field_type, type) and field_type in _PY_TO_TS:
        return _PY_TO_TS[field_type]
    origin = typing.get_origin(field_type)
    if origin is tuple:
        return "readonly string[]"
    if (
        event_base is not None
        and isinstance(field_type, type)
        and issubclass(field_type, event_base)
    ):
        return "never"
    if isinstance(field_type, type) and issubclass(field_type, enum.Enum):
        members = list(field_type.__members__.values())
        return " | ".join(f'"{m.value}"' for m in members)
    return "unknown"


def dataclass_interface(name: str, cls: type, *, event_base: type | None = None) -> str:
    hints = typing.get_type_hints(cls)
    lines = [f"export interface {name} {{"]
    if event_base is None:
        for field_name, field_type in hints.items():
            lines.append(f"  readonly {field_name}: {ts_type(field_type, event_base=event_base)};")
    else:
        lines.append(f'  readonly type: "{name}";')
        for field in dataclasses.fields(cls):
            if field.name == "type":
                continue
            lines.append(
                f"  readonly {field.name}: {ts_type(hints.get(field.name, field.type), event_base=event_base)};"
            )
    lines.append("}")
    return "\n".join(lines)
