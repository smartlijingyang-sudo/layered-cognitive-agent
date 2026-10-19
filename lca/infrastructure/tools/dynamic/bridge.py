"""Dynamic tool adapter and bridge for runtime-authored plugins."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any, ClassVar, Literal

import structlog

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.observability.event.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal.journal import RuntimeObserved
from lca.contracts.protocols import Tool
from lca.infrastructure.observability import record

_log = structlog.get_logger(__name__)


class DynamicPluginToolAdapter(Tool):
    """Wraps a dynamically compiled callable or plugin instance into a standard Tool."""

    # ADR-0256: runtime-authored (creator/preset) plugins are third-party code
    # from the built-in toolset's perspective -> ext domain (composio precedent).
    # Without this, ToolsService.register fail-fasts with ValueError.
    namespace: ClassVar[str] = "ext"
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        capabilities: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.description = description or f"Dynamically bridged tool {name}"
        self.parameters = parameters or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        self.capabilities = tuple(capabilities)
        self._func = func

    def validate(self, args: dict[str, Any]) -> str | None:
        """Validate required arguments if defined in parameters."""
        req = self.parameters.get("required", [])
        for field in req:
            if field not in args:
                return f"Missing required parameter: {field!r}"
        return None

    def _schema_properties(self) -> dict[str, Any]:
        """Declared per-field schemas from the parameters schema ({} when schemaless)."""
        params = self.parameters or {}
        props = params.get("properties")
        return props if isinstance(props, dict) else {}

    @staticmethod
    def _should_revive_json(field: str, properties: dict[str, Any]) -> bool:
        """Whether a string arg for `field` may be JSON-revived.

        Revive when the schema declares the field as array/object, or when the
        field is not declared at all (legacy leniency for schemaless bridges).
        A field declared with any other type (e.g. string) passes through untouched.
        """
        decl = properties.get(field)
        if not isinstance(decl, dict):
            return True
        declared_type = decl.get("type")
        if isinstance(declared_type, list):
            return "array" in declared_type or "object" in declared_type
        return declared_type in ("array", "object")

    async def execute(self, args: dict[str, Any]) -> Observation:
        """Execute the wrapped dynamic function with flexible argument unpacking."""
        obs_id = new_id("obs")
        try:
            # Schema-aware normalization (RA-165): revive stringified JSON only
            # for fields the parameters schema declares as array/object.
            # Undeclared fields keep the legacy lenient behavior; fields declared
            # with any other type (e.g. string) pass through untouched.
            properties = self._schema_properties()
            normalized_args: dict[str, Any] = {}
            for k, v in args.items():
                if isinstance(v, str) and self._should_revive_json(k, properties):
                    s = v.strip()
                    if (s.startswith("[") and s.endswith("]")) or (
                        s.startswith("{") and s.endswith("}")
                    ):
                        try:
                            normalized_args[k] = json.loads(s)
                            _log.debug(
                                "dynamic_tool.json_arg_revived",
                                tool_name=self.name,
                                field=k,
                            )
                            continue
                        except (json.JSONDecodeError, ValueError):
                            pass
                normalized_args[k] = v
            args = normalized_args

            sig = inspect.signature(self._func)
            params = list(sig.parameters.values())

            # Determine dispatch calling convention
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
            has_var_positional = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)

            if has_var_keyword:
                call_args = ()
                call_kwargs = args
            elif len(params) == 1 and not has_var_positional:
                # Single parameter: if name matches a key, pass by kwarg; else pass whole dict
                param_name = params[0].name
                if param_name in args:
                    call_args = ()
                    call_kwargs = {param_name: args[param_name]}
                else:
                    call_args = (args,)
                    call_kwargs = {}
            else:
                # Filter kwargs to matching parameter names
                matching_names = {p.name for p in params}
                call_args = ()
                call_kwargs = {k: v for k, v in args.items() if k in matching_names}

            if inspect.iscoroutinefunction(self._func):
                result = await self._func(*call_args, **call_kwargs)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: self._func(*call_args, **call_kwargs)
                )

            return Observation(
                observation_id=obs_id,
                success=True,
                payload=result,
            )
        except Exception as exc:
            _log.warning(
                "dynamic_tool.execute_failed",
                tool_name=self.name,
                error=str(exc),
                exc_info=True,
            )
            return Observation(
                observation_id=obs_id,
                success=False,
                payload=None,
                error=str(exc),
            )


class DynamicToolBridge:
    """Bridge for transforming raw callables/plugin instances into governed Tools."""

    @classmethod
    def bridge_callable(
        cls,
        name: str,
        func: Callable[..., Any],
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        capabilities: tuple[str, ...] = (),
    ) -> DynamicPluginToolAdapter:
        """Wrap a Python callable into a DynamicPluginToolAdapter."""
        return DynamicPluginToolAdapter(
            name=name,
            func=func,
            description=description,
            parameters=parameters,
            capabilities=capabilities,
        )

    @classmethod
    def bridge_instance(
        cls,
        name: str,
        instance: Any,
        meta: dict[str, Any] | None = None,
    ) -> DynamicPluginToolAdapter:
        """Wrap a plugin instance or factory output into a DynamicPluginToolAdapter."""
        target_fn = instance if callable(instance) else getattr(instance, "execute", None)
        if target_fn is None:
            raise TypeError(
                f"Instance for plugin {name!r} is neither callable nor has an execute method"
            )

        meta = meta or {}
        desc = meta.get("description") or getattr(target_fn, "__doc__", "") or f"Plugin tool {name}"
        params = meta.get("parameters")
        caps = tuple(meta.get("capabilities", ()))

        return cls.bridge_callable(
            name=name,
            func=target_fn,
            description=desc.strip(),
            parameters=params,
            capabilities=caps,
        )

    @classmethod
    def register_tool(
        cls,
        tool: Tool,
        *,
        tools_service: Any | None = None,
        safe_executor: Any | None = None,
    ) -> None:
        """Register tool into active ToolsService and synchronize SafeExecutor C5 permission."""
        if tools_service is not None and hasattr(tools_service, "register"):
            tools_service.register(tool)
            _log.info("dynamic_tool.registered_service", tool_name=tool.name)

        if safe_executor is not None and hasattr(safe_executor, "permission_manifest"):
            manifest = safe_executor.permission_manifest
            if hasattr(manifest, "add_permitted"):
                # 优先使用受管公共接口（C4 guardrail）
                manifest.add_permitted(tool.name)
                _log.info("dynamic_tool.authorized_safe_executor", tool_name=tool.name)

        # Emit audit fact
        try:
            record(
                RuntimeObserved(
                    kind=RuntimeKind.PLUGIN,
                    operation="tool.bridged",
                    source=tool.name,
                    outcome=OperationOutcome.OK,
                    attributes={"tool_name": tool.name},
                )
            )
        except Exception:
            _log.debug("dynamic_tool.record_audit_skipped", tool_name=tool.name)

    @classmethod
    def unregister_tool(
        cls,
        tool_name: str,
        *,
        tools_service: Any | None = None,
        safe_executor: Any | None = None,
    ) -> None:
        """Unregister tool from active ToolsService and revoke SafeExecutor C5 permission."""
        if tools_service is not None and hasattr(tools_service, "unregister"):
            tools_service.unregister(tool_name)
            _log.info("dynamic_tool.unregistered_service", tool_name=tool_name)
        elif (
            tools_service is not None
            and hasattr(tools_service, "_tools")
            and isinstance(tools_service._tools, dict)
        ):
            tools_service._tools.pop(tool_name, None)
            _log.info("dynamic_tool.unregistered_service", tool_name=tool_name)

        if safe_executor is not None and hasattr(safe_executor, "permission_manifest"):
            manifest = safe_executor.permission_manifest
            if hasattr(manifest, "revoke_permitted"):
                # 优先使用受管公共接口（C4 guardrail）
                manifest.revoke_permitted(tool_name)
                _log.info("dynamic_tool.revoked_safe_executor", tool_name=tool_name)

        # Emit audit fact
        try:
            record(
                RuntimeObserved(
                    kind=RuntimeKind.PLUGIN,
                    operation="tool.unbridged",
                    source=tool_name,
                    outcome=OperationOutcome.OK,
                    attributes={"tool_name": tool_name},
                )
            )
        except Exception:
            _log.debug("dynamic_tool.record_audit_skipped", tool_name=tool_name)


__all__ = [
    "DynamicPluginToolAdapter",
    "DynamicToolBridge",
]
