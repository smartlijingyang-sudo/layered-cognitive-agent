"""1:1 port of ``@deepseek-ai/dsh-tools/json-schema.ts``.

Enforced JSON Schema subset shared by tool outputs, generated Code Mode
types, subagents, and workflows.  The subset accepts any JSON root, an
annotation-only schema for unconstrained JSON, one scalar ``type``,
object ``properties``/``required``/boolean ``additionalProperties``,
array ``items``, type-correct scalar ``enum``/``const``, and
exact-one ``oneOf``.

Unsupported or misplaced keywords reject rather than being accepted
without enforcement.  Consumers that require an object root apply
:func:`assert_object_json_schema` before accepting input.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# Shared JSON value utilities
# ---------------------------------------------------------------------------

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
"""Any lossless-JSON value."""

JsonSchemaScalar = str | int | float | bool | None
"""Scalar JSON values supported by ``enum`` and ``const``."""

JsonSchemaType = Literal[
    "object", "array", "string", "number", "integer", "boolean", "null"
]
"""Single-type keywords accepted by the enforced subset."""

_SCHEMA_TYPES: tuple[str, ...] = (
    "object", "array", "string", "number", "integer", "boolean", "null",
)


# ---------------------------------------------------------------------------
# JsonSchemaNode
# ---------------------------------------------------------------------------

class JsonSchemaNodeDict(TypedDict, total=False):
    """One raw JSON Schema node in the enforced subset.

    The optional fields express the external wire schema;
    :func:`assert_supported_json_schema` rejects invalid combinations
    before a caller treats the node as trusted.
    """

    type: str
    oneOf: list[JsonSchemaNodeDict]
    properties: dict[str, JsonSchemaNodeDict]
    required: list[str]
    additionalProperties: bool
    items: JsonSchemaNodeDict
    enum: list[Any]
    const: Any
    description: str
    title: str
    default: Any
    examples: Any


# Alias so the rest of the port can use a short name
JsonSchemaNode = JsonSchemaNodeDict

ObjectJsonSchema = JsonSchemaNodeDict
"""A consumer-constrained object-rooted schema."""


# ---------------------------------------------------------------------------
# JsonSchemaError
# ---------------------------------------------------------------------------

@dataclass
class JsonSchemaError(Exception):
    """Thrown when a raw schema falls outside the enforced subset.

    ``violations`` lists every offending path instead of stopping at
    the first author error.
    """

    violations: list[str] = field(default_factory=list)
    code: str = "UNSUPPORTED_SCHEMA"

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        msg = f"unsupported JSON schema: {'; '.join(violations)}"
        super().__init__(msg)
        self.code = "UNSUPPORTED_SCHEMA"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONSTRAINT_KEYWORDS: frozenset[str] = frozenset({
    "type", "oneOf", "properties", "required",
    "additionalProperties", "items", "enum", "const",
})

_ANNOTATION_KEYWORDS: frozenset[str] = frozenset({
    "description", "title", "default", "examples",
})

_ONE_OF_SIBLING_KEYWORDS: tuple[str, ...] = (
    "properties", "required", "additionalProperties",
    "items", "enum", "const",
)


# ---------------------------------------------------------------------------
# Lossless JSON boundary helpers
# ---------------------------------------------------------------------------

def is_json_value(value: Any) -> bool:
    """Whether *value* is a lossless JSON value (no ``NaN`` / ``Inf`` / ``-0``)."""
    return _is_json_value_inner(value, set())


def _is_json_value_inner(value: Any, seen: set[int]) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return False
            if math.copysign(1.0, value) < 0 and value == 0.0:
                return False
        return True
    if isinstance(value, str):
        return True
    if isinstance(value, (list, tuple)):
        vid = id(value)
        if vid in seen:
            return False
        seen.add(vid)
        return all(_is_json_value_inner(item, seen) for item in value)
    if isinstance(value, dict):
        vid = id(value)
        if vid in seen:
            return False
        seen.add(vid)
        return all(
            isinstance(k, str) and _is_json_value_inner(v, seen)
            for k, v in value.items()
        )
    return False


def snapshot_json_value(value: Any) -> Any:
    """Detach *value* through a lossless JSON round-trip.

    Returns the snapshot, or ``None`` if the value is not lossless JSON.
    """
    try:
        encoded = json.dumps(value, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError):
        return None


def is_plain_json_record(value: Any) -> bool:
    """Test for a plain JSON dict without accepting lists or exotic objects."""
    return isinstance(value, dict)


def is_plain_json_array(value: Any) -> bool:
    """Test for a dense ordinary list with no JSON-invisible decorations."""
    return isinstance(value, (list, tuple))


def is_json_schema_record(value: Any) -> bool:
    """Test for an ordinary schema dict whose keys survive JSON projection."""
    return isinstance(value, dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_json_number(value: Any) -> bool:
    """Lossless finite JSON number, excluding negative zero."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value) and not (value == 0.0 and math.copysign(1.0, value) < 0)
    return False


def _scalar_matches(scalar_type: str, value: Any) -> bool:
    """Whether a scalar is valid for one declared schema type."""
    if scalar_type == "string":
        return isinstance(value, str)
    if scalar_type == "number":
        return _is_json_number(value)
    if scalar_type == "integer":
        return (_is_json_number(value) and isinstance(value, int)) or (
            isinstance(value, float) and value == int(value) and math.isfinite(value)
        )
    if scalar_type == "boolean":
        return isinstance(value, bool)
    if scalar_type == "null":
        return value is None
    return False


# ---------------------------------------------------------------------------
# Iterative schema validation walk
# ---------------------------------------------------------------------------



_SchemaWalkTask = Any  # discriminated union via dicts


def _check_object_schema_tail(
    node: dict[str, Any],
    path: str,
    properties: Any,
    violations: list[str],
) -> None:
    has_required = "required" in node
    required = node.get("required")
    if has_required:
        if not isinstance(required, list) or not all(isinstance(e, str) for e in required):
            violations.append(f"{path}.required must be an array of strings")
        else:
            declared = properties if isinstance(properties, dict) else {}
            for key in required:
                if key not in declared:
                    violations.append(f'{path}.required names "{key}" which is not in properties')
    if "additionalProperties" in node and not isinstance(node["additionalProperties"], bool):
        violations.append(f"{path}.additionalProperties must be a boolean")


def _check_schema_node(
    root: Any,
    root_path: str,
    violations: list[str],
    seen: set[int],
) -> None:
    """Collect every violation for one raw schema tree without recursion."""
    tasks: list[dict[str, Any]] = [
        {"kind": "enter", "node": root, "path": root_path}
    ]
    while tasks:
        task = tasks.pop()
        kind = task["kind"]

        if kind == "leave":
            seen.discard(id(task["node"]))
            continue

        if kind == "one-of-tail":
            node: dict[str, Any] = task["node"]
            path: str = task["path"]
            for key in _ONE_OF_SIBLING_KEYWORDS:
                if key in node:
                    violations.append(f"{path}.{key} is not supported beside oneOf")
            continue

        if kind == "object-tail":
            _check_object_schema_tail(
                task["node"], task["path"], task["properties"], violations,
            )
            continue

        # kind == "enter"
        node = task["node"]
        path = task["path"]

        if not is_json_schema_record(node):
            violations.append(f"{path} must be a schema object")
            continue
        nid = id(node)
        if nid in seen:
            violations.append(f"{path} is circular")
            continue
        seen.add(nid)
        tasks.append({"kind": "leave", "node": node})

        for key in list(node.keys()):
            if key in _CONSTRAINT_KEYWORDS:
                continue
            if key in _ANNOTATION_KEYWORDS:
                try:
                    if not is_json_value(node[key]):
                        violations.append(
                            f"{path}.{key} annotation must be lossless JSON data"
                        )
                except Exception:
                    violations.append(
                        f"{path}.{key} annotation must be lossless JSON data"
                    )
                continue
            violations.append(
                f"{path}.{key} is not a supported keyword "
                "(subset: type/oneOf/properties/required/additionalProperties/items/enum/const + annotations)"
            )

        if "description" in node and not isinstance(node["description"], str):
            violations.append(f"{path}.description must be a string")
        if "title" in node and not isinstance(node["title"], str):
            violations.append(f"{path}.title must be a string")

        has_type = "type" in node
        has_one_of = "oneOf" in node
        if has_type and has_one_of:
            violations.append(f"{path} cannot declare both type and oneOf")
            continue
        if not has_type and not has_one_of:
            for key in _ONE_OF_SIBLING_KEYWORDS:
                if key in node:
                    violations.append(f"{path}.{key} requires type or oneOf")
            continue

        if has_one_of:
            one_of = node["oneOf"]
            tasks.append({"kind": "one-of-tail", "node": node, "path": path})
            if not isinstance(one_of, list) or len(one_of) < 2:
                violations.append(f"{path}.oneOf must be an array of at least two schemas")
            else:
                for index in range(len(one_of) - 1, -1, -1):
                    tasks.append({
                        "kind": "enter",
                        "node": one_of[index],
                        "path": f"{path}.oneOf[{index}]",
                    })
            continue

        typ = node["type"]
        if not isinstance(typ, str) or typ not in _SCHEMA_TYPES:
            if isinstance(typ, list):
                violations.append(
                    f"{path}.type must be a single type string "
                    "(type arrays are not supported)"
                )
            else:
                violations.append(
                    f"{path}.type must be one of {'/'.join(_SCHEMA_TYPES)}"
                )
            continue
        schema_type = typ

        allowed_for: dict[str, list[str]] = {
            "properties": ["object"],
            "required": ["object"],
            "additionalProperties": ["object"],
            "items": ["array"],
            "enum": ["string", "number", "integer", "boolean", "null"],
            "const": ["string", "number", "integer", "boolean", "null"],
        }
        for kw, types in allowed_for.items():
            if kw in node and schema_type not in types:
                violations.append(f'{path}.{kw} is not supported on type "{schema_type}"')

        if schema_type == "object":
            properties = node.get("properties")
            tasks.append({
                "kind": "object-tail", "node": node, "path": path,
                "properties": properties,
            })
            if "properties" in node:
                if not is_json_schema_record(properties):
                    violations.append(f"{path}.properties must be an object of schemas")
                else:
                    entries = list(properties.items())
                    for index in range(len(entries) - 1, -1, -1):
                        k, v = entries[index]
                        tasks.append({
                            "kind": "enter",
                            "node": v,
                            "path": f"{path}.properties.{k}",
                        })

        elif schema_type == "array":
            if "items" in node:
                tasks.append({
                    "kind": "enter",
                    "node": node["items"],
                    "path": f"{path}.items",
                })

        else:  # string / number / integer / boolean / null
            has_enum = "enum" in node
            allowed = node.get("enum") if has_enum else None
            enum_valid = (
                isinstance(allowed, list)
                and len(allowed) > 0
                and all(_scalar_matches(schema_type, entry) for entry in allowed)
            )
            if has_enum and not enum_valid:
                violations.append(
                    f"{path}.enum must be a non-empty array of {schema_type} values"
                )
            has_const = "const" in node
            declared_const = node.get("const") if has_const else None
            const_valid = _scalar_matches(schema_type, declared_const)
            if has_const:
                if not const_valid:
                    violations.append(f"{path}.const must be a {schema_type} value")
                elif enum_valid and allowed is not None and declared_const not in allowed:
                    violations.append(
                        f"{path}.const must be one of {path}.enum when both are declared"
                    )


# ---------------------------------------------------------------------------
# Public validation entry points
# ---------------------------------------------------------------------------

def assert_supported_json_schema(schema: Any) -> None:
    """Assert that an arbitrary raw schema uses only the enforced subset.

    Annotation-only schemas are accepted as the standard unconstrained-JSON
    form; callers that require an object root use
    :func:`assert_object_json_schema`.

    Raises :class:`JsonSchemaError` on violation.
    """
    violations: list[str] = []
    _check_schema_node(schema, "schema", violations, set())
    if violations:
        raise JsonSchemaError(violations)


def assert_object_json_schema(schema: Any) -> None:
    """Assert the enforced subset plus the object-root constraint.

    Raises :class:`JsonSchemaError` on violation.
    """
    violations: list[str] = []
    _check_schema_node(schema, "schema", violations, set())
    if (
        not violations
        and (
            not isinstance(schema, dict)
            or "type" not in schema
            or schema["type"] != "object"
        )
    ):
        violations.append(
            'schema.type must be "object" (structured output is object-rooted)'
        )
    if violations:
        raise JsonSchemaError(violations)


# ---------------------------------------------------------------------------
# Value validation (iterative)
# ---------------------------------------------------------------------------

def _diagnostic_path(path: str) -> str:
    return path if path != "" else "arguments"


def _property_path(path: str, key: str) -> str:
    return key if path == "" else f"{path}.{key}"


def _lossless_value_violation(path: str) -> list[str]:
    return [f'"{_diagnostic_path(path)}" must be a lossless JSON value']


def _check_scalar_value(
    node: dict[str, Any], value: Any, path: str,
) -> list[str]:
    allowed = node.get("enum")
    if allowed is not None and "enum" in node and value not in allowed:
        return [f'"{_diagnostic_path(path)}" must be one of {json.dumps(allowed)}']
    if "const" in node and value != node["const"]:
        return [f'"{_diagnostic_path(path)}" must be {json.dumps(node["const"])}']
    return []


_ValueFrame = Any  # discriminated via dicts with "phase" key


def _value_frame(
    node: dict[str, Any], value: Any, path: str,
) -> dict[str, Any]:
    return {
        "node": node,
        "value": value,
        "path": path,
        "catches": False,
        "phase": "start",
        "kind": None,
        "children": [],
        "child_index": 0,
        "violations": [],
        "tail_violations": [],
        "matches": 0,
    }


def _check_value(
    schema: dict[str, Any], value: Any, path: str = "value",
) -> list[str]:
    """Validate one trusted schema/value pair with explicit frames."""
    frames: list[dict[str, Any]] = [_value_frame(schema, value, path)]
    root_result: list[str] | None = None

    def receive(result: list[str]) -> None:
        nonlocal root_result
        if not frames:
            root_result = result
            return
        parent = frames[-1]
        if parent["kind"] == "oneOf":
            if len(result) == 0:
                parent["matches"] += 1
        else:
            parent["violations"].extend(result)

    def finish(result: list[str]) -> None:
        frames.pop()
        receive(result)

    while frames:
        frame = frames[-1]
        try:
            if frame["phase"] == "children":
                if frame["child_index"] < len(frame["children"]):
                    child = frame["children"][frame["child_index"]]
                    frame["child_index"] += 1
                    frames.append(
                        _value_frame(child["node"], child["value"], child["path"])
                    )
                    continue
                if frame["kind"] == "oneOf":
                    finish(
                        []
                        if frame["matches"] == 1
                        else [
                            f'"{_diagnostic_path(frame["path"])}" must match exactly '
                            f'one oneOf branch (matched {frame["matches"]})'
                        ]
                    )
                    continue
                frame["violations"].extend(frame["tail_violations"])
                if frame["violations"]:
                    finish(frame["violations"])
                elif frame["kind"] == "object":
                    finish(
                        [] if _safely_is_json_value(frame["value"])
                        else [f'"{_diagnostic_path(frame["path"])}" must be a lossless JSON object']
                    )
                else:
                    finish(
                        [] if _safely_is_json_value(frame["value"])
                        else [f'"{_diagnostic_path(frame["path"])}" must be a dense lossless JSON array']
                    )
                continue

            # phase == "start"
            node_type = frame["node"].get("type")
            frame["catches"] = not (
                node_type is not None and node_type not in _SCHEMA_TYPES
            )
            one_of = frame["node"].get("oneOf")
            if "oneOf" in frame["node"] and one_of is not None:
                frame["kind"] = "oneOf"
                frame["children"] = [
                    {"node": branch, "value": frame["value"], "path": frame["path"]}
                    for branch in one_of
                ]
                frame["child_index"] = 0
                frame["matches"] = 0
                frame["phase"] = "children"
                continue

            if node_type is None:
                finish(
                    [] if _safely_is_json_value(frame["value"])
                    else _lossless_value_violation(frame["path"])
                )
                continue

            if node_type == "object":
                if not isinstance(frame["value"], dict):
                    finish([f'"{_diagnostic_path(frame["path"])}" must be an object'])
                    continue
                properties: dict[str, Any] = (
                    frame["node"].get("properties") or {}
                    if "properties" in frame["node"]
                    else {}
                )
                fv: list[str] = []
                required: list[str] = (
                    frame["node"].get("required") or []
                    if "required" in frame["node"]
                    else []
                )
                for key in required:
                    if key not in frame["value"] or frame["value"][key] is None:
                        fv.append(
                            f'missing required property "{_property_path(frame["path"], key)}"'
                        )
                children: list[dict[str, Any]] = []
                for key, child_schema in properties.items():
                    if key not in frame["value"] or frame["value"][key] is None:
                        continue
                    children.append({
                        "node": child_schema,
                        "value": frame["value"][key],
                        "path": _property_path(frame["path"], key),
                    })
                tail_violations: list[str] = []
                if (
                    "additionalProperties" in frame["node"]
                    and frame["node"]["additionalProperties"] is False
                ):
                    for key in frame["value"]:
                        if key not in properties:
                            tail_violations.append(
                                f'"{_property_path(frame["path"], key)}" is not a '
                                f"declared property (additionalProperties: false)"
                            )
                frame["kind"] = "object"
                frame["children"] = children
                frame["child_index"] = 0
                frame["violations"] = fv
                frame["tail_violations"] = tail_violations
                frame["phase"] = "children"

            elif node_type == "array":
                if not isinstance(frame["value"], list):
                    finish([f'"{_diagnostic_path(frame["path"])}" must be an array'])
                    continue
                items = frame["node"].get("items") if "items" in frame["node"] else None
                if items is None:
                    children = []
                else:
                    children = [
                        {
                            "node": items,
                            "value": entry,
                            "path": f"{frame['path']}[{index}]",
                        }
                        for index, entry in enumerate(frame["value"])
                    ]
                frame["kind"] = "array"
                frame["children"] = children
                frame["child_index"] = 0
                frame["violations"] = []
                frame["phase"] = "children"

            elif node_type == "string":
                finish(
                    _check_scalar_value(frame["node"], frame["value"], frame["path"])
                    if isinstance(frame["value"], str)
                    else [f'"{_diagnostic_path(frame["path"])}" must be a string']
                )

            elif node_type == "number":
                if not isinstance(frame["value"], (int, float)) or isinstance(frame["value"], bool):
                    finish([f'"{_diagnostic_path(frame["path"])}" must be a number'])
                elif not _is_json_number(frame["value"]):
                    finish([f'"{_diagnostic_path(frame["path"])}" must be a finite JSON number'])
                else:
                    finish(_check_scalar_value(frame["node"], frame["value"], frame["path"]))

            elif node_type == "integer":
                if not _is_json_number(frame["value"]):
                    finish([f'"{_diagnostic_path(frame["path"])}" must be an integer'])
                elif isinstance(frame["value"], int) or (isinstance(frame["value"], float) and frame["value"] == int(frame["value"])):
                    finish(_check_scalar_value(frame["node"], frame["value"], frame["path"]))
                else:
                    finish([f'"{_diagnostic_path(frame["path"])}" must be an integer'])

            elif node_type == "boolean":
                finish(
                    _check_scalar_value(frame["node"], frame["value"], frame["path"])
                    if isinstance(frame["value"], bool)
                    else [f'"{_diagnostic_path(frame["path"])}" must be a boolean']
                )

            elif node_type == "null":
                finish(
                    _check_scalar_value(frame["node"], frame["value"], frame["path"])
                    if frame["value"] is None
                    else [f'"{_diagnostic_path(frame["path"])}" must be null']
                )

        except Exception:
            failed = frames.pop()
            while failed is not None and not failed.get("catches", False):
                failed = frames.pop() if frames else None
            if failed is None:
                raise
            receive(_lossless_value_violation(failed["path"]))

    return root_result if root_result is not None else _lossless_value_violation(path)


def _safely_is_json_value(value: Any) -> bool:
    """Safely test the lossless JSON boundary when a getter may throw."""
    try:
        return is_json_value(value)
    except Exception:
        return False


def validate_json_schema_value(
    schema: JsonSchemaNode,
    value: Any,
    path: str = "value",
) -> list[str]:
    """Validate a candidate value against an asserted raw schema.

    The function is total for arbitrary values and returns
    path-qualified violations.
    """
    return _check_value(schema, value, path)
