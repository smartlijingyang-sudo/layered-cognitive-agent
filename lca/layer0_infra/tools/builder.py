"""Generic tool builder — manifest + executor → Tool Protocol instances.

One function turns any ``ToolManifest`` + executor into a list of ``Tool``
objects the reasoner can call.  Keeps the wiring convention identical
across ``lca_computer``, ``lca_sandbox``, ``web_search``, etc.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ToolApi, ToolManifest
from lca.contracts.protocols import Tool

ToolResult = Observation | dict[str, Any]


def build_tools_from_manifest(
    manifest: ToolManifest,
    executor: object,
    *,
    invoke_fn: Callable[[object, str, dict[str, Any]], Awaitable[ToolResult]] | None = None,
    observation_builder: Callable[[ToolResult, str, float], Observation] | None = None,
    name_prefix: str = "",
) -> list[Tool]:
    """Instantiate one ``Tool`` per API in the manifest.

    Parameters
    ----------
    manifest:
        Declares the API surface (names, schemas, descriptions).
    executor:
        Object that implements one method per API name.
    invoke_fn:
        How to call the executor.  Defaults to ``getattr(executor, api.name)``
        for self-contained executors, or ``executor.invoke(api_name, params)``
        for ComputerOps-backed executors.
    observation_builder:
        Convert a raw result into a journal ``Observation``.  Defaults to
        wrapping dict results in a generic observation.
    name_prefix:
        Prepended to each tool name (e.g. ``"local_"`` for machine tools).
    """
    tools: list[Tool] = []
    for api in manifest.api:
        tool_name = f"{name_prefix}{api.name}"
        tools.append(
            _build_single_tool(
                api=api,
                executor=executor,
                tool_name=tool_name,
                invoke_fn=invoke_fn,
                observation_builder=observation_builder,
            )
        )
    return tools


def _build_single_tool(
    *,
    api: ToolApi,
    executor: object,
    tool_name: str,
    invoke_fn: Callable[[object, str, dict[str, Any]], Awaitable[ToolResult]] | None,
    observation_builder: Callable[[ToolResult, str, float], Observation] | None,
) -> Tool:
    validator = getattr(executor, "validate", None)

    async def execute(_self: Tool, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        if invoke_fn is not None:
            raw = await invoke_fn(executor, api.name, args)
        else:
            method = getattr(executor, api.name, None)
            if method is None:
                raise AttributeError(f"{type(executor).__name__} has no method {api.name!r}")
            raw = await method(args)

        latency_ms = int((time.monotonic() - start) * 1000)
        if observation_builder is not None:
            return observation_builder(raw, tool_name, start)
        return _default_observation(raw, latency_ms)

    def validate(self: Tool, args: dict[str, Any]) -> str | None:
        if validator is not None:
            return validator(api.name, args)
        return None

    tool_cls = type(
        f"Tool_{tool_name}",
        (Tool,),
        {
            "name": tool_name,
            "description": api.description,
            "parameters": api.parameters,
            "is_idempotent": api.is_idempotent,
            "default_timeout_s": api.default_timeout_ms // 1000,
            "execute": execute,
            "validate": validate,
        },
    )
    return tool_cls()  # type: ignore[no-any-return]


def _default_observation(raw: Any, latency_ms: int) -> Observation:
    """Fallback: wrap a dict or primitive into an Observation."""
    if isinstance(raw, Observation):
        return raw
    if isinstance(raw, dict):
        success = bool(raw.get("success", True))
        return Observation(
            observation_id=new_id("obs"),
            success=success,
            payload=raw,
            content_type=ContentType.STRUCTURED,
            error=raw.get("error", "") if not success else "",
            latency_ms=latency_ms,
            extra={FAILURE_KIND: FAILURE_KIND_EXECUTION} if not success else {},
        )
    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=raw,
        latency_ms=latency_ms,
    )
