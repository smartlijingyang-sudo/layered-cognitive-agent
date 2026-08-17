"""1:1 port of ``@deepseek-ai/dsh-tools/testing.ts``.

Canonical tool-definition fixtures for repository tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.layer0_infra.dsh_core.tools.schema import (
    ToolDefinition,
    define_tool,
)
from lca.layer0_infra.dsh_core.tools.types import ContentBlock

JsonValue = Any

_CONTENT_VALUE_SCHEMA = {"type": "array", "items": {"type": "json"}}


def define_content_tool_fixture(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    execute: Callable[..., Any],
    timeout_ms: int | None = None,
    finalize_content: Callable[..., list[ContentBlock] | None] | None = None,
    is_concurrency_safe: Callable[[Any], bool] | None = None,
    present_call: Callable[[Any], Any] | None = None,
    present_result: Callable[..., Any] | None = None,
) -> ToolDefinition:
    """Define a test fixture whose canonical value is its rendered content array.

    Product tools must declare domain-owned DTOs instead.
    """
    return define_tool(
        name=name,
        description=description,
        parameters=parameters,
        output={
            "schema": _CONTENT_VALUE_SCHEMA,
            "render": lambda _args, value: value,
        },
        execute=execute,
        timeout_ms=timeout_ms,
        finalize_content=finalize_content,
        is_concurrency_safe=is_concurrency_safe,
        present_call=present_call,
        present_result=present_result,
    )
