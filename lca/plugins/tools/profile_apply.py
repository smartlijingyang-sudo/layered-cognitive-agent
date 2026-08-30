"""Dry-run-only profile candidate application Tool for the learning scenario."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ParameterSpec, ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class ProfileApplyTool(Tool):
    """Validate a profile candidate and produce a promotion preview only.

    The tool has no filesystem, Composer, or profile-resolver handle. A request
    with ``dry_run=false`` is rejected instead of silently turning an online
    learning loop into an unreviewed production write path.
    """

    name: ClassVar[str] = "profile_apply"
    description: ClassVar[str] = (
        "Preview an approved profile candidate; production application is disabled."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "candidate": {"type": "object", "description": "Versioned profile candidate metadata"},
            "dry_run": {
                "type": "boolean",
                "description": "Must remain true; this tool never applies production changes",
                "default": True,
            },
        },
        "required": ["candidate"],
    }
    is_idempotent: ClassVar[bool] = True
    default_timeout_s: ClassVar[int] = 5

    def validate(self, args: dict[str, Any]) -> str | None:
        candidate = args.get("candidate")
        if not isinstance(candidate, dict) or not str(candidate.get("candidate_id", "")).strip():
            return "candidate must be an object with a non-empty candidate_id"
        if args.get("dry_run", True) is not True:
            return "profile_apply only supports dry_run=true; production promotion requires an external approval gate"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        started = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=error,
                latency_ms=int((time.monotonic() - started) * 1000),
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        candidate = args["candidate"]
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "candidate_id": candidate["candidate_id"],
                "promotion_status": "requires_external_approval",
                "applied": False,
                "next_gate": "resolve_profile -> compile_plan -> isolated regression -> human approval",
            },
            latency_ms=int((time.monotonic() - started) * 1000),
        )


class Config(BaseModel):
    """Bundle switch for registration of the dry-run-only tool."""

    model_config = ConfigDict(extra="forbid")
    allowed: bool = True


MANIFEST = ToolManifest(
    identifier="profile_apply",
    type="builtin",
    api=(
        ToolApi(
            name="profile_apply",
            description=ProfileApplyTool.description,
            parameters={
                "type": "object",
                "properties": {
                    "candidate": {"type": "object", "description": "Versioned profile candidate metadata"},
                    "dry_run": {
                        "type": "boolean",
                        "description": "Must remain true; this tool never applies production changes",
                        "default": True,
                    },
                },
                "required": ["candidate"],
            },
            is_idempotent=True,
            default_timeout_ms=5_000,
        ),
    ),
    meta=ToolMeta(
        avatar="📋",
        title="profile_apply",
        description="Preview an approved profile candidate; production application is disabled.",
    ),
    parameters={
        "candidate": ParameterSpec(
            type="object",
            required=True,
            ui_hint="object",
            description="Versioned profile candidate metadata",
        ),
        "dry_run": ParameterSpec(
            type="boolean",
            required=False,
            default=True,
            ui_hint="boolean",
            description="Must remain true; this tool never applies production changes",
        ),
    },
)


@plugin(
    id="lca-tool-profile-apply",
    provides=["tools.profile_apply"],
    requires=["tools"],
    implements=["Tool"],
    layer="L1",
    effects="none",
    description="Register a dry-run-only profile candidate promotion preview Tool.",
    test_suite="tests/architecture/test_self_improving_plugins.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register only when the scenario explicitly enables this safe preview tool."""

    if config.allowed:
        ctx.require("tools").register(ProfileApplyTool())


__all__ = ["Config", "ProfileApplyTool"]
