"""1:1 port of ``@deepseek-ai/dsh-tools/schema.ts``.

Unified JSON-value schema DSL, inference, compilation, and typed tool helper.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from lca.layer0_infra.dsh_core.tools.json_schema import (
    JsonSchemaError,
    JsonSchemaNodeDict,
    assert_supported_json_schema,
    validate_json_schema_value,
)
from lca.layer0_infra.dsh_core.tools.types import ContentBlock

JsonValue = Any  # lossless-JSON value

# ---------------------------------------------------------------------------
# Annotation interfaces
# ---------------------------------------------------------------------------

@dataclass
class ValueSchemaAnnotations:
    """Annotation keywords shared by every author-facing schema node."""

    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None


# ---------------------------------------------------------------------------
# Value schema spec types
# ---------------------------------------------------------------------------

@dataclass
class StringValueSchemaSpec:
    type: Literal["string"] = "string"
    enum: list[str] | None = None
    const: str | None = None
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class NumberValueSchemaSpec:
    type: Literal["number"] = "number"
    enum: list[float] | None = None
    const: float | None = None
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class IntegerValueSchemaSpec:
    type: Literal["integer"] = "integer"
    enum: list[int] | None = None
    const: int | None = None
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class BooleanValueSchemaSpec:
    type: Literal["boolean"] = "boolean"
    enum: list[bool] | None = None
    const: bool | None = None
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class NullValueSchemaSpec:
    type: Literal["null"] = "null"
    enum: list[None] | None = None
    const: None = None
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class ArrayValueSchemaSpec:
    type: Literal["array"] = "array"
    items: Any = None  # ValueSchemaSpec
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class ObjectValueSchemaSpec:
    type: Literal["object"] = "object"
    properties: dict[str, Any] | None = None  # ParameterSchemaSpec
    additional_properties: bool = True
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class JsonValueSchemaSpec:
    type: Literal["json"] = "json"
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None
    required: bool | None = None


@dataclass
class OneOfValueSchemaSpec:
    one_of: list[Any] = field(default_factory=list)  # list[ValueSchemaSpec]
    description: str | None = None
    title: str | None = None
    default: Any = None
    examples: Any = None


ValueSchemaSpec = Union[
    StringValueSchemaSpec,
    NumberValueSchemaSpec,
    IntegerValueSchemaSpec,
    BooleanValueSchemaSpec,
    NullValueSchemaSpec,
    ArrayValueSchemaSpec,
    ObjectValueSchemaSpec,
    JsonValueSchemaSpec,
    OneOfValueSchemaSpec,
]

# Parameter specs
ParameterPropertySpec = ValueSchemaSpec
ParameterSchemaSpec = dict[str, ParameterPropertySpec]
ParameterJsonSchema = JsonSchemaNodeDict

# Type aliases (Python cannot do full TS inference; we approximate with Any)
InferValue = Any
InferArgs = dict[str, Any]


# ---------------------------------------------------------------------------
# Compilation helpers
# ---------------------------------------------------------------------------

_ANNOTATION_KEYS = ("description", "title", "default", "examples")


def _author_error(message: str) -> None:
    raise JsonSchemaError([message])


def _copy_annotations(source: dict[str, Any], target: dict[str, Any]) -> None:
    for key in _ANNOTATION_KEYS:
        if key in source:
            target[key] = source[key]


def _assert_author_keys(
    source: dict[str, Any], path: str, allowed: list[str],
) -> None:
    for key in source:
        if key not in allowed:
            _author_error(f"{path}.{key} is not supported by the value schema DSL")


@dataclass
class _CompiledPropertyMap:
    properties: dict[str, JsonSchemaNodeDict]
    required: list[str] | None = None


_CompileRoot: dict[str, Any] = {}


def _assign_compiled_node(
    destination: dict[str, Any], node: JsonSchemaNodeDict,
) -> None:
    kind = destination["kind"]
    if kind == "root":
        destination["holder"]["value"] = node
    elif kind == "property":
        destination["target"][destination["key"]] = node
    elif kind == "item":
        destination["target"]["items"] = node
    elif kind == "one-of":
        destination["target"][destination["index"]] = node


def _assign_compiled_property_map(
    destination: dict[str, Any], compiled: _CompiledPropertyMap,
) -> None:
    if destination["kind"] == "root":
        destination["holder"]["value"] = compiled
    else:
        destination["target"]["properties"] = compiled.properties


def _run_schema_compiler(initial: dict[str, Any]) -> None:
    """Execute an author-schema compilation task graph without recursion."""
    seen: set[int] = set()
    tasks: list[dict[str, Any]] = [initial]

    while tasks:
        task = tasks.pop()
        kind = task["kind"]

        if kind == "leave":
            seen.discard(id(task["input"]))
            continue

        if kind == "property-map-tail":
            compiled: _CompiledPropertyMap = task["compiled"]
            required: list[str] = task["required"]
            if required:
                compiled.required = required
                if task["destination"]["kind"] == "object":
                    task["destination"]["target"]["required"] = required
            continue

        if kind == "property":
            prop = task["property"]
            if not isinstance(prop, dict):
                _author_error(f"{task['path']} must be a value schema object")
            if "required" in prop and prop["required"] is not True:
                _author_error(f"{task['path']}.required must be true when present")
            if "required" in prop and prop["required"] is True:
                task["required"].append(task["key"])
            tasks.append({
                "kind": "value",
                "input": prop,
                "path": task["path"],
                "allow_required": True,
                "destination": {
                    "kind": "property",
                    "target": task["properties"],
                    "key": task["key"],
                },
            })
            continue

        if kind == "property-map":
            inp = task["input"]
            if not isinstance(inp, dict):
                _author_error(f"{task['path']} must be an object of value schemas")
            if id(inp) in seen:
                _author_error(f"{task['path']} is circular")
            seen.add(id(inp))
            compiled_map = _CompiledPropertyMap(properties={})
            required_list: list[str] = []
            _assign_compiled_property_map(task["destination"], compiled_map)
            tasks.append({"kind": "leave", "input": inp})
            tasks.append({
                "kind": "property-map-tail",
                "compiled": compiled_map,
                "required": required_list,
                "destination": task["destination"],
            })
            entries = list(inp.items())
            for k, v in reversed(entries):
                tasks.append({
                    "kind": "property",
                    "property": v,
                    "path": f"{task['path']}.{k}",
                    "key": k,
                    "properties": compiled_map.properties,
                    "required": required_list,
                })
            continue

        # kind == "value"
        inp = task["input"]
        path = task["path"]
        if not isinstance(inp, dict):
            _author_error(f"{path} must be a value schema object")
        if id(inp) in seen:
            _author_error(f"{path} is circular")
        seen.add(id(inp))
        allow_required = task.get("allow_required", False)
        author_keys = list(_ANNOTATION_KEYS)
        if allow_required:
            author_keys.append("required")
        node: JsonSchemaNodeDict = {}
        _assign_compiled_node(task["destination"], node)
        tasks.append({"kind": "leave", "input": inp})

        if "oneOf" in inp:
            allowed = [*author_keys, "oneOf", "type"]
            _assert_author_keys(inp, path, allowed)
            if "type" in inp:
                _author_error(f"{path} cannot declare both type and oneOf")
            one_of = inp["oneOf"]
            if not isinstance(one_of, list) or len(one_of) < 2:
                _author_error(
                    f"{path}.oneOf must be an array of at least two value schemas"
                )
            branches: list[JsonSchemaNodeDict] = []
            node["oneOf"] = branches
            _copy_annotations(inp, node)
            for index in range(len(one_of) - 1, -1, -1):
                tasks.append({
                    "kind": "value",
                    "input": one_of[index],
                    "path": f"{path}.oneOf[{index}]",
                    "allow_required": False,
                    "destination": {
                        "kind": "one-of",
                        "target": branches,
                        "index": index,
                    },
                })
            continue

        input_type = inp.get("type")
        if input_type == "json":
            allowed = [*author_keys, "type"]
            _assert_author_keys(inp, path, allowed)
            _copy_annotations(inp, node)

        elif input_type == "object":
            allowed = [*author_keys, "type", "properties", "additionalProperties"]
            _assert_author_keys(inp, path, allowed)
            if "additionalProperties" not in inp or not isinstance(
                inp["additionalProperties"], bool
            ):
                _author_error(
                    f"{path}.additionalProperties must be explicitly true or false"
                )
            node["type"] = "object"
            _copy_annotations(inp, node)
            node["additionalProperties"] = inp["additionalProperties"]
            if "properties" in inp:
                tasks.append({
                    "kind": "property-map",
                    "input": inp["properties"],
                    "path": f"{path}.properties",
                    "destination": {"kind": "object", "target": node},
                })

        elif input_type == "array":
            allowed = [*author_keys, "type", "items"]
            _assert_author_keys(inp, path, allowed)
            node["type"] = "array"
            _copy_annotations(inp, node)
            if "items" in inp:
                tasks.append({
                    "kind": "value",
                    "input": inp["items"],
                    "path": f"{path}.items",
                    "allow_required": False,
                    "destination": {"kind": "item", "target": node},
                })

        elif input_type in ("string", "number", "integer", "boolean", "null"):
            allowed = [*author_keys, "type", "enum", "const"]
            _assert_author_keys(inp, path, allowed)
            node["type"] = input_type
            _copy_annotations(inp, node)
            if "enum" in inp:
                enum_val = inp["enum"]
                if not isinstance(enum_val, list) or len(enum_val) == 0:
                    _author_error(
                        f"{path}.enum must be a non-empty array of scalar values"
                    )
                node["enum"] = list(enum_val)
            if "const" in inp:
                node["const"] = inp["const"]

        else:
            _author_error(
                f"{path}.type must be string/number/integer/boolean/null/array/object/json, "
                "or use oneOf"
            )


def _compile_property_map(
    input_: Any, path: str,
) -> _CompiledPropertyMap:
    holder: dict[str, Any] = {}
    _run_schema_compiler({
        "kind": "property-map",
        "input": input_,
        "path": path,
        "destination": {"kind": "root", "holder": holder},
    })
    result = holder.get("value")
    if result is None:
        _author_error(f"{path} did not compile")
    return result


def _compile_value_schema(input_: Any, path: str) -> JsonSchemaNodeDict:
    holder: dict[str, Any] = {}
    _run_schema_compiler({
        "kind": "value",
        "input": input_,
        "path": path,
        "allow_required": False,
        "destination": {"kind": "root", "holder": holder},
    })
    result = holder.get("value")
    if result is None:
        _author_error(f"{path} did not compile")
    return result


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Convert a dataclass spec to a dict for compilation."""
    if isinstance(spec, dict):
        return spec
    if hasattr(spec, "__dataclass_fields__"):
        result: dict[str, Any] = {}
        for fld_name in spec.__dataclass_fields__:
            val = getattr(spec, fld_name)
            if val is not None:
                # Convert camelCase → snake_case for some fields
                if fld_name == "additional_properties":
                    result["additionalProperties"] = val
                elif fld_name == "one_of":
                    result["oneOf"] = [_spec_to_dict(v) for v in val]
                elif fld_name == "properties" and isinstance(val, dict):
                    result["properties"] = {
                        k: _spec_to_dict(v) for k, v in val.items()
                    }
                elif fld_name == "items" and val is not None:
                    result["items"] = _spec_to_dict(val)
                else:
                    result[fld_name] = val
        return result
    return dict(spec)


# ---------------------------------------------------------------------------
# Public compilation entry points
# ---------------------------------------------------------------------------

def value_schema_spec_to_json_schema(spec: Any) -> JsonSchemaNodeDict:
    """Compile one author-facing value schema to the enforced raw JSON Schema subset."""
    spec_dict = _spec_to_dict(spec)
    schema = _compile_value_schema(spec_dict, "schema")
    assert_supported_json_schema(schema)
    return schema


def parameter_schema_spec_to_json_schema(spec: ParameterSchemaSpec) -> ParameterJsonSchema:
    """Compile the implicit open parameter object into raw JSON Schema."""
    spec_dict = {k: _spec_to_dict(v) for k, v in spec.items()}
    compiled = _compile_property_map(spec_dict, "parameters")
    schema: ParameterJsonSchema = {
        "type": "object",
        "properties": compiled.properties,
    }
    if compiled.required:
        schema["required"] = compiled.required
    assert_supported_json_schema(schema)
    return schema


# ---------------------------------------------------------------------------
# ToolArgsError
# ---------------------------------------------------------------------------

@dataclass
class ToolArgsError(Exception):
    """Invalid model-generated arguments for a typed tool."""

    violations: list[str] = field(default_factory=list)
    code: str = "INVALID_ARGS"

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        msg = f"invalid arguments: {'; '.join(violations)}"
        super().__init__(msg)
        self.code = "INVALID_ARGS"


def validate_args(spec: ParameterSchemaSpec, args: Any) -> list[str]:
    """Validate model-generated arguments against an implicit parameter schema."""
    return validate_json_schema_value(
        parameter_schema_spec_to_json_schema(spec), args, ""
    )


# ---------------------------------------------------------------------------
# ToolDefinition / ToolOutputDefinition
# ---------------------------------------------------------------------------

class ToolOutputDefinition:
    """Tool-owned canonical output contract."""

    def __init__(
        self,
        schema: JsonSchemaNodeDict,
        render: Callable[[Any, Any], list[ContentBlock]],
        presentation_meta: Callable[[Any, Any], Any] | None = None,
    ) -> None:
        self.schema = schema
        self.render = render
        self.presentation_meta = presentation_meta


class ToolDefinition:
    """A registered tool: its schema plus the execution function."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Any,
        output: ToolOutputDefinition,
        execute: Callable[..., Any],
        timeout_ms: int | None = None,
        finalize_content: Callable[..., list[ContentBlock] | None] | None = None,
        is_concurrency_safe: Callable[[Any], bool] | None = None,
        present_call: Callable[[Any], Any] | None = None,
        present_result: Callable[..., Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.output = output
        self.execute = execute
        self.timeout_ms = timeout_ms
        self.finalize_content = finalize_content
        self.is_concurrency_safe = is_concurrency_safe
        self.present_call = present_call
        self.present_result = present_result


# ---------------------------------------------------------------------------
# ToolRunContext / ToolExecution / ToolExecutionResult (forward refs)
# ---------------------------------------------------------------------------

# These are defined fully in index.py; here we need the type aliases
# for define_tool's signatures.  They are imported lazily to avoid
# circular imports.
ToolRunContext = Any
ToolExecution = Any
ToolExecutionResult = Any
ToolResult = Any


# ---------------------------------------------------------------------------
# define_tool
# ---------------------------------------------------------------------------

def define_tool(
    *,
    name: str,
    description: str,
    parameters: ParameterSchemaSpec,
    output: dict[str, Any],
    execute: Callable[..., Any],
    timeout_ms: int | None = None,
    finalize_content: Callable[..., list[ContentBlock] | None] | None = None,
    is_concurrency_safe: Callable[[Any], bool] | None = None,
    present_call: Callable[[Any], Any] | None = None,
    present_result: Callable[..., Any] | None = None,
) -> ToolDefinition:
    """Define a first-party tool with inferred arguments and strict execution validation.

    ``output`` must contain ``schema`` (a ValueSchemaSpec) and ``render``
    (a callable taking (args, value) -> list[ContentBlock]).
    """
    if timeout_ms is not None and (not isinstance(timeout_ms, (int, float)) or timeout_ms <= 0):
        raise ValueError(
            f"defineTool({name}): timeoutMs must be a positive finite number"
        )

    output_schema_spec = output["schema"]
    user_render = output["render"]
    user_presentation_meta = output.get("presentationMeta")

    parameters_json = parameter_schema_spec_to_json_schema(parameters)
    output_json = value_schema_spec_to_json_schema(output_schema_spec)

    def validate(args: Any) -> list[str]:
        return validate_json_schema_value(parameters_json, args, "")

    async def wrapped_execute(args: Any, exec_: Any) -> Any:
        violations = validate(args)
        if violations:
            raise ToolArgsError(violations)
        return await execute(args, exec_)

    tool = ToolDefinition(
        name=name,
        description=description,
        parameters=parameters_json,
        output=ToolOutputDefinition(
            schema=output_json,
            render=user_render,
            presentation_meta=user_presentation_meta,
        ),
        execute=wrapped_execute,
        timeout_ms=timeout_ms,
        finalize_content=finalize_content,
    )

    # Presentation is display-only and may run on REPLAY of arbitrary
    # logged args (possibly from an older schema), so it must never throw.
    if present_call is not None:
        def safe_present_call(args: Any) -> Any:
            if validate(args):
                return None
            return present_call(args)
        tool.present_call = safe_present_call

    if present_result is not None:
        def safe_present_result(args: Any, result: Any) -> Any:
            if validate(args):
                return None
            return present_result(args, result)
        tool.present_result = safe_present_result

    if is_concurrency_safe is not None:
        def safe_is_concurrency_safe(args: Any) -> bool:
            if validate(args):
                return False
            return is_concurrency_safe(args)
        tool.is_concurrency_safe = safe_is_concurrency_safe

    return tool
