"""Read-only profile candidate diff Tool for the learning scenario."""

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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class ProfileDiffTool(Tool):
    """Compare two declarative profile payloads without reading or writing files."""

    name: ClassVar[str] = "profile_diff"
    description: ClassVar[str] = "Compare two profile candidates without applying either one."
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "baseline": {"type": "object", "description": "Current declarative profile payload"},
            "candidate": {"type": "object", "description": "Proposed declarative profile payload"},
        },
        "required": ["baseline", "candidate"],
    }
    is_idempotent: ClassVar[bool] = True
    default_timeout_s: ClassVar[int] = 5

    def validate(self, args: dict[str, Any]) -> str | None:
        if not isinstance(args.get("baseline"), dict):
            return "baseline must be an object"
        if not isinstance(args.get("candidate"), dict):
            return "candidate must be an object"
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
        baseline = args["baseline"]
        candidate = args["candidate"]
        baseline_keys = set(baseline)
        candidate_keys = set(candidate)
        changed = tuple(
            key for key in sorted(baseline_keys & candidate_keys) if baseline[key] != candidate[key]
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "added": sorted(candidate_keys - baseline_keys),
                "removed": sorted(baseline_keys - candidate_keys),
                "changed": list(changed),
                "apply_status": "not_applied",
            },
            latency_ms=int((time.monotonic() - started) * 1000),
        )


class Config(BaseModel):
    """Bundle switch for registration of this read-only tool."""

    model_config = ConfigDict(extra="forbid")
    allowed: bool = True


MANIFEST = ToolManifest(
    identifier="profile_diff",
    type="builtin",
    api=(
        ToolApi(
            name="profile_diff",
            description=ProfileDiffTool.description,
            parameters={
                "type": "object",
                "properties": {
                    "baseline": {
                        "type": "object",
                        "description": "Current declarative profile payload",
                    },
                    "candidate": {
                        "type": "object",
                        "description": "Proposed declarative profile payload",
                    },
                },
                "required": ["baseline", "candidate"],
            },
            is_idempotent=True,
            default_timeout_ms=5_000,
        ),
    ),
    meta=ToolMeta(
        avatar="🔍",
        title="profile_diff",
        description="Compare two profile candidates without applying either one.",
    ),
    parameters={
        "baseline": ParameterSpec(
            type="object",
            required=True,
            ui_hint="object",
            description="Current declarative profile payload",
        ),
        "candidate": ParameterSpec(
            type="object",
            required=True,
            ui_hint="object",
            description="Proposed declarative profile payload",
        ),
    },
)


@plugin(
    id="lca-tool-profile-diff",
    provides=["tools.profile_diff"],
    requires=["tools"],
    implements=["Tool"],
    layer="L1",
    effects="none",
    description="Register a read-only profile candidate diff Tool.",
    test_suite="tests/architecture/test_self_improving_plugins.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.TURN,
        authority=('tool.invoke',),
        evidence=('lca-tool-profile-diff.checked', 'lca-tool-profile-diff.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('tool.invoke', 'tools.profile_diff'),
        emits=('tools.profile_diff.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register only when the scenario explicitly enables this non-effectful tool."""

    if config.allowed:
        ctx.require("tools").register(ProfileDiffTool())


__all__ = ["Config", "ProfileDiffTool"]
