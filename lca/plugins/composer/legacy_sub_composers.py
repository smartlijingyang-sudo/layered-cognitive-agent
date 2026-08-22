"""PR-5a sub-composer plugins (ADR-0071 + ADR-0074 PR-5).

This module provides 4 sub-composers (BrainComposer + BodyComposer +
PerceiveComposer + TeamComposer) that wrap the existing factory calls
from spawn_agent / spawn_team. PR-5a 阶段把 spawn_agent 内联的装配
策略迁到这些 plugin 内，L4 spawn 不再直接 import 具体 plugin ID。

PR-5 验收（acceptance-criteria §3.1 L2 + tracker §PR-5）：

- ``grep "control.authorize\\|simple_body\\|default_factory" lca/layer4_app/``
  为 0 hit（PR-5 完成后）
- e2e 跑通 1 个标准 agent（golden profile）

PR-5a 阶段：sub-composers 实现 + boot 注册，但 spawn_agent 不迁移；
PR-5b 阶段：spawn_agent 改用 bind_plan 默认路径。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.enums import ActionScope
from lca.contracts.capabilities import (
    BODIES,
    STOP_RULES,
    STRATEGIES,
)
from lca.contracts.harness.composer import AgentGraph, TeamGraph
from lca.contracts.mechanisms.capability import require_capability


class BrainComposer:
    """PR-5a brain sub-composer。

    拼装 Brain（含 reasoner / critic / skill_router / decision_gate /
    agent_gates），对应 think 概念群。
    """

    key: str = "brain"

    def compose_agent(self, spec: Any, scope: Any) -> AgentGraph:
        from lca.layer4_app.spawn import _apply_lead_brain, _instrument_llm, _resolve_brain

        llm = _instrument_llm(spec.llm)
        brain = _resolve_brain(spec, spec.profile, llm, scope=scope)
        if getattr(spec, "decision_gate", None) is not None:
            brain = _apply_lead_brain(brain, decision_gate=spec.decision_gate)

        return AgentGraph(
            brain=brain,
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=llm,
            stop_rule=None,
            metadata={"composer_key": "brain"},
        )

    def compose_team(self, spec: Any, scope: Any) -> TeamGraph:
        raise NotImplementedError("BrainComposer.compose_team not implemented")


class BodyComposer:
    """PR-5a body sub-composer。

    拼装 Body（含 tool registry / safe executor / transport registry /
    action registry），对应 act 概念群。
    """

    key: str = "body"

    def compose_agent(self, spec: Any, scope: Any) -> AgentGraph:
        from lca.layer1_cognitive.body.action_catalog import (
            build_default_action_registry,
        )
        from lca.layer4_app.spawn import (
            _build_hooks,
            _fork_transport,
            _require_factory,
        )

        # tools.compose_service factory
        tools_factory = _require_factory(scope, "tools.compose_service")
        tool_registry = tools_factory()
        for tool in spec.tools:
            tool_registry.register(tool)

        safe_executor_cls = _require_factory(scope, "safe_executor.simple")
        safe_executor = safe_executor_cls(spec.profile.tool_permission_manifest)
        transport_registry = _fork_transport(
            require_capability(scope, "transport"),
            getattr(spec, "team_channel", None),
            scope,
        )
        action_scope = getattr(spec, "action_scope", None) or ActionScope.SOLO
        action_registry = build_default_action_registry(
            tool_registry,
            safe_executor,
            transport_registry,
            scope=action_scope,
        )
        body = require_capability(scope, BODIES.key).create(
            "simple",
            tool_registry=tool_registry,
            safe_executor=safe_executor,
            transport_registry=transport_registry,
            action_registry=action_registry,
        )
        hooks = _build_hooks(scope)
        return AgentGraph(
            brain=None,
            body=body,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=hooks,
            observability=None,
            llm=None,
            stop_rule=None,
            metadata={"composer_key": "body"},
        )

    def compose_team(self, spec: Any, scope: Any) -> TeamGraph:
        raise NotImplementedError("BodyComposer.compose_team not implemented")


class PerceiveComposer:
    """PR-5a perceive sub-composer。

    拼装 PerceiveHub + Memory + StateStore + Observability，对应 perceive
    概念群。
    """

    key: str = "perceive"

    def compose_agent(self, spec: Any, scope: Any) -> AgentGraph:
        from lca.contracts.capabilities import (
            MEMORY,
            OBSERVABILITY,
            STATE_STORE,
        )
        from lca.contracts.mechanisms.capability import (
            MissingCapabilityError,
            require_capability,
        )
        from lca.harness.observability import make_minimal_bound
        from lca.layer4_app.spawn import _resolve_memory, _resolve_state_store, build_perceive_hub

        # observability
        if isinstance(getattr(spec, "observability", None), str):
            try:
                hub = require_capability(scope, OBSERVABILITY.key)
            except MissingCapabilityError:
                hub = make_minimal_bound()
        elif getattr(spec, "observability", None) is not None:
            hub = spec.observability
        else:
            hub = make_minimal_bound()

        memory = _resolve_memory(
            getattr(spec, "memory", None),
            getattr(spec, "shared_store", None),
            require_capability(scope, MEMORY.key),
        )
        state_store = _resolve_state_store(
            getattr(spec, "state_store", None),
            require_capability(scope, STATE_STORE.key),
        )
        perceive_hub = build_perceive_hub(
            memory,
            hub=hub,
            scope=scope,
            action_scope=getattr(spec, "action_scope", None),
        )
        stop_rule = require_capability(scope, STOP_RULES.key).create("default")
        return AgentGraph(
            brain=None,
            body=None,
            memory=memory,
            state_store=state_store,
            perceive_hub=perceive_hub,
            hooks=None,
            observability=hub,
            llm=None,
            stop_rule=stop_rule,
            metadata={"composer_key": "perceive"},
        )

    def compose_team(self, spec: Any, scope: Any) -> TeamGraph:
        raise NotImplementedError("PerceiveComposer.compose_team not implemented")


class TeamComposer:
    """PR-5b team sub-composer（stub）。"""

    key: str = "team"

    def compose_agent(self, spec: Any, scope: Any) -> AgentGraph:
        raise NotImplementedError("TeamComposer.compose_agent — teams have no single agent")

    def compose_team(self, spec: Any, scope: Any) -> TeamGraph:
        from lca.contracts.models.team.role_team import TeamAssembly
        from lca.contracts.protocols.spec import LeadSpec
        from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
        from lca.layer4_app.spawn import (
            _build_stage,
            _resolve_team_observability,
            spawn_lead,
            spawn_member,
        )

        observability = _resolve_team_observability(spec)
        shared_store = (
            TeamSharedMemoryStore(list(spec.shared_memory_layers))
            if spec.shared_memory_layers
            else None
        )
        members = tuple(
            spawn_member(
                member_spec,
                shared_store=shared_store,
                observability=observability,
                scope=scope,
            )
            for member_spec in spec.members
        )
        stage, transport = _build_stage(members)
        governance = spec.governance
        lead = None
        if isinstance(governance, LeadSpec):
            lead = spawn_lead(
                governance.agent,
                transport=transport,
                mandate=governance.mandate,
                observability=observability,
                scope=scope,
            )
        assembly = TeamAssembly(
            governance=governance,
            stage=stage,
            lead=lead,
            delegate_max_attempts=spec.delegate_max_attempts,
        )
        strategy_key = _governance_strategy_key(governance)
        strategy = require_capability(scope, STRATEGIES.key).create(strategy_key, assembly)
        return TeamGraph(
            members=members,
            strategy=strategy,
            stage=stage,
            transport=transport,
            observability=observability,
            metadata={"composer_key": "team", "lead": lead},
        )


def _governance_strategy_key(governance: Any) -> str:
    """Helper: derive strategy registry key from governance."""
    from lca.contracts.protocols.spec import strategy_key_for_governance

    return strategy_key_for_governance(governance)


__all__ = [
    "BodyComposer",
    "BrainComposer",
    "PerceiveComposer",
    "TeamComposer",
]
