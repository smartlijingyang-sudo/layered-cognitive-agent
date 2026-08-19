"""Auto-generated surface skeleton for upstream ``core/tools/src/index.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/tools/src/index.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "RUN_CODE_NAME",
    "TOOL_ABORTED",
    "TOOL_ABORTED_BEFORE_DISPATCH",
    "TOOL_RUNTIME_SCHEDULER",
    "ArrayValueSchemaSpec",
    "BooleanValueSchemaSpec",
    "CodeDispatchEventData",
    "CodeDispatchLog",
    "CodeDispatchStartEventData",
    "CodeRunFailedError",
    "Config",
    "ContentToolFixtureOptions",
    "DefineToolOptions",
    "DiffCallView",
    "DiffResultView",
    "FileDiff",
    "FileLocation",
    "GenericCallView",
    "GenericResultView",
    "InferArgs",
    "InferValue",
    "IntegerValueSchemaSpec",
    "JsonSchemaError",
    "JsonSchemaNode",
    "JsonSchemaScalar",
    "JsonSchemaType",
    "JsonValue",
    "JsonValueSchemaSpec",
    "NullValueSchemaSpec",
    "NumberValueSchemaSpec",
    "ObjectJsonSchema",
    "ObjectValueSchemaSpec",
    "OneOfValueSchemaSpec",
    "ParameterJsonSchema",
    "ParameterPropertySpec",
    "ParameterSchemaSpec",
    "PostToolDecision",
    "PreToolDecision",
    "ReadFileLine",
    "ReadResultView",
    "ScheduledToolDispatch",
    "ScheduledToolPreparation",
    "SearchFileMatches",
    "SearchLineMatch",
    "SearchMatchesResultView",
    "SearchPathsResultView",
    "SearchResultView",
    "StringValueSchemaSpec",
    "TerminalCallView",
    "TerminalResultView",
    "ToolArgsError",
    "ToolCallKind",
    "ToolCallView",
    "ToolDefinition",
    "ToolDispatchExecution",
    "ToolErrorInfo",
    "ToolExecution",
    "ToolExecutionFailure",
    "ToolExecutionInput",
    "ToolExecutionMode",
    "ToolExecutionResult",
    "ToolExecutionSuccess",
    "ToolExecutionToken",
    "ToolFailure",
    "ToolGuard",
    "ToolNotFoundError",
    "ToolOutputDefinition",
    "ToolOutputError",
    "ToolPresentationMode",
    "ToolRestriction",
    "ToolResult",
    "ToolResultView",
    "ToolRunContext",
    "ToolRuntime",
    "ToolRuntimeScheduler",
    "ValueSchemaAnnotations",
    "ValueSchemaSpec",
    "WebFetchResultView",
    "WebResultView",
    "WebSearchResultView",
    "WebSource",
    "assertObjectJsonSchema",
    "assertSupportedJsonSchema",
    "defineContentToolFixture",
    "defineTool",
    "jsonSchemaToPy",
    "jsonSchemaToTs",
    "parameterSchemaSpecToJsonSchema",
    "renderToolsSdk",
    "renderToolsSdkPy",
    "validateArgs",
    "validateJsonSchemaValue",
    "valueSchemaSpecToJsonSchema",
]

ArrayValueSchemaSpec: TypeAlias = object  # port: surface stub

BooleanValueSchemaSpec: TypeAlias = object  # port: surface stub

CodeDispatchEventData: TypeAlias = object  # port: surface stub

CodeDispatchStartEventData: TypeAlias = object  # port: surface stub

ContentToolFixtureOptions: TypeAlias = object  # port: surface stub

DefineToolOptions: TypeAlias = object  # port: surface stub

DiffCallView: TypeAlias = object  # port: surface stub

DiffResultView: TypeAlias = object  # port: surface stub

FileDiff: TypeAlias = object  # port: surface stub

FileLocation: TypeAlias = object  # port: surface stub

GenericCallView: TypeAlias = object  # port: surface stub

GenericResultView: TypeAlias = object  # port: surface stub

InferArgs: TypeAlias = object  # port: surface stub

InferValue: TypeAlias = object  # port: surface stub

IntegerValueSchemaSpec: TypeAlias = object  # port: surface stub

JsonSchemaNode: TypeAlias = object  # port: surface stub

JsonSchemaScalar: TypeAlias = object  # port: surface stub

JsonSchemaType: TypeAlias = object  # port: surface stub

JsonValue: TypeAlias = object  # port: surface stub

JsonValueSchemaSpec: TypeAlias = object  # port: surface stub

NullValueSchemaSpec: TypeAlias = object  # port: surface stub

NumberValueSchemaSpec: TypeAlias = object  # port: surface stub

ObjectJsonSchema: TypeAlias = object  # port: surface stub

ObjectValueSchemaSpec: TypeAlias = object  # port: surface stub

OneOfValueSchemaSpec: TypeAlias = object  # port: surface stub

ParameterJsonSchema: TypeAlias = object  # port: surface stub

ParameterPropertySpec: TypeAlias = object  # port: surface stub

ParameterSchemaSpec: TypeAlias = object  # port: surface stub

PostToolDecision: TypeAlias = object  # port: surface stub

PreToolDecision: TypeAlias = object  # port: surface stub

ReadFileLine: TypeAlias = object  # port: surface stub

ReadResultView: TypeAlias = object  # port: surface stub

ScheduledToolDispatch: TypeAlias = object  # port: surface stub

ScheduledToolPreparation: TypeAlias = object  # port: surface stub

SearchFileMatches: TypeAlias = object  # port: surface stub

SearchLineMatch: TypeAlias = object  # port: surface stub

SearchMatchesResultView: TypeAlias = object  # port: surface stub

SearchPathsResultView: TypeAlias = object  # port: surface stub

SearchResultView: TypeAlias = object  # port: surface stub

StringValueSchemaSpec: TypeAlias = object  # port: surface stub

TerminalCallView: TypeAlias = object  # port: surface stub

TerminalResultView: TypeAlias = object  # port: surface stub

ToolCallKind: TypeAlias = object  # port: surface stub

ToolCallView: TypeAlias = object  # port: surface stub

ToolExecutionMode: TypeAlias = object  # port: surface stub

ToolExecutionResult: TypeAlias = object  # port: surface stub

ToolExecutionToken: TypeAlias = object  # port: surface stub

ToolGuard: TypeAlias = object  # port: surface stub

ToolPresentationMode: TypeAlias = object  # port: surface stub

ToolResultView: TypeAlias = object  # port: surface stub

ValueSchemaAnnotations: TypeAlias = object  # port: surface stub

ValueSchemaSpec: TypeAlias = object  # port: surface stub

WebFetchResultView: TypeAlias = object  # port: surface stub

WebResultView: TypeAlias = object  # port: surface stub

WebSearchResultView: TypeAlias = object  # port: surface stub

WebSource: TypeAlias = object  # port: surface stub

TOOL_ABORTED = None  # port: surface stub

TOOL_ABORTED_BEFORE_DISPATCH = None  # port: surface stub

TOOL_RUNTIME_SCHEDULER = None  # port: surface stub

class ToolNotFoundError:
    """Surface stub for upstream class ``ToolNotFoundError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ToolNotFoundError.__init__ from core/tools/src/index.ts")

class ToolOutputError:
    """Surface stub for upstream class ``ToolOutputError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ToolOutputError.__init__ from core/tools/src/index.ts")

class ToolRuntime:
    """Surface stub for upstream class ``ToolRuntime``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ToolRuntime.__init__ from core/tools/src/index.ts")

CodeRunFailedError = None  # port: surface stub (reexport)

JsonSchemaError = None  # port: surface stub (reexport)

RUN_CODE_NAME = None  # port: surface stub (reexport)

ToolArgsError = None  # port: surface stub (reexport)

assertObjectJsonSchema = None  # port: surface stub (reexport)

assertSupportedJsonSchema = None  # port: surface stub (reexport)

defineContentToolFixture = None  # port: surface stub (reexport)

defineTool = None  # port: surface stub (reexport)

jsonSchemaToPy = None  # port: surface stub (reexport)

jsonSchemaToTs = None  # port: surface stub (reexport)

parameterSchemaSpecToJsonSchema = None  # port: surface stub (reexport)

renderToolsSdk = None  # port: surface stub (reexport)

renderToolsSdkPy = None  # port: surface stub (reexport)

validateArgs = None  # port: surface stub (reexport)

validateJsonSchemaValue = None  # port: surface stub (reexport)

valueSchemaSpecToJsonSchema = None  # port: surface stub (reexport)

class CodeDispatchLog(Protocol):
    """Surface stub for upstream interface ``CodeDispatchLog``."""
    pass

class Config(Protocol):
    """Surface stub for upstream interface ``Config``."""
    pass

class ToolDefinition(Protocol):
    """Surface stub for upstream interface ``ToolDefinition``."""
    pass

class ToolDispatchExecution(Protocol):
    """Surface stub for upstream interface ``ToolDispatchExecution``."""
    pass

class ToolErrorInfo(Protocol):
    """Surface stub for upstream interface ``ToolErrorInfo``."""
    pass

class ToolExecution(Protocol):
    """Surface stub for upstream interface ``ToolExecution``."""
    pass

class ToolExecutionFailure(Protocol):
    """Surface stub for upstream interface ``ToolExecutionFailure``."""
    pass

class ToolExecutionInput(Protocol):
    """Surface stub for upstream interface ``ToolExecutionInput``."""
    pass

class ToolExecutionSuccess(Protocol):
    """Surface stub for upstream interface ``ToolExecutionSuccess``."""
    pass

class ToolFailure(Protocol):
    """Surface stub for upstream interface ``ToolFailure``."""
    pass

class ToolOutputDefinition(Protocol):
    """Surface stub for upstream interface ``ToolOutputDefinition``."""
    pass

class ToolRestriction(Protocol):
    """Surface stub for upstream interface ``ToolRestriction``."""
    pass

class ToolResult(Protocol):
    """Surface stub for upstream interface ``ToolResult``."""
    pass

class ToolRunContext(Protocol):
    """Surface stub for upstream interface ``ToolRunContext``."""
    pass

class ToolRuntimeScheduler(Protocol):
    """Surface stub for upstream interface ``ToolRuntimeScheduler``."""
    pass
