"""CordisControlTool exposes the Creator four-face protocol as one governed Tool."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.mechanisms.composition import ComposerError
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ParameterSpec, ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.plugins.tools.cordis_control.creator_runtime import CreatorRuntime

IDENTIFIER = "cordis-control"
ALLOWED_ACTIONS = ("inspect", "author", "validate", "promote")

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="cordisControl",
            description="Creator 控制面：inspect、author、validate、promote 四个受治理动作。",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(ALLOWED_ACTIONS),
                        "description": "Creator 动作：inspect/author/validate/promote 四选一",
                    },
                    "name": {
                        "type": "string",
                        "description": "artifact 名；author/validate/promote 必填",
                    },
                    "path": {"type": "string", "description": "author 时的 plugin 源码路径"},
                    "target_scope": {"type": "string", "description": "promote 的目标 scope"},
                    "rollback": {"type": "boolean", "description": "promote 时退休已激活 artifact"},
                    "preset_id": {"type": "string", "description": "release promote 的 preset 名"},
                },
                "required": ["action"],
            },
            is_idempotent=False,
            default_timeout_ms=30_000,
        ),
    ),
    meta=ToolMeta(
        avatar="🧬",
        title="cordis_control",
        description="Creator four-face control surface",
    ),
    parameters={
        "action": ParameterSpec(
            type="string",
            required=True,
            ui_hint="enum",
            description="Creator 动作：inspect/author/validate/promote 四选一",
        ),
        "name": ParameterSpec(
            type="string",
            required=False,
            ui_hint="text",
            description="artifact 名；author/validate/promote 必填",
        ),
        "path": ParameterSpec(
            type="string",
            required=False,
            ui_hint="path",
            description="author 时的 plugin 源码路径",
        ),
        "target_scope": ParameterSpec(
            type="string",
            required=False,
            ui_hint="text",
            description="promote 的目标 scope",
        ),
        "rollback": ParameterSpec(
            type="boolean",
            required=False,
            default=False,
            ui_hint="boolean",
            description="promote 时退休已激活 artifact",
        ),
        "preset_id": ParameterSpec(
            type="string",
            required=False,
            ui_hint="text",
            description="release promote 的 preset 名",
        ),
    },
)


class CordisControlTool(Tool):
    """Run the four Creator faces through one Composer-bound artifact lifecycle."""

    name: ClassVar[str] = "cordis_control"
    description: ClassVar[str] = MANIFEST.api[0].description
    parameters: ClassVar[dict[str, Any]] = MANIFEST.api[0].parameters
    is_idempotent: ClassVar[bool] = False
    default_timeout_s: ClassVar[int] = MANIFEST.api[0].default_timeout_ms // 1000

    def __init__(
        self,
        *,
        composer: Any,
        caller_grant: tuple[str, ...] = (),
        actor_role: str = "",
        preset_root: Path | None = None,
        on_mounted: Any | None = None,
    ) -> None:
        self._composer = composer
        self._caller_grant = tuple(caller_grant)
        self._actor_role = actor_role
        self._preset_root = preset_root
        self._on_mounted = on_mounted
        self._creator = CreatorRuntime(self)

    def validate(self, args: dict[str, Any]) -> str | None:
        action = args.get("action")
        if action not in ALLOWED_ACTIONS:
            return f"action {action!r} 非法；必须是 {list(ALLOWED_ACTIONS)}"
        if action in {"author", "validate", "promote"} and not args.get("name"):
            return f"action={action!r} 必填 name"
        if action == "author" and not args.get("path"):
            return "action='author' 必填 path（plugin 源码路径）"
        if action != "promote" and any(
            key in args for key in ("target_scope", "rollback", "preset_id")
        ):
            return "target_scope、rollback 与 preset_id 仅可用于 action='promote'"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        started = time.monotonic()
        validation = self.validate(args)
        if validation is not None:
            return self._failure(validation, started)
        try:
            action = args["action"]
            if action == "inspect":
                payload = self._creator.inspect(target=args.get("name"))
            elif action == "author":
                payload = self._creator.author(name=args["name"], path=args["path"])
            elif action == "validate":
                payload = self._creator.validate(name=args["name"])
            else:
                payload = self._creator.promote(
                    name=args["name"],
                    target_scope=args.get("target_scope"),
                    rollback=bool(args.get("rollback", False)),
                    preset_id=args.get("preset_id"),
                )
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=payload,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except (ComposerError, ValueError, OSError) as exc:
            return self._failure(str(exc), started, error_code=getattr(exc, "code", None))

    def _failure(
        self, message: str, started: float, *, error_code: object | None = None
    ) -> Observation:
        extra = {FAILURE_KIND: FAILURE_KIND_VALIDATION}
        if error_code is not None:
            extra["error_code"] = getattr(error_code, "value", str(error_code))
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=message,
            latency_ms=int((time.monotonic() - started) * 1000),
            extra=extra,
        )


def build_cordis_control_tool(
    *,
    composer: Any,
    caller_grant: tuple[str, ...] = (),
    actor_role: str = "",
    preset_root: Path | None = None,
    on_mounted: Any | None = None,
) -> Tool:
    """Build the protocol Tool bound to one governed Creator runtime."""

    implementation = CordisControlTool(
        composer=composer,
        caller_grant=caller_grant,
        actor_role=actor_role,
        preset_root=preset_root,
        on_mounted=on_mounted,
    )
    tool_type = type(
        "Tool_cordis_control",
        (Tool,),
        {
            "name": implementation.name,
            "description": implementation.description,
            "parameters": implementation.parameters,
            "is_idempotent": implementation.is_idempotent,
            "default_timeout_s": implementation.default_timeout_s,
            "execute": implementation.execute,
            "validate": implementation.validate,
        },
    )
    return tool_type()  # type: ignore[no-any-return]


__all__ = [
    "ALLOWED_ACTIONS",
    "IDENTIFIER",
    "MANIFEST",
    "CordisControlTool",
    "build_cordis_control_tool",
]
