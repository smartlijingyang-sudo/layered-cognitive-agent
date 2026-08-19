"""Auto-generated surface skeleton for upstream ``core/tools/src/schema.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/tools/src/schema.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "ArrayValueSchemaSpec",
    "BooleanValueSchemaSpec",
    "DefineToolOptions",
    "InferArgs",
    "InferValue",
    "IntegerValueSchemaSpec",
    "JsonValueSchemaSpec",
    "NullValueSchemaSpec",
    "NumberValueSchemaSpec",
    "ObjectValueSchemaSpec",
    "OneOfValueSchemaSpec",
    "ParameterJsonSchema",
    "ParameterPropertySpec",
    "ParameterSchemaSpec",
    "StringValueSchemaSpec",
    "ToolArgsError",
    "ValueSchemaAnnotations",
    "ValueSchemaSpec",
    "defineTool",
    "parameterSchemaSpecToJsonSchema",
    "validateArgs",
    "valueSchemaSpecToJsonSchema",
]

InferArgs: TypeAlias = object  # port: surface stub

InferValue: TypeAlias = object  # port: surface stub

ParameterPropertySpec: TypeAlias = object  # port: surface stub

ParameterSchemaSpec: TypeAlias = object  # port: surface stub

ValueSchemaSpec: TypeAlias = object  # port: surface stub

def defineTool(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``defineTool``."""
    raise NotImplementedError("port defineTool from core/tools/src/schema.ts")

def parameterSchemaSpecToJsonSchema(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``parameterSchemaSpecToJsonSchema``."""
    raise NotImplementedError("port parameterSchemaSpecToJsonSchema from core/tools/src/schema.ts")

def validateArgs(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``validateArgs``."""
    raise NotImplementedError("port validateArgs from core/tools/src/schema.ts")

def valueSchemaSpecToJsonSchema(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``valueSchemaSpecToJsonSchema``."""
    raise NotImplementedError("port valueSchemaSpecToJsonSchema from core/tools/src/schema.ts")

class ToolArgsError:
    """Surface stub for upstream class ``ToolArgsError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ToolArgsError.__init__ from core/tools/src/schema.ts")

class ArrayValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``ArrayValueSchemaSpec``."""
    pass

class BooleanValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``BooleanValueSchemaSpec``."""
    pass

class DefineToolOptions(Protocol):
    """Surface stub for upstream interface ``DefineToolOptions``."""
    pass

class IntegerValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``IntegerValueSchemaSpec``."""
    pass

class JsonValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``JsonValueSchemaSpec``."""
    pass

class NullValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``NullValueSchemaSpec``."""
    pass

class NumberValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``NumberValueSchemaSpec``."""
    pass

class ObjectValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``ObjectValueSchemaSpec``."""
    pass

class OneOfValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``OneOfValueSchemaSpec``."""
    pass

class ParameterJsonSchema(Protocol):
    """Surface stub for upstream interface ``ParameterJsonSchema``."""
    pass

class StringValueSchemaSpec(Protocol):
    """Surface stub for upstream interface ``StringValueSchemaSpec``."""
    pass

class ValueSchemaAnnotations(Protocol):
    """Surface stub for upstream interface ``ValueSchemaAnnotations``."""
    pass
