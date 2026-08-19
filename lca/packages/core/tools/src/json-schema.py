"""Auto-generated surface skeleton for upstream ``core/tools/src/json-schema.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/tools/src/json-schema.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "JsonSchemaError",
    "JsonSchemaNode",
    "JsonSchemaScalar",
    "JsonSchemaType",
    "ObjectJsonSchema",
    "assertObjectJsonSchema",
    "assertSupportedJsonSchema",
    "isJsonSchemaRecord",
    "isPlainJsonArray",
    "isPlainJsonRecord",
    "validateJsonSchemaValue",
]

JsonSchemaScalar: TypeAlias = object  # port: surface stub

JsonSchemaType: TypeAlias = object  # port: surface stub

ObjectJsonSchema: TypeAlias = object  # port: surface stub

def assertObjectJsonSchema(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertObjectJsonSchema``."""
    raise NotImplementedError("port assertObjectJsonSchema from core/tools/src/json-schema.ts")

def assertSupportedJsonSchema(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``assertSupportedJsonSchema``."""
    raise NotImplementedError("port assertSupportedJsonSchema from core/tools/src/json-schema.ts")

def isJsonSchemaRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isJsonSchemaRecord``."""
    raise NotImplementedError("port isJsonSchemaRecord from core/tools/src/json-schema.ts")

def isPlainJsonArray(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isPlainJsonArray``."""
    raise NotImplementedError("port isPlainJsonArray from core/tools/src/json-schema.ts")

def isPlainJsonRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``isPlainJsonRecord``."""
    raise NotImplementedError("port isPlainJsonRecord from core/tools/src/json-schema.ts")

def validateJsonSchemaValue(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``validateJsonSchemaValue``."""
    raise NotImplementedError("port validateJsonSchemaValue from core/tools/src/json-schema.ts")

class JsonSchemaError:
    """Surface stub for upstream class ``JsonSchemaError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port JsonSchemaError.__init__ from core/tools/src/json-schema.ts")

class JsonSchemaNode(Protocol):
    """Surface stub for upstream interface ``JsonSchemaNode``."""
    pass
