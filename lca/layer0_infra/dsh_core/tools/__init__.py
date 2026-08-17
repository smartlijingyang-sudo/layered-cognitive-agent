"""1:1 port of ``@deepseek-ai/dsh-tools``.

Re-exports the public surface from all tool submodules.
"""

from __future__ import annotations

from lca.layer0_infra.dsh_core.tools.code_mode import (
    RUN_CODE_NAME,
    SDK_SECTION_ORDER,
    CodeRunFailedError,
    RunCodeBridgeOptions,
    create_run_code_tool,
)
from lca.layer0_infra.dsh_core.tools.index import (
    CODE_ONLY_INSTRUCTION,
    COLLAPSE_SECTION_ORDER,
    TOOL_ABORTED,
    TOOL_ABORTED_BEFORE_DISPATCH,
    TOOL_RUNTIME_SCHEDULER,
    CodeDispatchLog,
    Config,
    ToolErrorInfo,
    ToolExecution,
    ToolExecutionFailure,
    ToolExecutionInput,
    ToolExecutionSuccess,
    ToolFailure,
    ToolNotFoundError,
    ToolOutputError,
    ToolPresentationMode,
    ToolRestriction,
    ToolResult,
    ToolRunContext,
    ToolRuntime,
    _CompiledToolRestriction,
    execute_tool_calls,
)
from lca.layer0_infra.dsh_core.tools.json_schema import (
    JsonSchemaError,
    assert_object_json_schema,
    assert_supported_json_schema,
    is_json_schema_record,
    is_plain_json_array,
    is_plain_json_record,
    snapshot_json_value,
    validate_json_schema_value,
)
from lca.layer0_infra.dsh_core.tools.py_types import (
    render_tools_sdk_py,
)
from lca.layer0_infra.dsh_core.tools.schema import (
    ToolArgsError,
    ToolDefinition,
    define_tool,
    validate_args,
)
from lca.layer0_infra.dsh_core.tools.ts_types import (
    ToolSdkSchema,
    render_tools_sdk,
)
from lca.layer0_infra.dsh_core.tools.types import (
    CodeDispatchEventData,
    CodeDispatchStartEventData,
    ContentBlock,
    TextContentBlock,
)

__all__ = [
    # index
    "CODE_ONLY_INSTRUCTION",
    "COLLAPSE_SECTION_ORDER",
    # code-mode
    "RUN_CODE_NAME",
    "SDK_SECTION_ORDER",
    "TOOL_ABORTED",
    "TOOL_ABORTED_BEFORE_DISPATCH",
    "TOOL_RUNTIME_SCHEDULER",
    "CodeDispatchEventData",
    "CodeDispatchLog",
    "CodeDispatchStartEventData",
    "CodeRunFailedError",
    "Config",
    # types
    "ContentBlock",
    # json-schema
    "JsonSchemaError",
    "RunCodeBridgeOptions",
    "TextContentBlock",
    # schema
    "ToolArgsError",
    "ToolDefinition",
    "ToolErrorInfo",
    "ToolExecution",
    "ToolExecutionFailure",
    "ToolExecutionInput",
    "ToolExecutionSuccess",
    "ToolFailure",
    "ToolNotFoundError",
    "ToolOutputError",
    "ToolPresentationMode",
    "ToolRestriction",
    "ToolResult",
    "ToolRunContext",
    "ToolRuntime",
    # ts/py types
    "ToolSdkSchema",
    "_CompiledToolRestriction",
    "assert_object_json_schema",
    "assert_supported_json_schema",
    "create_run_code_tool",
    "define_tool",
    "execute_tool_calls",
    "is_json_schema_record",
    "is_plain_json_array",
    "is_plain_json_record",
    "render_tools_sdk",
    "render_tools_sdk_py",
    "snapshot_json_value",
    "validate_args",
    "validate_json_schema_value",
]
