"""1:1 port of ``@deepseek-ai/dsh-tools/py-types.ts``.

Code Mode codegen — Python flavor.  The pure projection from registered
tool schemas to the Python SDK text the model programs against under
``runtime.language == 'python'``.
"""

from __future__ import annotations

import contextlib
import json
import re
import unicodedata
from typing import Any

from lca.layer0_infra.dsh_core.tools.json_schema import (
    JsonSchemaNodeDict,
    JsonSchemaScalar,
    assert_supported_json_schema,
)
from lca.layer0_infra.dsh_core.tools.ts_types import ToolSdkSchema

# ---------------------------------------------------------------------------
# Identifier predicates
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^[\w][\w]*$", re.UNICODE)


def _is_xid_start(ch: str) -> bool:
    """Approximate XID_Start test."""
    cat = unicodedata.category(ch)
    return cat in ("Lu", "Ll", "Lt", "Lm", "Lo", "Nl")


def _is_xid_continue(ch: str) -> bool:
    """Approximate XID_Continue test."""
    cat = unicodedata.category(ch)
    return cat in (
        "Lu", "Ll", "Lt", "Lm", "Lo", "Nl",
        "Mn", "Mc", "Nd", "Pc",
    )


def _is_bare_identifier(name: str) -> bool:
    """Whether a name can be emitted as a bare Python identifier."""
    if not name:
        return False
    if not _is_xid_start(name[0]):
        return False
    if not all(_is_xid_continue(ch) for ch in name):
        return False
    # NFKC stability check
    try:
        nfkc = unicodedata.normalize("NFKC", name)
        return nfkc == name
    except Exception:
        return False


_RESERVED: frozenset[str] = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield", "__debug__",
})

_TYPING_ORDER: tuple[str, ...] = (
    "Any", "Literal", "NotRequired", "Protocol", "TypedDict",
)


def _pad(indent: int) -> str:
    return "    " * indent


# ---------------------------------------------------------------------------
# RenderState
# ---------------------------------------------------------------------------

class _RenderState:
    """Collector threaded through render_type."""

    __slots__ = ("classes", "next_class_counter", "typing", "used_class_names")

    def __init__(self) -> None:
        self.classes: list[str] = []
        self.used_class_names: set[str] = set()
        self.next_class_counter: dict[str, int] = {}
        self.typing: set[str] = set()


# ---------------------------------------------------------------------------
# Control-character escaping
# ---------------------------------------------------------------------------

_UNPRINTABLE = re.compile(r"[\u0000-\u0008\u000e-\u001f\u007f-\u009f]")
_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


def _describe(schema: Any) -> str | None:
    """Collapsed one-line description, or None."""
    if isinstance(schema, dict):
        description = schema.get("description")
    else:
        description = getattr(schema, "description", None)
    if not isinstance(description, str):
        return None
    collapsed = re.sub(r"\s+", " ", description)
    collapsed = _UNPRINTABLE.sub(
        lambda m: f"\\x{ord(m.group()):02x}", collapsed,
    )
    collapsed = _LONE_SURROGATE.sub(
        lambda m: f"\\u{ord(m.group()):04x}", collapsed,
    )
    collapsed = collapsed.strip()
    return collapsed if collapsed else None


def _doc_lines(description: Any, indent: int) -> list[str]:
    """One-line docstring for a tool description, or no lines."""
    collapsed = _describe({"description": description})
    if collapsed is None:
        return []
    escaped = collapsed.replace("\\", "\\\\").replace('"', '\\"')
    return [f'{_pad(indent)}"""{escaped}"""']


# ---------------------------------------------------------------------------
# CamelCase
# ---------------------------------------------------------------------------

def _camel_case(raw: str) -> str:
    """CamelCase a name into a Python type identifier."""
    parts = re.split(r"[^\w]+|_+", raw)
    parts = [p for p in parts if p]
    if not parts:
        return "Tool"
    joined_parts = []
    for part in parts:
        head = part[0]
        try:
            upper = head.upper()
        except Exception:
            upper = head
        joined_parts.append(upper + part[1:])
    joined = "".join(joined_parts)
    with contextlib.suppress(Exception):
        joined = unicodedata.normalize("NFKC", joined)
    result = joined if joined and _is_xid_start(joined[0]) else f"Tool{joined}"
    with contextlib.suppress(Exception):
        result = unicodedata.normalize("NFKC", result)
    return result


# ---------------------------------------------------------------------------
# Class name allocation
# ---------------------------------------------------------------------------

_MAX_CLASS_NAME_BASE = 120
_MAX_LIST_NESTING = 180


def _cap_class_name_base(base: str) -> str:
    if len(base) <= _MAX_CLASS_NAME_BASE:
        return base
    capped = base[:_MAX_CLASS_NAME_BASE]
    # Avoid cutting an astral character in half
    if capped and 0xD800 <= ord(capped[-1]) <= 0xDBFF:
        capped = capped[:-1]
    return capped


def _allocate_class_name(base: str, state: _RenderState) -> str:
    capped = _cap_class_name_base(base)
    name = capped
    if name in state.used_class_names:
        n = state.next_class_counter.get(capped, 2)
        while f"{capped}{n}" in state.used_class_names:
            n += 1
        name = f"{capped}{n}"
        state.next_class_counter[capped] = n + 1
    state.used_class_names.add(name)
    return name


def _child_class_name(base: str, segment: str) -> str:
    raw = f"{base}{segment}"
    with contextlib.suppress(Exception):
        raw = unicodedata.normalize("NFKC", raw)
    return _cap_class_name_base(raw)


# ---------------------------------------------------------------------------
# Scalar rendering
# ---------------------------------------------------------------------------

def _py_scalar(value: JsonSchemaScalar) -> str:
    """Render one validated scalar as Python literal text."""
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value)


def _render_constrained_scalar(
    node: JsonSchemaNodeDict, broad: str, state: _RenderState,
) -> str:
    if "const" in node:
        state.typing.add("Literal")
        return f"Literal[{_py_scalar(node['const'])}]"
    if "enum" in node:
        state.typing.add("Literal")
        return f"Literal[{', '.join(_py_scalar(v) for v in node['enum'])}]"
    return broad


# ---------------------------------------------------------------------------
# Iterative type rendering
# ---------------------------------------------------------------------------

def _render_type(
    schema: Any, class_name: str, state: _RenderState,
) -> str:
    """Map one JSON-Schema node to a Python type expression."""

    try:
        assert_supported_json_schema(schema)
    except Exception:
        state.typing.add("Any")
        return "Any"

    frames: list[dict[str, Any]] = [{
        "schema": schema,
        "class_name": class_name,
        "phase": "start",
        "kind": None,
        "node": None,
        "list_depth": 0,
        "children": [],
        "child_index": 0,
        "child_types": [],
        "entries": [],
        "allocated": None,
    }]
    result: str | None = None

    def finish(type_expr: str) -> None:
        nonlocal result
        frames.pop()
        if not frames:
            result = type_expr
        else:
            frames[-1]["child_types"].append(type_expr)

    while frames:
        frame = frames[-1]

        if frame["phase"] == "children":
            if frame["child_index"] < len(frame["children"]):
                child = frame["children"][frame["child_index"]]
                frame["child_index"] += 1
                frames.append({
                    "schema": child["schema"],
                    "class_name": child["class_name"],
                    "phase": "start",
                    "kind": None,
                    "node": None,
                    "list_depth": child["list_depth"],
                    "children": [],
                    "child_index": 0,
                    "child_types": [],
                    "entries": [],
                    "allocated": None,
                })
                continue

            if frame["kind"] == "oneOf":
                union = ""
                for idx, ct in enumerate(frame["child_types"]):
                    union = ct if idx == 0 else f"{union} | {ct}"
                finish(union)
                continue

            if frame["kind"] == "array":
                finish(f"list[{frame['child_types'][0] if frame['child_types'] else 'Any'}]")
                continue

            # typeddict
            node = frame["node"]
            name = frame["allocated"]
            if node is None or name is None:
                raise RuntimeError("missing typeddict frame state")
            required_set = set(node.get("required", []))
            lines = [f"class {name}(TypedDict):"]
            for idx, (field_name, field_schema) in enumerate(frame["entries"]):
                field_type = frame["child_types"][idx]
                desc = _describe(field_schema)
                if desc is not None:
                    lines.append(f"{_pad(1)}# {desc}")
                if field_name in required_set:
                    lines.append(f"{_pad(1)}{field_name}: {field_type}")
                else:
                    state.typing.add("NotRequired")
                    lines.append(f"{_pad(1)}{field_name}: NotRequired[{field_type}]")
            if node.get("additionalProperties") is not False:
                lines.append(
                    f"{_pad(1)}# Additional keys beyond those declared are allowed."
                )
            if len(lines) == 1:
                lines.append(f"{_pad(1)}pass")
            state.classes.append("\n".join(lines))
            finish(name)
            continue

        # phase == "start"
        frame["phase"] = "children"
        node = frame["schema"]

        if "oneOf" in node and node["oneOf"] is not None:
            frame["kind"] = "oneOf"
            frame["children"] = [
                {
                    "schema": branch,
                    "class_name": _child_class_name(
                        frame["class_name"], str(idx + 1),
                    ),
                    "list_depth": frame["list_depth"],
                }
                for idx, branch in enumerate(node["oneOf"])
            ]
            continue

        if node.get("type") is None:
            state.typing.add("Any")
            finish("Any")
            continue

        node_type = node["type"]
        if node_type == "string":
            finish(_render_constrained_scalar(node, "str", state))
        elif node_type == "number":
            finish(_render_constrained_scalar(node, "float", state))
        elif node_type == "integer":
            finish(_render_constrained_scalar(node, "int", state))
        elif node_type == "boolean":
            finish(_render_constrained_scalar(node, "bool", state))
        elif node_type == "null":
            finish("None")
        elif node_type == "array":
            if node.get("items") is None:
                state.typing.add("Any")
                finish("list[Any]")
            elif frame["list_depth"] >= _MAX_LIST_NESTING:
                state.typing.add("Any")
                finish("Any")
            else:
                frame["kind"] = "array"
                frame["children"] = [{
                    "schema": node["items"],
                    "class_name": frame["class_name"],
                    "list_depth": frame["list_depth"] + 1,
                }]
        elif node_type == "object":
            entries = list((node.get("properties") or {}).items())
            if (
                class_name == ""
                or not all(
                    _is_bare_identifier(name)
                    and name not in _RESERVED
                    and not (name.startswith("__") and not name.endswith("__"))
                    for name, _ in entries
                )
            ) or (not entries and node.get("additionalProperties") is not False):
                state.typing.add("Any")
                finish("dict[str, Any]")
            else:
                frame["kind"] = "typeddict"
                frame["node"] = node
                frame["allocated"] = _allocate_class_name(frame["class_name"], state)
                state.typing.add("TypedDict")
                frame["entries"] = entries
                frame["children"] = [
                    {
                        "schema": child,
                        "class_name": _child_class_name(
                            frame["allocated"] or "", _camel_case(field),
                        ),
                        "list_depth": 1,
                    }
                    for field, child in entries
                ]
        else:
            state.typing.add("Any")
            finish("Any")

    return result if result is not None else "Any"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def json_schema_to_py(schema: Any) -> str:
    """Map one JSON-Schema node to a context-free Python type expression."""
    state = _RenderState()
    return _render_type(schema, "", state)


# ---------------------------------------------------------------------------
# SDK rendering
# ---------------------------------------------------------------------------

_SDK_INSTRUCTIONS = r"""## Writing code for run_code

`run_code` takes two required arguments: `code` — the body of an async Python function (top-level `await` and `return` both work) — and `description`, a short summary of what the program does. At run time exactly two of the names declared below are bound: `tools` and `ToolCallError`. Everything else is a STATIC STUB describing argument and return types — in particular the `TypedDict` classes do NOT exist at run time, so build arguments as plain `dict`/`list` JSON values: `await tools.name({"field": 1})`, never `FooArgs(field=1)`, which raises `NameError`. Inside the program:

- Call tools as `await tools.name(args)` — subscript access for exotic, reserved, or underscore-leading names: `await tools["my-tool"](args)`. Every call resolves to the tool's typed canonical JSON value (each method's return type below). Tool arguments must be lossless JSON.
- A FAILED tool call raises `ToolCallError`, whose `toolName` identifies the failed tool and whose message is human-readable — wrap in `try/except` to handle and continue.
- Independent read-only calls MAY overlap under `asyncio.gather` (safe calls run concurrently; mutating calls run alone, in submission order). Sequence dependent work with `await`.
- Emit the run's answer with `print(...)` and/or a top-level `return <value>`; the returned value must be lossless JSON. ONLY what you print and the returned value come back — intermediate tool results never enter the conversation, so extract just what you need.

The available tools:"""


def render_tools_sdk_py(schemas: list[ToolSdkSchema]) -> str:
    """Render the full ``tools:sdk`` prompt section under Python flavor.

    Deterministic — tools are emitted in lexicographic name order.
    """
    sorted_schemas = sorted(schemas, key=lambda s: s["name"])
    state = _RenderState()
    state.typing.add("Protocol")

    members: list[str] = []
    statements = 0

    for schema in sorted_schemas:
        arg_type = _render_type(
            schema["parameters"], f"{_camel_case(schema['name'])}Args", state,
        )
        output_type = _render_type(
            schema["output"], f"{_camel_case(schema['name'])}Output", state,
        )
        name = schema["name"]
        if (
            _is_bare_identifier(name)
            and name not in _RESERVED
            and not name.startswith("_")
        ):
            doc = _doc_lines(schema.get("description"), 2)
            if doc:
                members.append(
                    f"{_pad(1)}async def {name}(self, args: {arg_type}) -> {output_type}:"
                )
                members.extend(doc)
            else:
                members.append(
                    f"{_pad(1)}async def {name}(self, args: {arg_type}) -> {output_type}: ..."
                )
            statements += 1
        else:
            members.append(
                f"{_pad(1)}# tools[{json.dumps(name)}](args: {arg_type}) -> {output_type}"
            )
            desc = _describe(schema)
            if desc is not None:
                members.append(f"{_pad(1)}#   {desc}")

    body = "\n".join(members) if statements > 0 else "\n".join([f"{_pad(1)}pass", *members])

    imports = sorted(s for s in _TYPING_ORDER if s in state.typing)
    class_block = ""
    if state.classes:
        class_block = "\n\n".join(state.classes) + "\n\n"

    error_decl = "class ToolCallError(Exception):\n    toolName: str"
    declaration = (
        f"from typing import {', '.join(imports)}\n\n"
        f"{error_decl}\n\n"
        f"{class_block}"
        f"class Tools(Protocol):\n{body}\n\n"
        f"tools: Tools"
    )
    return f"{_SDK_INSTRUCTIONS}\n\n```python\n{declaration}\n```"
