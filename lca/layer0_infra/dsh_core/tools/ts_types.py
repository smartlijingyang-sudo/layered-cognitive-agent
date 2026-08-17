"""1:1 port of ``@deepseek-ai/dsh-tools/ts-types.ts``.

Code Mode codegen: the pure projection from registered tool schemas to the
TypeScript SDK text the model programs against (the ``tools:sdk`` prompt
section).
"""

from __future__ import annotations

import json
import re
from typing import Any

from lca.layer0_infra.dsh_core.tools.json_schema import (
    JsonSchemaNodeDict,
    JsonSchemaScalar,
    assert_supported_json_schema,
)

# ---------------------------------------------------------------------------
# ToolSdkSchema
# ---------------------------------------------------------------------------

ToolSdkSchema = dict[str, Any]
"""Internal Code Mode projection: parameters + canonical output schema."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _render_key(name: str) -> str:
    """Bare when valid identifier, quoted otherwise."""
    return name if _IDENTIFIER.match(name) else json.dumps(name)


def _pad(indent: int) -> str:
    return "  " * indent


def _doc_lines(description: Any, indent: int) -> list[str]:
    """A one-line JSDoc block, or no lines when there is none."""
    if not isinstance(description, str) or not description:
        return []
    collapsed = re.sub(r"\s+", " ", description).strip()
    if not collapsed:
        return []
    collapsed = collapsed.replace("*/", r"*\/")
    return [f"{_pad(indent)}/** {collapsed} */"]


def _render_scalar(value: JsonSchemaScalar) -> str:
    return json.dumps(value)


def _render_constrained_scalar(node: dict[str, Any], type_: str) -> str:
    broad = "number" if type_ == "integer" else type_
    if "const" in node:
        return _render_scalar(node["const"])
    if "enum" in node:
        return " | ".join(_render_scalar(v) for v in node["enum"])
    return broad


# ---------------------------------------------------------------------------
# Composable type document
# ---------------------------------------------------------------------------

class _TypeDocument:
    """A composable type document that can be flattened without recursive concat."""

    __slots__ = ("contains_union_or_intersection", "parts")

    def __init__(
        self,
        parts: list[Any],
        contains_union_or_intersection: bool = False,
    ) -> None:
        self.parts = parts
        self.contains_union_or_intersection = contains_union_or_intersection


def _type_document_from(parts: list[Any]) -> _TypeDocument:
    has_ui = any(
        (isinstance(p, str) and ("|" in p or "&" in p))
        or (isinstance(p, _TypeDocument) and p.contains_union_or_intersection)
        for p in parts
    )
    return _TypeDocument(parts, has_ui)


def _type_document(*parts: Any) -> _TypeDocument:
    return _type_document_from(list(parts))


def _flatten_type_document(document: _TypeDocument) -> str:
    chunks: list[str] = []
    tasks: list[Any] = [document]
    while tasks:
        task = tasks.pop()
        if isinstance(task, str):
            chunks.append(task)
        else:
            for part in reversed(task.parts):
                if part is not None:
                    tasks.append(part)
    return "".join(chunks)


# ---------------------------------------------------------------------------
# Iterative schema-to-TypeScript rendering
# ---------------------------------------------------------------------------

def _render_supported_schema(
    schema: JsonSchemaNodeDict, indent: int,
) -> _TypeDocument:

    frames: list[dict[str, Any]] = [{
        "node": schema,
        "indent": indent,
        "phase": "start",
        "kind": None,
        "children": [],
        "child_index": 0,
        "child_documents": [],
        "entries": [],
    }]
    root_document: _TypeDocument | None = None

    def finish(document: _TypeDocument) -> None:
        nonlocal root_document
        frames.pop()
        if not frames:
            root_document = document
        else:
            frames[-1]["child_documents"].append(document)

    while frames:
        frame = frames[-1]
        if frame["phase"] == "children":
            if frame["child_index"] < len(frame["children"]):
                child = frame["children"][frame["child_index"]]
                frame["child_index"] += 1
                frames.append({
                    "node": child["node"],
                    "indent": child["indent"],
                    "phase": "start",
                    "kind": None,
                    "children": [],
                    "child_index": 0,
                    "child_documents": [],
                    "entries": [],
                })
                continue

            if frame["kind"] == "oneOf":
                parts: list[Any] = []
                for idx, cd in enumerate(frame["child_documents"]):
                    if idx > 0:
                        parts.append(" | ")
                    parts.append(cd)
                finish(_type_document_from(parts))
                continue

            if frame["kind"] == "array":
                child_doc = frame["child_documents"][0]
                if child_doc.contains_union_or_intersection:
                    finish(_type_document("(", child_doc, ")[]"))
                else:
                    finish(_type_document(child_doc, "[]"))
                continue

            # object
            required_set = set(frame["node"].get("required", []))
            parts = ["{"]
            for idx, (entry_name, prop_schema) in enumerate(frame["entries"]):
                child_doc = frame["child_documents"][idx]
                for line in _doc_lines(prop_schema.get("description"), frame["indent"] + 1):
                    parts.append("\n")
                    parts.append(line)
                opt = "" if entry_name in required_set else "?"
                parts.append("\n")
                parts.append(
                    f"{_pad(frame['indent'] + 1)}{_render_key(entry_name)}{opt}: "
                )
                parts.append(child_doc)
                parts.append(";")
            parts.append("\n")
            parts.append(f"{_pad(frame['indent'])}}}")
            declared = _type_document_from(parts)
            if frame["node"].get("additionalProperties") is False:
                finish(declared)
            else:
                finish(_type_document(declared, " & Record<string, JsonValue>"))
            continue

        # phase == "start"
        node = frame["node"]
        if "oneOf" in node and node["oneOf"] is not None:
            frame["kind"] = "oneOf"
            frame["children"] = [
                {"node": child, "indent": frame["indent"]}
                for child in node["oneOf"]
            ]
            frame["child_index"] = 0
            frame["child_documents"] = []
            frame["phase"] = "children"
            continue

        if node.get("type") is None:
            finish(_type_document("JsonValue"))
            continue

        node_type = node["type"]
        if node_type in ("string", "number", "integer", "boolean", "null"):
            finish(_type_document(_render_constrained_scalar(node, node_type)))
        elif node_type == "array":
            if node.get("items") is None:
                finish(_type_document("JsonValue[]"))
            else:
                frame["kind"] = "array"
                frame["children"] = [
                    {"node": node["items"], "indent": frame["indent"]}
                ]
                frame["child_index"] = 0
                frame["child_documents"] = []
                frame["phase"] = "children"
        elif node_type == "object":
            is_open = node.get("additionalProperties") is not False
            entries = list((node.get("properties") or {}).items())
            if not entries:
                if is_open:
                    finish(_type_document("Record<string, JsonValue>"))
                else:
                    finish(_type_document("Record<string, never>"))
            else:
                frame["kind"] = "object"
                frame["entries"] = entries
                frame["children"] = [
                    {"node": child, "indent": frame["indent"] + 1}
                    for _, child in entries
                ]
                frame["child_index"] = 0
                frame["child_documents"] = []
                frame["phase"] = "children"
        else:
            finish(_type_document("unknown"))

    return root_document if root_document is not None else _type_document("unknown")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def json_schema_to_ts(schema: Any, indent: int = 0) -> str:
    """Map one enforced JSON-Schema node to a TypeScript type literal.

    Returns ``unknown`` for malformed or unsupported inputs without throwing.
    """
    try:
        assert_supported_json_schema(schema)
        return _flatten_type_document(_render_supported_schema(schema, indent))
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# SDK rendering
# ---------------------------------------------------------------------------

_SDK_INSTRUCTIONS = r"""## Writing code for run_code

`run_code` takes two required arguments: `code` — the body of an async TypeScript function (erasable syntax only — no `enum` or namespaces; type annotations are advisory, the code runs type-stripped) — and `description`, a short summary of what the program does. Inside the program:

- Call tools as `await tools.name(args)` — quoted access for exotic names: `tools["my-tool"](args)`. Every call resolves to the tool's typed canonical JSON value. Tool arguments must be lossless JSON.
- A FAILED tool call rejects with `ToolCallError`, whose `toolName` identifies the failed tool and whose `message` is human-readable — `try/catch` it to handle and continue.
- Independent read-only calls MAY overlap under `Promise.all` (safe calls run concurrently; mutating calls run alone, in submission order). Sequence dependent work with `await`.
- Emit results with `return` and/or `console.log(...)`. ONLY what you print or return comes back to you — intermediate tool results never enter the conversation, so extract just what you need.

The available tools:"""


def render_tools_sdk(schemas: list[ToolSdkSchema]) -> str:
    """Render the full ``tools:sdk`` prompt section.

    Deterministic — tools are emitted in lexicographic name order.
    """
    sorted_schemas = sorted(schemas, key=lambda s: s["name"])
    args_members: list[str] = []
    output_members: list[str] = []

    for schema in sorted_schemas:
        for line in _doc_lines(schema.get("description"), 1):
            args_members.append(line)
        args_members.append(
            f"{_pad(1)}{_render_key(schema['name'])}: "
            f"{json_schema_to_ts(schema['parameters'], 1)};"
        )
        output_members.append(
            f"{_pad(1)}{_render_key(schema['name'])}: "
            f"{json_schema_to_ts(schema['output'], 1)};"
        )

    args_body = (
        f"\n{chr(10).join(args_members)}\n"
        if args_members
        else ""
    )
    output_body = (
        f"\n{chr(10).join(output_members)}\n"
        if output_members
        else ""
    )
    args_map = f"interface ToolArgsMap {{{args_body}}}"
    output_map = f"interface ToolOutputMap {{{output_body}}}"

    error_class = "\n".join([
        "declare class ToolCallError extends Error {",
        '  readonly name: "ToolCallError";',
        "  readonly toolName: ToolName;",
        "}",
    ])
    tools_decl = "\n".join([
        "declare const tools: {",
        "  [K in ToolName]: (args: ToolArgsMap[K]) => Promise<ToolOutputMap[K]>;",
        "}",
    ])
    declaration = "\n\n".join([
        args_map,
        output_map,
        "type ToolName = keyof ToolOutputMap",
        error_class,
        tools_decl,
    ])
    json_value = (
        "type JsonValue = null | boolean | number | string "
        "| JsonValue[] | { [key: string]: JsonValue }"
    )
    return f"{_SDK_INSTRUCTIONS}\n\n```ts\n{json_value}\n\n{declaration}\n```"
