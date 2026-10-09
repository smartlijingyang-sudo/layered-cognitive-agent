"""phase.concept.act_subgraph.act_authorize — policy-level authorization.

concept.act.subgraph 节点 2 (``concept.act.authorize``):typed
``Decision`` + ``AgentState`` → ``Decision``。从 ``control.act.budget``,
``control.act.constrain`` 和 ``control.act.safe-boundary`` 提取的授权逻辑。

执行四类策略检查:
1. Budget:steps / tokens / cost_usd 任一超限拒绝
2. Constraint:USE_TOOL tool_calls call_ids 必须唯一
3. Safety boundary:拒绝明显危险的 tool_name(本地确定性检查)
4. Grant（ADR-0292 §10 P3）:声明了 required_grant 的工具必须在该 grant 的
   ambient TrustEnvelope 内,否则输出 grant_refused 路由到 terminal.commit
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.observability.evidence.evidence import (
    Classification,
    RetentionClass,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.runtime.trust import get_current_trust_envelope
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_NEXT_HINT_GRANT_REFUSED = "grant_refused"


def _required_grant_of(tool: object) -> str:
    """Return the tool's declared grant requirement, or ``""`` when none.

    与 ``lca.infrastructure.tools.assistant.filter._required_grant`` 同语义：
    ``Tool`` 协议不携带 grant 字段，需要 grant 的工具以 ``required_grant``
    class attribute 声明。grant-agnostic 工具不受运行时授权检查约束。
    """
    return str(getattr(tool, "required_grant", "") or "").strip()


def _no_refusal() -> RoutingDecision:
    """默认路由：无授权拒绝，放行到下游 ``act.approve.gate``。"""
    return RoutingDecision(action_type=ActionType.RESPOND, next_node=None, next_hint=None)


def _route_refusal_to_evidence(
    missing_grants: list[str],
    decision_id: str,
) -> None:
    """ADR-0292 §10 审计：把授权拒绝写入 run-trace evidence ledger。

    与授权门原 §10 实现的 payload 形态一致，gate 名改为 ``act.authorize``。
    observability 未绑定时静默跳过（no-ref 路径）。
    """
    try:
        from lca.infrastructure.observability import resolve_evidence_store
    except ImportError:  # pragma: no cover - packaged without observability
        return
    store = resolve_evidence_store()
    if store is None:
        return
    import json
    from datetime import UTC, datetime

    payload = json.dumps(
        {
            "event": "authorization_refusal",
            "gate": "act.authorize",
            "adr": "0292",
            "section": "10",
            "decision_id": decision_id,
            "missing_grants": missing_grants,
            "refused_at": datetime.now(UTC).isoformat(),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    store.prepare(
        payload,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
        media_type="application/json",
        prepared_by="act.authorize",
    )


def _grant_refusal_routing(decision: Decision, tools: object) -> RoutingDecision:
    """ADR-0292 §10 P3 运行时授权检查。

    对每个 ``tool_call``，用 per-run ``ToolsService`` 解析该工具的
    ``required_grant``。``required_grant`` 非空且不在 ambient
    TrustEnvelope 的 grant 集（含 envelope 未绑定）→ 拒绝，路由到
    ``terminal.commit``，并写 evidence。检查不读 ``decision.needs_approval``。
    """
    envelope = get_current_trust_envelope()
    if decision.action_type != "use_tool" or not decision.tool_calls:
        return _no_refusal()
    missing: list[str] = []
    for call in decision.tool_calls:
        tool = getattr(tools, "get", lambda _name: None)(call.tool_name)
        required_grant = _required_grant_of(tool)
        if required_grant and (envelope is None or not envelope.grants(required_grant)):
            missing.append(required_grant)
    if not missing:
        return _no_refusal()
    _route_refusal_to_evidence(sorted(set(missing)), decision.decision_id)
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        next_node="terminal.commit",
        next_hint=_NEXT_HINT_GRANT_REFUSED,
    )


@dataclass(frozen=True, slots=True)
class ActAuthorizeExecutor:
    """``concept.act.authorize`` 节点:策略级授权检查 (policy-level authorization)。"""

    semantic_name: str = "act.authorize"
    region: str = "act"
    # ADR-0235 / PR-5: state is now an optional declared input — its
    # absence skips budget checks (preserves the v2 driver's fan-in
    # dispatch path). When present, it is passed through to downstream
    # typed ports (``act.envelope``, ``act.dispatch``, ``effect.execute``)
    # so the kernel does not need to reach into ``context.runtime``
    # again. The metadata-based smuggle path is closed.
    # ``tools`` 是 kernel-owned 端口（``_port_registry_seed_from_runtime_plane``
    # 注入的 per-turn ToolsService），用于解析每个 tool_call 的
    # ``required_grant``（ADR-0292 §10 P3 运行时授权检查）。
    declared_inputs: tuple[PortName, ...] = (
        PortName("decision"),
        PortName("state"),
        PortName("tools"),
    )
    # ADR-0237 / PR-1b: typed ``approval_required: bool`` port replaces
    # the previous ``decision.extra["needs_approval"]`` metadata grep.
    # Decision itself is a typed DTO; ``approval_required`` is computed
    # here so we don't widen Decision's contract for one consumer. The
    # only reader is ``act.approve.gate`` in the same subgraph.
    # ``grant_routing`` 是授权检查的路由信号：grant 缺失时输出
    # ``next_hint="grant_refused"``，外层 plan 据此路由到 terminal.commit。
    declared_outputs: tuple[PortName, ...] = (
        PortName("decision"),
        PortName("state"),
        PortName("approval_required"),
        PortName("approval_requirement"),
        PortName("grant_routing"),
    )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.authorize 入口。

        inputs 端口(yaml): decision (Decision), state (AgentState),
                            tools (ToolsService)
        outputs 端口(yaml): decision (Decision), state (AgentState),
                            approval_required (bool),
                            approval_requirement (ApprovalRequirement),
                            grant_routing (RoutingDecision)
        """
        del context
        decision = input.port_values.get(PortName("decision"))
        state = input.port_values.get(PortName("state"))
        tools = input.port_values.get(PortName("tools"))
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.authorize: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "act.authorize: 'state' port must be an AgentState or None, "
                f"got {type(state).__name__}"
            )

        # Budget check: refuse if any resource is exhausted.
        budget = getattr(state, "budget", None) if state is not None else None
        if budget is not None:
            if budget.exceeded("steps"):
                raise ValueError(
                    "act.authorize: budget step limit exceeded "
                    f"(used={budget.used_steps}, max={budget.max_steps})"
                )
            if budget.exceeded("tokens"):
                raise ValueError(
                    "act.authorize: budget token limit exceeded "
                    f"(used={budget.used_tokens}, max={budget.max_tokens})"
                )
            if budget.exceeded("cost_usd"):
                raise ValueError(
                    "act.authorize: budget cost limit exceeded "
                    f"(used={budget.used_cost_usd}, max={budget.max_cost_usd})"
                )

        # Constraint check: USE_TOOL tool_calls must have unique call_ids.
        if decision.action_type == "use_tool" and decision.tool_calls:
            call_ids = [call.call_id for call in decision.tool_calls]
            if len(call_ids) != len(set(call_ids)):
                duplicates = sorted({cid for cid in call_ids if call_ids.count(cid) > 1})
                raise ValueError(f"act.authorize: duplicate tool call_ids {duplicates}")

        # Safety boundary: USE_TOOL must not include self-destructive patterns
        # in the tool_name (deterministic local check; deeper policy lives in
        # the runtime capability seam).
        if decision.action_type == "use_tool":
            for call in decision.tool_calls:
                name = call.tool_name.strip().lower()
                if name.startswith(("self_destruct", "rm_rf_root")):
                    raise ValueError(
                        f"act.authorize: unsafe tool name rejected: {call.tool_name!r}"
                    )

        # ADR-0237 / PR-1b: typed ``approval_required`` and structured
        # ``approval_requirement``. We evaluate policies via ApprovalPolicyEngine
        # and project onto the subgraph ports.
        from lca.infrastructure.runtime_plane.access.approval_engine import (
            build_default_approval_engine,
        )
        from lca.infrastructure.runtime_plane.bindings.bindings import current_primary

        plane = getattr(state, "primary_plane", None) or current_primary()
        req = build_default_approval_engine().evaluate(decision.tool_calls, plane=plane)

        approval_required = bool(decision.needs_approval) or bool(req.required)

        # ADR-0292 §10 P3 运行时授权检查：对声明了 required_grant 的工具，
        # 要求该 grant 在 ambient TrustEnvelope 里。检查不读
        # decision.needs_approval，模型清掉自报授权也无法绕过。
        grant_routing = _grant_refusal_routing(decision, tools)

        return NodeOutput(
            port_values={
                PortName("decision"): decision,
                PortName("state"): state,
                PortName("approval_required"): approval_required,
                PortName("approval_requirement"): req,
                PortName("grant_routing"): grant_routing,
            }
        )


@plugin(
    id="phase.concept.act_subgraph.act_authorize",
    Config=None,
    provides=("act::act.authorize",),
    requires=(),
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
                "phase_concept_act_subgraph_act_authorize.checked",
                "phase_concept_act_subgraph_act_authorize.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = ActAuthorizeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActAuthorizeExecutor", "setup"]
