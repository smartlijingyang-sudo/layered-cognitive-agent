"""phase.concept.effect.pre_dispatch_envelope_check — typed-port 4-gate atomic check.

ADR-0234 (PR-2 of act-subgraph-tightening plan) moved the envelope gates
that ``PipelineSafeExecutor.execute`` internalised into a graph node so
the graph kernel can see them: envelope-shape / permission / grant /
budget. The extraction kept emitting a fifth verdict,
``effect.pre_dispatch.safe-boundary:valid``, but no safe-boundary gate
ever ran in this node -- the executor's old "safe-boundary validation"
was only a plan_ref/scope_ref non-empty check, which the envelope-shape
gate already covers. Emitting a verdict for a gate that never runs is
unearned evidence (RA-115), so the verdict is gone: 4 gates run,
4 verdicts emitted. Real safe-boundary enforcement lives at dispatch
time via ``ControlSlot.ACT_SAFE_BOUNDARY`` plugins
(tool_guards_service, guard_tool_result_spill, guard_tool_timeout,
safe_executor), not at envelope time (``execution_space_ref`` stays
empty until PR-7, so no envelope-time predicate exists to check).

Inputs: envelope (CommandEnvelope)
Outputs: envelope (CommandEnvelope), verdict_refs (tuple[str, ...])

The tool identity is derived from ``envelope.grant.capability``; the
permission gate compares that against ``permission_manifest.allowed_tools``.
This keeps the typed-port contract a single-input / two-output boundary
that fits the existing ``act.fanout → act.dispatch`` wiring without
introducing a new ``tool`` port.

On any gate failure the node raises ``ValueError`` and emits no
``verdict_refs``; the outer edge predicate routes the subgraph to
``terminal.commit`` (fail-loud).
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.contracts.protocols.act.command.envelope import CommandEnvelope
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeExecutor,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_VERDICT_ENVELOPE_SHAPE = "effect.pre_dispatch.envelope-shape:valid"
_VERDICT_PERMISSION = "effect.pre_dispatch.permission:allow"
_VERDICT_GRANT = "effect.pre_dispatch.grant:valid"
_VERDICT_BUDGET = "effect.pre_dispatch.budget:valid"

# NOTE (RA-115): no _VERDICT_SAFE_BOUNDARY. A safe-boundary verdict was
# emitted from the PR-2 extraction (39fa69654) until this fix, but no
# safe-boundary gate ever ran in execute() -- the old executor's
# "safe-boundary validation" was a plan_ref/scope_ref non-empty check,
# subsumed by the envelope-shape gate. Real safe-boundary enforcement
# is at dispatch time via ControlSlot.ACT_SAFE_BOUNDARY plugins.

_ALL_REF_ORDER = (
    _VERDICT_ENVELOPE_SHAPE,
    _VERDICT_PERMISSION,
    _VERDICT_GRANT,
    _VERDICT_BUDGET,
)


@dataclass(frozen=True, slots=True)
class EffectPreDispatchEnvelopeCheckExecutor(NodeExecutor):
    """``effect.pre_dispatch.envelope_check`` 节点执行器。

    4 闸一次性 atomic check:任意闸失败 → raise ValueError,verdict_refs 不 emit。
    safe-boundary 不在此检查（dispatch 时由 ControlSlot.ACT_SAFE_BOUNDARY
    插件执行）；此处曾 emit 的 safe-boundary:valid 是未兑现的 verdict
    (RA-115)，已删除。
    """

    semantic_name: str = "effect.pre_dispatch.envelope_check"
    region: str = "effect"
    declared_inputs: tuple[PortName, ...] = (
        PortName("envelope"),
        PortName("envelopes"),
    )
    declared_outputs: tuple[PortName, ...] = (
        PortName("envelope"),
        PortName("envelopes"),
        PortName("verdict_refs"),
    )
    permission_manifest: ToolPermissionManifest | None = None

    async def execute(self, context: NodeContext, input: NodeInput) -> NodeOutput:
        port_values = input.port_values
        envelope_in = port_values.get(PortName("envelope"))
        envelopes_in = port_values.get(PortName("envelopes"))

        if envelopes_in is not None:
            if isinstance(envelopes_in, (list, tuple)):
                candidates = list(envelopes_in)
            else:
                raise TypeError(
                    "effect.pre_dispatch.envelope_check: 'envelopes' must be tuple or list of CommandEnvelope"
                )
        elif envelope_in is not None:
            candidates = [envelope_in]
        else:
            raise TypeError(
                "effect.pre_dispatch.envelope_check: neither 'envelope' nor 'envelopes' port provided"
            )

        if not candidates:
            raise ValueError("effect.pre_dispatch.envelope_check: batch of envelopes is empty")

        # permission (ADR-0220 PR-A typed-port read; profile-resolved
        # manifest is published onto the kernel runtime carrier so the
        # node reads the active policy at visit time, not the boot-time
        # snapshot bound on the executor instance).
        runtime = getattr(context, "runtime", None)
        manifest = getattr(runtime, "permission_manifest", None) if runtime is not None else None
        if manifest is None:
            manifest = self.permission_manifest
        allowed = manifest.allowed_tools if manifest is not None else None

        for idx, env in enumerate(candidates):
            if not isinstance(env, CommandEnvelope):
                raise TypeError(
                    f"effect.pre_dispatch.envelope_check: envelope #{idx} must be CommandEnvelope, got {type(env).__name__}"
                )

            # Tool identity is the grant capability the envelope was minted with.
            tool_name: str = env.grant.capability

            # envelope-shape
            if not (env.plan_ref and env.scope_ref and env.decision_ref and env.provider):
                raise ValueError(
                    "effect.pre_dispatch.envelope_check: envelope-shape incomplete "
                    f"(plan_ref={env.plan_ref!r}, scope_ref={env.scope_ref!r}, "
                    f"decision_ref={env.decision_ref!r}, provider={env.provider!r})"
                )

            # permission
            if allowed is None or tool_name not in allowed:
                raise ValueError(
                    f"effect.pre_dispatch.envelope_check: permission denied for tool {tool_name!r}"
                )

            # grant
            grant = env.grant
            if grant.effect_class != "tools":
                raise ValueError(
                    "effect.pre_dispatch.envelope_check: grant mismatch "
                    f"(capability={grant.capability!r}, tool={tool_name!r}, "
                    f"effect_class={grant.effect_class!r})"
                )

            # budget
            res = env.budget_reservation
            if min(res.tokens, res.cost_cents, res.wall_clock_ms, res.tool_calls) < 0:
                raise ValueError(
                    f"effect.pre_dispatch.envelope_check: budget reservation negative ({res!r})"
                )

        primary_envelope = candidates[0]
        return NodeOutput(
            port_values={
                PortName("envelope"): primary_envelope,
                PortName("envelopes"): tuple(candidates),
                PortName("verdict_refs"): _ALL_REF_ORDER,
            }
        )


@plugin(
    id="phase.concept.effect.pre_dispatch_envelope_check",
    Config=None,
    provides=("effect::effect.pre_dispatch.envelope_check",),
    # PR-2 close-out: ``permission_manifest`` is provided by the
    # profile's policy adapters (default: ``lca-effect-permission-manifest-default``
    # ships a deny-by-default ``ToolPermissionManifest``). The wildcard
    # ``requires`` accepts any ``permission_manifest.<name>`` provider
    # so production profiles can swap in their own allowlist without
    # editing this node.
    requires=("permission_manifest.*",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_effect_pre_dispatch_envelope_check.checked",
                "phase_concept_effect_pre_dispatch_envelope_check.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object = None) -> None:
    del config
    # ``permission_manifest`` is an optional capability: when no
    # PluginSpec provider is wired into the resolved profile the
    # permission gate is fail-loud deny-by-default (see
    # ``EffectPreDispatchEnvelopeCheckExecutor.execute``).
    # ``require_matching`` walks the ``permission_manifest.*`` binding
    # chain — empty when no provider is registered.
    matches = ctx.require_matching("permission_manifest.")
    # Pick the first manifest; production profiles that ship
    # multiple ``permission_manifest.*`` providers should use the
    # highest-precedence entry (a single ``tool_permission_manifest``
    # producer is the common case).
    permission_manifest = next(iter(matches.values())) if matches else None
    executor = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=permission_manifest,
    )
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = [
    "_ALL_REF_ORDER",
    "EffectPreDispatchEnvelopeCheckExecutor",
]
