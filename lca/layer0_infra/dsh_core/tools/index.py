"""1:1 port of ``@deepseek-ai/dsh-tools/index.ts``.

Tool registry, model presentation modes, and pre/guard/around/post/result
execution pipeline.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from lca.layer0_infra.dsh_core.scope import ScopeKey, scope_of, scope_target
from lca.layer0_infra.dsh_core.scope.store import (
    AnonymousEntries,
    NamedEntries,
    ScopedLayers,
    ScopeLayer,
)
from lca.layer0_infra.dsh_core.tools.code_mode import (
    RUN_CODE_NAME,
    SDK_SECTION_ORDER,
    RunCodeBridgeOptions,
    create_run_code_tool,
)
from lca.layer0_infra.dsh_core.tools.json_schema import (
    assert_supported_json_schema,
    snapshot_json_value,
    validate_json_schema_value,
)
from lca.layer0_infra.dsh_core.tools.py_types import render_tools_sdk_py

# Re-exports from submodules
from lca.layer0_infra.dsh_core.tools.schema import (
    ToolDefinition,
)
from lca.layer0_infra.dsh_core.tools.ts_types import (
    ToolSdkSchema,
    render_tools_sdk,
)
from lca.layer0_infra.dsh_core.tools.types import ContentBlock, TextContentBlock

JsonValue = Any
UserMessage = Any
ToolSchema = dict[str, Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLAPSE_SECTION_ORDER = 99

CODE_ONLY_INSTRUCTION = (
    f"`{RUN_CODE_NAME}` is the only tool you can call directly — a tool call "
    f"naming any other tool fails. Reach every tool the SDK declares below "
    f"from inside the program."
)

TOOL_ABORTED = "ABORTED"
TOOL_ABORTED_BEFORE_DISPATCH = "ABORTED_BEFORE_DISPATCH"

ToolPresentationMode = Literal["native", "code", "both"]

ToolExecutionMode = Literal["parallel", "exclusive"]

# Scheduler symbol (Python equivalent of TS unique symbol)
TOOL_RUNTIME_SCHEDULER = "tools_scheduler"

# SDK renderers
SDK_RENDERERS: dict[str, Callable[[list[ToolSdkSchema]], str]] = {
    "typescript": render_tools_sdk,
    "python": render_tools_sdk_py,
}


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class ToolNotFoundError(Exception):
    """Thrown when the model requests a tool that isn't registered."""

    def __init__(self, tool_name: str, reachable_from: str | None = None) -> None:
        if reachable_from is not None:
            msg = f'unknown tool "{tool_name}": {reachable_from}'
        else:
            msg = f'unknown tool "{tool_name}"'
        super().__init__(msg)
        self.tool_name = tool_name
        self.code = "UNKNOWN_TOOL"
        self.name = "ToolNotFoundError"


class ToolOutputError(Exception):
    """Thrown when a tool body or post-policy value violates its declared output."""

    def __init__(self, tool_name: str, violations: list[str]) -> None:
        self.violations = violations
        self.code = "INVALID_TOOL_OUTPUT"
        self.name = "ToolOutputError"
        super().__init__(
            f'tool "{tool_name}" returned invalid output: {"; ".join(violations)}'
        )


# ---------------------------------------------------------------------------
# Tool execution types
# ---------------------------------------------------------------------------

@dataclass
class ToolErrorInfo:
    name: str
    code: str


@dataclass
class ToolFailure:
    message: str
    info: ToolErrorInfo | None = None


@dataclass
class ToolExecutionInput:
    call_id: str
    name: str
    arguments: Any
    signal: Any = None
    root_call_id: str | None = None
    agent: Any = None
    parent: Any = None


@dataclass
class ToolExecution:
    """One pending tool call inside the registry pipeline."""

    call_id: str
    name: str
    arguments: Any
    token: Any
    root_call_id: str
    signal: Any = None
    agent: Any = None
    parent: Any = None


@dataclass
class ToolRunContext:
    """Runtime context handed to a tool implementation."""

    call_id: str
    name: str
    arguments: Any
    token: Any
    root_call_id: str
    signal: Any = None
    agent: Any = None
    parent: Any = None
    _deferred_contexts: list[Any] = field(default_factory=list)
    _concludes_turn: bool = False

    def defer_context(self, context: Any) -> None:
        self._deferred_contexts.append(context)

    def conclude_turn(self) -> None:
        self._concludes_turn = True


@dataclass
class ToolExecutionSuccess:
    is_error: bool = False
    value: Any = None
    content: list[ContentBlock] = field(default_factory=list)
    meta: Any = None
    additional_contexts: list[Any] | None = None
    concludes_turn: bool | None = None


@dataclass
class ToolExecutionFailure:
    is_error: bool = True
    error: ToolFailure | None = None
    content: list[ContentBlock] = field(default_factory=list)
    meta: Any = None
    additional_contexts: list[Any] | None = None


ToolExecutionResult = Union[ToolExecutionSuccess, ToolExecutionFailure]


@dataclass
class ToolResult:
    """The completed outcome handed to ToolDefinition.present_result."""

    content: list[ContentBlock] = field(default_factory=list)
    is_error: bool = False
    meta: Any = None


# Pre/post decisions
PreToolDecision = Any
PostToolDecision = Any

# Guard type
ToolGuard = Callable[[ToolExecution], str | None]

# Config
@dataclass
class Config:
    mode: ToolPresentationMode = "native"
    max_parallel_sub_calls: int = 10


# ToolRestriction
@dataclass(frozen=True)
class ToolRestriction:
    allow: tuple[str, ...] | None = None
    deny: tuple[str, ...] | None = None


@dataclass
class _CompiledToolRestriction:
    allow: set[str] | None = None
    deny: set[str] | None = None


# CodeDispatchLog
@dataclass
class CodeDispatchLog:
    exec_: ToolExecution
    agent: Any = None
    sub_call_id: str = ""
    name: str = ""
    is_error: bool = False
    content: list[ContentBlock] = field(default_factory=list)


# ScheduledToolPreparation / ScheduledToolDispatch
ScheduledToolPreparation = Any
ScheduledToolDispatch = Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_message(error: Any) -> str:
    """Best-effort human-readable message from an arbitrary thrown value."""
    try:
        if isinstance(error, Exception):
            return str(error)
        if isinstance(error, dict) and "message" in error:
            return str(error["message"])
        return str(error)
    except Exception:
        return "<unprintable thrown value>"


def _failure_message_from_content(content: list[ContentBlock]) -> str:
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextContentBlock):
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        else:
            parts.append(f"[{getattr(block, 'type', 'unknown')} content]")
    text = "\n".join(parts)
    return text if text else "tool result blocked by post-execute policy"


def _error_info(error: Any) -> ToolErrorInfo | None:
    try:
        if hasattr(error, "code") and hasattr(error, "name"):
            return ToolErrorInfo(name=error.name, code=error.code)
    except Exception:
        pass
    return None


def _deep_freeze(value: Any) -> Any:
    """Deep-freeze one value (in Python, return a deep copy as immutability proxy)."""
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _snapshot_tool_value(tool_name: str, candidate: Any) -> Any:
    detached = snapshot_json_value(candidate)
    if detached is None:
        raise ToolOutputError(tool_name, ["value is not lossless JSON"])
    return detached


def _materialize_presentation(candidate: Any) -> Any:
    detached = snapshot_json_value(candidate)
    if detached is None:
        raise TypeError("tool result must be losslessly JSON-serializable")
    return _deep_freeze(detached)


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------

class _ToolLayer(ScopeLayer):
    """One scope's complete tool-registry contribution."""

    def __init__(self, scope: ScopeKey | None = None) -> None:
        scope_label = str(scope) if scope is not None else None
        self.tools = NamedEntries(
            lambda name: Exception(
                f'tool "{name}" is already registered'
                + (" in this scope" if scope_label else "")
            )
        )
        self.restrictions = AnonymousEntries[_CompiledToolRestriction]()
        self.guards = AnonymousEntries[ToolGuard]()
        self.mode: ToolPresentationMode | None = None

    def is_empty(self) -> bool:
        return (
            self.tools.is_empty()
            and self.restrictions.is_empty()
            and self.guards.is_empty()
            and self.mode is None
        )

    def admits(self, name: str) -> bool:
        for filt in self.restrictions.values():
            if filt.allow is not None and name not in filt.allow:
                return False
            if filt.deny is not None and name in filt.deny:
                return False
        return True

    def guard_reason(self, exec_: ToolExecution) -> str | None:
        for guard in self.guards.values():
            reason = guard(exec_)
            if reason is not None:
                return reason
        return None


# ---------------------------------------------------------------------------
# ToolRuntime
# ---------------------------------------------------------------------------

class ToolRuntime:
    """Tool registry and execution pipeline.

    Scoped registrations shadow globals; one visibility resolver feeds
    presentation, lookup, and dispatch.
    """

    inject = ["systemPrompt"]

    def __init__(self, ctx: Any, config: Config | None = None) -> None:
        self.ctx = ctx
        cfg = config or Config()
        self._default_mode: ToolPresentationMode = cfg.mode
        self._max_parallel_sub_calls = max(1, cfg.max_parallel_sub_calls)

        self._deferred_contexts: dict[int, list[Any]] = {}
        self._concluding_executions: set[int] = set()
        self._cancellation_states: dict[int, dict[str, Any]] = {}
        self._content_finalizers: dict[int, Any] = {}
        self._layers = ScopedLayers(
            lambda scope: _ToolLayer(scope),
            lambda: ctx.emit("tools/change") if hasattr(ctx, "emit") else None,
        )
        self._code_transport: ToolDefinition | None = None
        self._canonical_results: dict[int, Any] = {}

        if hasattr(ctx, "systemPrompt"):
            ctx.systemPrompt.tools(lambda context: self._wire_schemas(
                getattr(context, "scope", None)
            ))
            if self._default_mode != "native":
                ctx.systemPrompt.section(self._collapse_section())
                ctx.systemPrompt.section(self._sdk_section())

    # -- prompt sections --

    def _collapse_section(self) -> dict[str, Any]:
        return {
            "name": "tools:code-only",
            "order": COLLAPSE_SECTION_ORDER,
            "text": lambda context: (
                CODE_ONLY_INSTRUCTION
                if self._mode_for(getattr(context, "scope", None)) == "code"
                else ""
            ),
        }

    def _sdk_section(self) -> dict[str, Any]:
        def text_fn(context: Any) -> str:
            scope = getattr(context, "scope", None)
            mode = self._mode_for(scope)
            if mode == "native":
                return ""
            runtime = self._require_code_runtime(mode)
            language = getattr(runtime, "language", "typescript")
            render = SDK_RENDERERS.get(language)
            if render is None:
                raise RuntimeError(f"dsh-tools: no SDK renderer for {language}")
            return render(self._sdk_schemas(scope))

        return {
            "name": "tools:sdk",
            "order": SDK_SECTION_ORDER,
            "text": text_fn,
        }

    def _mode_for(self, scope: ScopeKey | None = None) -> ToolPresentationMode:
        layers = self._layers.chain_layers(scope)
        for layer in reversed(layers):
            if layer.mode is not None:
                return layer.mode
        return self._default_mode

    def _require_code_transport(self) -> ToolDefinition:
        if self._code_transport is None:
            self._code_transport = create_run_code_tool(self, RunCodeBridgeOptions(
                require_runtime=lambda: self._require_code_runtime(self._default_mode),
                peek_runtime=lambda: getattr(self.ctx, "get", lambda *_: None)("codeRuntime"),
                max_parallel=self._max_parallel_sub_calls,
                shape_dispatch_log=self._shape_dispatch_log,
            ))
        return self._code_transport

    def _require_code_runtime(self, mode: ToolPresentationMode) -> Any:
        runtime = None
        if hasattr(self.ctx, "get"):
            runtime = self.ctx.get("codeRuntime")
        if runtime is None:
            raise RuntimeError(
                f'dsh-tools: mode "{mode}" requires a code runtime — '
                f'load a ctx.codeRuntime implementation or set tools mode to "native"'
            )
        language = getattr(runtime, "language", None)
        if language not in SDK_RENDERERS:
            known = ", ".join(repr(k) for k in SDK_RENDERERS)
            raise RuntimeError(
                f"dsh-tools: no SDK renderer registered for runtime language "
                f"{language!r} (known: {known})"
            )
        return runtime

    # -- registration --

    def present_as(self, mode: ToolPresentationMode) -> Callable[[], None]:
        """Present the calling scope's tools in *mode* instead of the default."""
        if scope_of(self.ctx) is None:
            raise RuntimeError(
                "tools.present_as() requires a scoped context (agent.ctx)"
            )

        def setup() -> Callable[[], None]:
            def action(layer: _ToolLayer) -> Callable[[], None]:
                if layer.mode is not None:
                    raise RuntimeError(
                        f'tools.present_as("{mode}") conflicts with "{layer.mode}" '
                        f"already declared for this scope"
                    )
                layer.mode = mode

                def undo() -> None:
                    layer.mode = None

                return undo

            dispose = self._layers.effect(
                self.ctx, action, label="tools.present_as()",
            )
            if mode != "native" and hasattr(self.ctx, "systemPrompt"):
                self.ctx.systemPrompt.section(self._collapse_section())
                self.ctx.systemPrompt.section(self._sdk_section())
            return dispose

        return self.ctx.effect(setup, "tools.present_as()")

    def register(self, definition: ToolDefinition) -> Callable[[], None]:
        """Register globally or in the calling agent scope."""
        name = definition.name
        output = getattr(definition, "output", None)
        if output is None or not hasattr(output, "render"):
            raise TypeError(
                f'tool "{name}" must declare output {{ schema, render, presentationMeta? }}'
            )
        assert_supported_json_schema(output.schema)
        timeout_ms = getattr(definition, "timeout_ms", None)
        if timeout_ms is not None:
            if not isinstance(timeout_ms, (int, float)) or timeout_ms <= 0:
                raise TypeError(f'tool "{name}" timeoutMs must be a positive finite number')
        if name == RUN_CODE_NAME:
            raise RuntimeError(
                f'tool name "{RUN_CODE_NAME}" is reserved for the Code Mode '
                f"presentation transport and cannot be registered or shadowed"
            )
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.tools.insert(name, definition),
            label="tools.register()",
        )

    def restrict(self, filter_: ToolRestriction) -> Callable[[], None]:
        """Restrict global tools for the calling agent scope."""
        scope = scope_of(self.ctx)
        if scope is None:
            raise RuntimeError(
                "tools.restrict() requires a scoped context (agent.ctx)"
            )
        allow = filter_.allow
        deny = filter_.deny
        if allow is None and deny is None:
            raise RuntimeError(
                "tools.restrict({}) is a no-op: pass allow and/or deny"
            )
        compiled = _CompiledToolRestriction(
            allow=set(allow) if allow is not None else None,
            deny=set(deny) if deny is not None else None,
        )
        all_names = list(allow or []) + list(deny or [])
        if RUN_CODE_NAME in all_names:
            raise RuntimeError(
                f'tools.restrict() cannot name reserved Code Mode transport "{RUN_CODE_NAME}"'
            )
        view = self._view(scope)
        unknown = [n for n in all_names if n not in view["restrictable_names"]]
        if unknown:
            raise RuntimeError(
                f"tools.restrict() names unknown global tool(s) "
                f"{', '.join(repr(n) for n in unknown)}"
            )
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.restrictions.append(compiled),
            label="tools.restrict()",
        )

    def guard(self, guard_fn: ToolGuard) -> Callable[[], None]:
        """Register a monotonic guard."""
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.guards.append(guard_fn),
            label="tools.guard()",
            notify=False,
        )

    def _guard_reason(self, exec_: ToolExecution) -> str | None:
        global_reason = self._layers.global_layer.guard_reason(exec_)
        if global_reason is not None:
            return global_reason
        if exec_.agent is None:
            return None
        for layer in self._layers.chain_layers(exec_.agent):
            reason = layer.guard_reason(exec_)
            if reason is not None:
                return reason
        return None

    # -- view resolution --

    def _view(self, scope: ScopeKey | None = None) -> dict[str, Any]:
        layers = self._layers.chain_layers(scope)
        own = self._layers.peek(scope)
        inherited: dict[str, ToolDefinition] = dict(
            self._layers.global_layer.tools.entries()
        )
        for layer in layers:
            if layer is own:
                continue
            for name, definition in layer.tools.entries():
                inherited[name] = definition
        visible: dict[str, ToolDefinition] = {}
        known_names: set[str] = set()
        restrictable_names: set[str] = set()
        for name, definition in inherited.items():
            known_names.add(name)
            restrictable_names.add(name)
            if all(layer.admits(name) for layer in layers):
                visible[name] = definition
        if own is not None:
            for name, definition in own.tools.entries():
                known_names.add(name)
                visible[name] = definition
        if self._mode_for(scope) != "native":
            visible[RUN_CODE_NAME] = self._require_code_transport()
        return {
            "visible": visible,
            "known_names": known_names,
            "restrictable_names": restrictable_names,
        }

    def get(self, name: str, scope: ScopeKey | None = None) -> ToolDefinition | None:
        """Look up a tool as one scope sees it."""
        return self._view(scope)["visible"].get(name)

    def schemas(self, scope: ScopeKey | None = None) -> list[ToolSchema]:
        """Project visible definitions onto the model-facing schema fields."""
        return [
            self._schema_of(defn, True)
            for defn in self._view(scope)["visible"].values()
        ]

    def _sdk_schemas(self, scope: ScopeKey | None = None) -> list[ToolSdkSchema]:
        result: list[ToolSdkSchema] = []
        for defn in self._view(scope)["visible"].values():
            if defn.name == RUN_CODE_NAME:
                continue
            output = snapshot_json_value(defn.output.schema)
            if output is None:
                raise RuntimeError(
                    f'tool "{defn.name}" output schema must be lossless JSON'
                )
            result.append({
                **self._schema_of(defn, True),
                "output": output,
            })
        return result

    def _schema_of(self, definition: ToolDefinition, detach: bool) -> ToolSchema:
        name = definition.name
        description = definition.description
        params = definition.parameters
        detached = snapshot_json_value(params) if detach else params
        if detached is None:
            raise RuntimeError(f'tool "{name}" parameters must be lossless JSON')
        return {"name": name, "description": description, "parameters": detached}

    def _wire_schemas(self, scope: ScopeKey | None = None) -> Any:
        view = self._view(scope)
        mode = self._mode_for(scope)
        if mode == "native":
            schemas = [
                self._schema_of(defn, False)
                for defn in view["visible"].values()
            ]
            return {"schemas": schemas, "knownNames": list(view["known_names"])}
        self._require_code_runtime(mode)
        schemas = [
            self._schema_of(defn, False)
            for defn in view["visible"].values()
        ]
        if mode == "code":
            schemas = [s for s in schemas if s["name"] == RUN_CODE_NAME]
            return {"schemas": schemas, "knownNames": [RUN_CODE_NAME]}
        return {
            "schemas": schemas,
            "knownNames": [*list(view["known_names"]), RUN_CODE_NAME],
        }

    # -- execution --

    def execution_mode(self, exec_input: ToolExecutionInput) -> dict[str, str]:
        """Classify a pending call."""
        tool = self._resolve_execution(
            exec_input.name,
            getattr(exec_input, "agent", None),
            getattr(exec_input, "parent", None) is not None,
        )
        if tool is None or tool.is_concurrency_safe is None:
            return {"kind": "exclusive"}
        try:
            safe = tool.is_concurrency_safe(exec_input.arguments)
            return {"kind": "parallel" if safe is True else "exclusive"}
        except Exception:
            return {"kind": "exclusive"}

    def _resolve_execution(
        self, name: str, scope: ScopeKey | None, nested: bool,
    ) -> ToolDefinition | None:
        tool = self.get(name, scope)
        if tool is None:
            return None
        if self._collapses(name, scope, nested):
            return None
        return tool

    def _collapses(
        self, name: str, scope: ScopeKey | None, nested: bool,
    ) -> bool:
        return (
            not nested
            and self._mode_for(scope) == "code"
            and name != RUN_CODE_NAME
        )

    async def _shape_dispatch_log(
        self, dispatch: CodeDispatchLog,
    ) -> list[ContentBlock]:
        try:
            carrier = scope_target(self, dispatch.agent)
            return await self.ctx.waterfall(
                carrier,
                "tools/code-dispatch-log",
                dispatch,
                lambda: dispatch.content,
            )
        except Exception:
            if hasattr(self.ctx, "logger"):
                self.ctx.logger.warning(
                    f"tools: code-dispatch-log listener failed for {dispatch.name}"
                )
            return dispatch.content

    async def execute(self, exec_input: ToolExecutionInput) -> ToolExecutionResult:
        """Execute through the full pipeline."""
        token = _create_execution_token()
        call_id = exec_input.call_id
        root_call_id = exec_input.root_call_id or call_id
        name = exec_input.name
        agent = getattr(exec_input, "agent", None)
        parent = getattr(exec_input, "parent", None)

        exec_obj = ToolExecution(
            call_id=call_id,
            name=name,
            arguments=exec_input.arguments,
            token=token,
            root_call_id=root_call_id,
            signal=getattr(exec_input, "signal", None),
            agent=agent,
            parent=parent,
        )

        # Snapshot and freeze arguments
        try:
            detached = snapshot_json_value(exec_input.arguments)
            if detached is None:
                raise TypeError(
                    "tool execution arguments must be losslessly JSON-serializable"
                )
            exec_obj.arguments = _deep_freeze(detached)
        except Exception as error:
            return _tool_error_result(error)

        # Check collapse
        visible = self.get(name, agent)
        collapsed = visible is not None and self._collapses(
            name, agent, parent is not None,
        )
        if collapsed:
            if visible is not None:
                return _tool_error_result(ToolNotFoundError(
                    name,
                    f"only `{RUN_CODE_NAME}` is callable directly — call "
                    f"`{name}` from inside a `{RUN_CODE_NAME}` program instead",
                ))
            return _tool_error_result(ToolNotFoundError(name))

        # Create run context
        run_ctx = ToolRunContext(
            call_id=call_id,
            name=name,
            arguments=exec_obj.arguments,
            token=token,
            root_call_id=root_call_id,
            signal=exec_obj.signal,
            agent=agent,
            parent=parent,
        )
        self._deferred_contexts[id(run_ctx)] = []

        # Pre-execute waterfall
        try:
            carrier = scope_target(self, agent)
            gate = await self.ctx.waterfall(
                carrier,
                "tools/pre-execute",
                exec_obj,
                lambda: {"kind": "allow"},
            )
        except Exception as error:
            return _tool_error_result(error)

        # Guard
        denial = None
        if gate.get("kind") == "allow":
            denial = self._guard_reason(exec_obj)
        elif gate.get("kind") == "deny":
            denial = gate.get("reason", "denied")

        if denial is not None:
            return self._materialize_final_result(ToolExecutionFailure(
                content=[TextContentBlock(type="text", text=f"Error: {denial}")],
                error=ToolFailure(message=denial),
            ))

        # Execute
        tool = self._resolve_execution(name, agent, parent is not None)
        if tool is None:
            return _tool_error_result(ToolNotFoundError(name))

        try:
            returned = await tool.execute(exec_obj.arguments, run_ctx)
            result = self._create_success_result(exec_obj, tool, returned)
        except Exception as error:
            result = _tool_error_result(error)

        # Post-execute waterfall
        try:
            carrier = scope_target(self, agent)
            decision = await self.ctx.waterfall(
                carrier,
                "tools/post-execute",
                exec_obj,
                result,
                lambda: {"kind": "accept"},
            )
        except Exception as error:
            result = _tool_error_result(error)
            decision = {"kind": "accept"}

        if decision.get("kind") == "block":
            fb = decision.get("feedback", [])
            msg = _failure_message_from_content(fb)
            result = ToolExecutionFailure(
                content=fb,
                error=ToolFailure(message=msg),
            )

        # Add deferred contexts
        deferred = self._deferred_contexts.pop(id(run_ctx), [])
        if deferred:
            existing = result.additional_contexts or []
            result.additional_contexts = deferred + list(existing)

        # Materialize
        final = self._materialize_final_result(result)

        # Notify
        try:
            if hasattr(self.ctx, "events"):
                self.ctx.events.dispatch("emit", [
                    scope_target(self, agent), "tools/result", exec_obj, final,
                ])
        except Exception:
            pass

        return final

    def _create_success_result(
        self,
        exec_: ToolExecution,
        tool: ToolDefinition,
        candidate: Any,
    ) -> ToolExecutionSuccess:
        detached = _snapshot_tool_value(tool.name, candidate)
        violations = validate_json_schema_value(
            tool.output.schema, detached, "value",
        )
        if violations:
            raise ToolOutputError(tool.name, violations)
        value = _deep_freeze(detached)
        try:
            rendered = tool.output.render(exec_.arguments, value)
        except Exception as error:
            raise ToolOutputError(
                tool.name, [f"output.render failed: {_error_message(error)}"]
            )
        content = snapshot_json_value(rendered)
        if content is None:
            raise ToolOutputError(tool.name, ["output.render returned non-lossless JSON"])

        meta = None
        if (
            exec_.parent is None
            and tool.output.presentation_meta is not None
        ):
            try:
                projected = tool.output.presentation_meta(exec_.arguments, value)
            except Exception as error:
                raise ToolOutputError(
                    tool.name,
                    [f"output.presentationMeta failed: {_error_message(error)}"],
                )
            meta = snapshot_json_value(projected)
            if meta is None:
                raise ToolOutputError(
                    tool.name, ["output.presentationMeta returned non-lossless JSON"]
                )

        return ToolExecutionSuccess(
            value=value,
            content=rendered,
            meta=meta,
        )

    def _materialize_final_result(
        self, result: ToolExecutionResult,
    ) -> ToolExecutionResult:
        try:
            presentation = {
                "content": result.content,
            }
            if result.meta is not None:
                presentation["meta"] = result.meta
            if result.additional_contexts:
                presentation["additionalContexts"] = result.additional_contexts
            if isinstance(result, ToolExecutionFailure):
                return ToolExecutionFailure(
                    content=_deep_freeze(presentation["content"]),
                    error=result.error,
                    meta=_deep_freeze(presentation.get("meta")),
                    additional_contexts=presentation.get("additionalContexts"),
                )
            detached = _deep_freeze(presentation)
            return ToolExecutionSuccess(
                value=result.value,
                content=detached["content"],
                meta=detached.get("meta"),
                additional_contexts=detached.get("additionalContexts"),
                concludes_turn=result.concludes_turn,
            )
        except Exception:
            return _tool_error_result(Exception("result materialization failed"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_execution_token() -> str:
    return f"tool-exec-{uuid.uuid4().hex[:12]}"


def _tool_error_result(error: Any) -> ToolExecutionFailure:
    info = _error_info(error)
    message = _error_message(error)
    return ToolExecutionFailure(
        content=[TextContentBlock(type="text", text=f"Error: {message}")],
        error=ToolFailure(
            message=message,
            info=info,
        ),
    )


# ---------------------------------------------------------------------------
# execute_tool_calls (convenience)
# ---------------------------------------------------------------------------

async def execute_tool_calls(
    runtime: ToolRuntime,
    calls: list[ToolExecutionInput],
) -> list[ToolExecutionResult]:
    """Execute multiple tool calls sequentially."""
    results: list[ToolExecutionResult] = []
    for call in calls:
        result = await runtime.execute(call)
        results.append(result)
    return results
