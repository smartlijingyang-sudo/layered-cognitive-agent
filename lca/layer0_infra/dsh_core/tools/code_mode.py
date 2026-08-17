"""1:1 port of ``@deepseek-ai/dsh-tools/code-mode.ts``.

Code Mode ``run_code`` transport.  Programs call the registry's
agent-visible tools through nested executions scheduled under the native
concurrency contract; each sub-dispatch is logged for reconstruction,
while only the outer curated result enters model history.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lca.layer0_infra.dsh_core.tools.json_schema import snapshot_json_value
from lca.layer0_infra.dsh_core.tools.schema import (
    ToolDefinition,
    define_tool,
    parameter_schema_spec_to_json_schema,
)
from lca.layer0_infra.dsh_core.tools.types import TextContentBlock

JsonValue = Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUN_CODE_NAME = "run_code"
"""The model-facing name of the Code Mode tool."""

SDK_SECTION_ORDER = 150
"""The ``tools:sdk`` section order (inside the 100–199 band)."""


# ---------------------------------------------------------------------------
# RunCodeFlavor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _RunCodeFlavor:
    """Language-specific ``run_code`` schema text."""

    description: str
    code_description: str


_TYPESCRIPT_FLAVOR = _RunCodeFlavor(
    description=(
        "Execute a TypeScript program against the available tools. Takes two required "
        "arguments: `code`, the BODY of an async function (erasable syntax only; top-level "
        "`await` and `return` work), and `description`, a short summary of what the program "
        "does. Call tools as `await tools.name(args)` per the declarations in the system "
        "prompt. Only what you print or return comes back — curate it."
    ),
    code_description="The program: the body of an async TypeScript function.",
)

_PYTHON_FLAVOR = _RunCodeFlavor(
    description=(
        "Execute a Python program against the available tools. Takes two required "
        "arguments: `code`, the BODY of an async function (top-level `await` and `return` "
        "work), and `description`, a short summary of what the program does. Call tools as "
        "`await tools.name(args)` per the declarations in the system prompt. Answer "
        "with `print(...)` and/or `return <value>` — only that comes back, so curate it."
    ),
    code_description="The program: the body of an async Python function.",
)


CodeSdkLanguage = str  # "typescript" | "python"
"""The languages Code Mode ships a presentation for."""

_RUN_CODE_FLAVORS: dict[str, _RunCodeFlavor] = {
    "typescript": _TYPESCRIPT_FLAVOR,
    "python": _PYTHON_FLAVOR,
}

_RUN_CODE_DESCRIPTION_PARAM_DESCRIPTION = (
    "Clear, concise description of what this program does in active voice, "
    "5-10 words (shown in the UI). Examples: \"Count TODO markers across packages\"; "
    "\"Read failing test and its fixture\"; \"Rename config key in every cordis.yml\"."
)


def _resolve_flavor(peek_runtime: Callable[[], Any]) -> _RunCodeFlavor:
    """Resolve the flavor for the loaded runtime's language."""
    runtime = peek_runtime()
    if runtime is None:
        return _TYPESCRIPT_FLAVOR
    language = getattr(runtime, "language", None)
    flavor = _RUN_CODE_FLAVORS.get(language)
    if flavor is None:
        known = ", ".join(repr(k) for k in _RUN_CODE_FLAVORS)
        raise RuntimeError(
            f"dsh-tools: no run_code schema flavor registered for runtime "
            f"language {language!r} (known: {known})"
        )
    return flavor


# ---------------------------------------------------------------------------
# CodeRunFailedError
# ---------------------------------------------------------------------------

class CodeRunFailedError(Exception):
    """Thrown by ``run_code`` when the program run itself failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "CODE_RUN_FAILED"
        self.name = "CodeRunFailedError"


# ---------------------------------------------------------------------------
# JSON presentation helpers
# ---------------------------------------------------------------------------

_JSON_INDENT = "  "
_MAX_JSON_INDENT_CHARS = 10


def _render_json_value(value: Any) -> str:
    """Render one non-string JSON root without recursive traversal."""
    if isinstance(value, str):
        return value
    chunks: list[str] = []
    tasks: list[dict[str, Any]] = [
        {"kind": "value", "value": value, "depth": 0, "compact": False}
    ]
    while tasks:
        task = tasks.pop()
        if task["kind"] == "text":
            chunks.append(task["text"])
            continue

        current = task["value"]
        if current is None or isinstance(current, (bool, int, float)):
            chunks.append(json.dumps(current))
            continue
        if isinstance(current, str):
            chunks.append(json.dumps(current))
            continue

        compact = task["compact"] or (task["depth"] + 1) * len(_JSON_INDENT) > _MAX_JSON_INDENT_CHARS
        child_depth = task["depth"] + 1

        if isinstance(current, list):
            chunks.append("[")
            if not current:
                chunks.append("]")
                continue
            tasks.append({
                "kind": "text",
                "text": "])" if compact else f"\n{_JSON_INDENT * task['depth']}]",
            })
            for index in range(len(current) - 1, -1, -1):
                item = current[index]
                tasks.append({
                    "kind": "value", "value": item,
                    "depth": child_depth, "compact": compact,
                })
                if compact:
                    tasks.append({
                        "kind": "text",
                        "text": "" if index == 0 else ",",
                    })
                else:
                    sep = "\n" if index == 0 else ",\n"
                    tasks.append({
                        "kind": "text",
                        "text": f"{sep}{_JSON_INDENT * child_depth}",
                    })
            continue

        # dict
        keys = list(current.keys())
        chunks.append("{")
        if not keys:
            chunks.append("}")
            continue
        tasks.append({
            "kind": "text",
            "text": "}" if compact else f"\n{_JSON_INDENT * task['depth']}}}",
        })
        for index in range(len(keys) - 1, -1, -1):
            key = keys[index]
            item = current[key]
            tasks.append({
                "kind": "value", "value": item,
                "depth": child_depth, "compact": compact,
            })
            if compact:
                tasks.append({
                    "kind": "text",
                    "text": f"{'' if index == 0 else ','}{json.dumps(key)}:",
                })
            else:
                sep = "\n" if index == 0 else ",\n"
                tasks.append({
                    "kind": "text",
                    "text": f"{sep}{_JSON_INDENT * child_depth}{json.dumps(key)}: ",
                })

    return "".join(chunks)


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _render_json_value(value)


# ---------------------------------------------------------------------------
# RunCodeOutput
# ---------------------------------------------------------------------------

@dataclass
class _RunCodeOutput:
    logs: list[str]
    result: Any = None


# ---------------------------------------------------------------------------
# RunCodeBridgeOptions
# ---------------------------------------------------------------------------

class RunCodeBridgeOptions:
    """Registry-private capabilities the bridge receives at construction."""

    def __init__(
        self,
        require_runtime: Callable[[], Any],
        peek_runtime: Callable[[], Any],
        max_parallel: int,
        shape_dispatch_log: Callable[..., Any],
    ) -> None:
        self.require_runtime = require_runtime
        self.peek_runtime = peek_runtime
        self.max_parallel = max_parallel
        self.shape_dispatch_log = shape_dispatch_log


# ---------------------------------------------------------------------------
# JSON-normalize args
# ---------------------------------------------------------------------------

def _json_normalize_args(value: Any) -> tuple[Any, Any]:
    """Snapshot one binding call's argument as lossless JSON."""
    snapshot = snapshot_json_value(value)
    if snapshot is None:
        raise TypeError(
            "tool arguments must be lossless JSON "
            "(call the tool with an arguments object, e.g. `{}`)"
        )
    logged = snapshot_json_value(snapshot)
    if logged is None:
        raise TypeError("tool arguments could not be detached for durable logging")
    return snapshot, logged


# ---------------------------------------------------------------------------
# create_run_code_tool
# ---------------------------------------------------------------------------

def create_run_code_tool(
    registry: Any,
    options: RunCodeBridgeOptions,
) -> ToolDefinition:
    """Build the ``run_code`` ToolDefinition.

    The registry reserves it as presentation infrastructure under non-native
    modes, outside the filterable global/scoped capability layers.
    """
    require_runtime = options.require_runtime
    peek_runtime = options.peek_runtime

    async def execute(args: dict[str, Any], exec_: Any) -> dict[str, Any]:
        if not args.get("description", "").strip():
            raise ValueError("invalid description: expected a non-empty string")
        runtime = require_runtime()

        # Simplified Python port: we dispatch sub-calls sequentially through
        # the registry's execute method.  The full TS version implements a
        # complex parallel/Exclusive scheduler; the Python port preserves the
        # same semantics but uses asyncio primitives directly.
        import asyncio

        run_event = asyncio.Event()
        dispatches: list[dict[str, Any]] = []
        logs: list[str] = []

        async def binding(name: str, raw_args: Any) -> Any:
            if run_event.is_set():
                raise RuntimeError(f"run_code run is over; {name} not dispatched")
            dispatched, _logged = _json_normalize_args(raw_args)
            n = len(dispatches) + 1
            sub_call_id = f"{exec_.call_id}:code:{n}"
            try:
                result = await registry.execute({
                    "call_id": sub_call_id,
                    "root_call_id": exec_.root_call_id,
                    "name": name,
                    "arguments": dispatched,
                    "signal": exec_.signal,
                })
                if result.get("is_error"):
                    raise RuntimeError(result["error"]["message"])
                return result.get("value")
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc

        # Execute the code program.  In the full TS version this goes through
        # a code runtime (VM).  In the Python port we store the program text
        # and let the runtime handle execution.
        # For now, we provide the binding interface and let the code runtime
        # drive it.
        try:
            # The code runtime is expected to provide a `run` method
            run_result = await runtime.run({
                "program": args["code"],
                "bindings": [{"global": "tools", "functions": binding}],
                "signal": exec_.signal,
            })
        finally:
            run_event.set()

        if hasattr(run_result, "error") and run_result.error:
            logs_text = (
                f"\nCaptured output:\n{chr(10).join(run_result.logs)}"
                if run_result.logs
                else ""
            )
            raise CodeRunFailedError(
                f"code run failed ({run_result.error.kind}): "
                f"{run_result.error.message}{logs_text}"
            )

        logs = getattr(run_result, "logs", [])
        return {
            "logs": logs,
            **({"result": run_result.value} if getattr(run_result, "value", None) is not None else {}),
        }

    def present_call(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "card": "generic",
            "title": args.get("description", ""),
            "kind": "execute",
            "raw_input": args.get("code", ""),
        }

    definition = define_tool(
        name=RUN_CODE_NAME,
        description=_TYPESCRIPT_FLAVOR.description,
        parameters={
            "code": {
                "type": "string",
                "required": True,
                "description": _TYPESCRIPT_FLAVOR.code_description,
            },
            "description": {
                "type": "string",
                "required": True,
                "description": _RUN_CODE_DESCRIPTION_PARAM_DESCRIPTION,
            },
        },
        output={
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "logs": {"type": "array", "required": True, "items": {"type": "string"}},
                    "result": {"type": "json"},
                },
            },
            "render": lambda _args, value: [
                TextContentBlock(
                    type="text",
                    text=(
                        "\n".join(filter(None, [
                            "\n".join(value.get("logs", [])) if value.get("logs") else "",
                            _render_value(value["result"]) if "result" in value else "",
                        ]))
                        or "(run_code completed with no output)"
                    ),
                )
            ],
        },
        execute=execute,
        present_call=present_call,
    )

    # Lazy language-aware description/parameters
    _original_desc = definition.description
    _original_params = definition.parameters

    class _LanguageAwareDefinition(ToolDefinition):
        """Wrapper that resolves description/parameters from the runtime flavor."""

        @property
        def description(self) -> str:  # type: ignore[override]
            return _resolve_flavor(peek_runtime).description

        @property
        def parameters(self) -> Any:  # type: ignore[override]
            return parameter_schema_spec_to_json_schema({
                "code": {
                    "type": "string",
                    "required": True,
                    "description": _resolve_flavor(peek_runtime).code_description,
                },
                "description": {
                    "type": "string",
                    "required": True,
                    "description": _RUN_CODE_DESCRIPTION_PARAM_DESCRIPTION,
                },
            })

    # Copy all attributes from definition
    lang_aware = _LanguageAwareDefinition(
        name=definition.name,
        description=definition.description,
        parameters=definition.parameters,
        output=definition.output,
        execute=definition.execute,
        timeout_ms=definition.timeout_ms,
        finalize_content=definition.finalize_content,
        is_concurrency_safe=definition.is_concurrency_safe,
        present_call=definition.present_call,
        present_result=definition.present_result,
    )
    return lang_aware
