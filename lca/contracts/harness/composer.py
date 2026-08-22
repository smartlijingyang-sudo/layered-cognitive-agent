"""Composer Protocol + AgentGraph / TeamGraph（ADR-0071 + ADR-0074 PR-5）。

ADR-0071 Composer-per-Cluster：把 ``spawn_agent`` 内联的装配策略
（BrainFactory / Body / PerceiveHub / Team）抽出到 4 个 sub-composer plugin，
L4 spawn 只保留「绑定 plan + 上下文 + 编排图」的角色。

字段：

- ``Composer`` Protocol — ``key: ClassVar[str]`` + ``compose_agent`` /
  ``compose_team`` 两个方法
- ``AgentGraph`` — frozen dataclass；持有 Brain / Body / PerceiveHub /
  Hooks / Observability / LLMAdapter 等封闭对象图
- ``TeamGraph`` — frozen dataclass；持有 members + strategy + stage +
  transport + observability

PR-5 落地（tracke §PR-5）：
1. Composer Protocol + AgentGraph / TeamGraph（本文件）
2. BrainComposer + BodyComposer + PerceiveComposer + TeamComposer
   plugins (lca/plugins/composer/) —— PR-5a
3. spawn_agent 接受 compiled_plan 参数；RuntimeDeps 用 compiled_plan
   替换散落 factory 字段；L4 不再 import 具体插件 ID

PR-5 验收（acceptance-criteria §3.1 L2 + tracker §PR-5）：

- ``grep "control.authorize\\|simple_body\\|default_factory" lca/layer4_app/``
  为 0 hit
- e2e 跑通 1 个标准 agent（golden profile）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    # Protocols 仅类型层使用，避免 lca/contracts/protocols 在
    # lca/contracts/harness/__init__.py 加载时触发循环 import。
    from lca.contracts.protocols import (
        AgentTransport,
        Body,
        Brain,
        HookRegistry,
        LLMAdapter,
        MemorySystem,
        PerceiveHub,
        StateStore,
        StopRule,
    )


# ── Graph containers ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AgentGraph:
    """单 agent 封闭对象图（ADR-0071 + PR-5）。

    持有 ``spawn_agent`` 构造的 Brain / Body / Memory / StateStore /
    PerceiveHub / Hooks / Observability / LLM 等所有依赖。frozen dataclass
    确保 runtime 期间不变；可作为 plan_ref × Journal 绑定时的状态快照。
    """

    brain: Brain
    body: Body
    memory: MemorySystem
    state_store: StateStore
    perceive_hub: PerceiveHub
    hooks: HookRegistry
    observability: Any  # BoundObservability (avoid hard import cycle)
    llm: LLMAdapter
    stop_rule: StopRule
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TeamGraph:
    """Team 封闭对象图（ADR-0071 + PR-5）。

    持有 ``spawn_team`` 构造的所有依赖：members / strategy / stage /
    transport / observability。
    """

    members: tuple[Any, ...]  # tuple[CognitiveAgent, ...]（避免硬 import）
    strategy: Any
    stage: Any
    transport: AgentTransport | None
    observability: Any
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Module-level accessors (ADR-0015) ──────────────────────────────────


def agent_graph_has_brain(graph: AgentGraph) -> bool:
    """``AgentGraph.brain`` is not None."""
    return graph.brain is not None


def agent_graph_has_body(graph: AgentGraph) -> bool:
    """``AgentGraph.body`` is not None."""
    return graph.body is not None


def team_graph_member_count(graph: TeamGraph) -> int:
    """TeamGraph.members 长度。"""
    return len(graph.members)


# ── Composer Protocol ────────────────────────────────────────────────


@runtime_checkable
class Composer(Protocol):
    """Sub-composer Protocol（ADR-0071）。

    每个 sub-composer 对应一个认知概念群：

    - ``BrainComposer`` — think 概念群（BrainFactory + lead 构造模板）
    - ``BodyComposer`` — act 概念群（tool registry / safe executor /
      action registry / transport registry）
    - ``PerceiveComposer`` — perceive 概念群（perceive hub 装配）
    - ``TeamComposer`` — collaboration 概念群（member / strategy /
      stage / transport 编排）

    每个 sub-composer 是 cordis plugin，boot 时通过
    ``ctx.provide(f"composer.{key}", BrainComposer())`` 注入。
    spawn_agent 通过 ``require_capability(scope, f"composer.{key}")`` 解析。
    """

    key: ClassVar[str]

    def compose_agent(self, spec: Any, scope: Any) -> AgentGraph:
        """Construct agent graph for one ``AgentSpec``.

        ``spec`` 是 ``AgentSpec``；``scope`` 是 booted cordis Context。
        返回 frozen ``AgentGraph``。
        """
        ...

    def compose_team(self, spec: Any, scope: Any) -> TeamGraph:
        """Construct team graph for one ``TeamSpec``.

        ``spec`` 是 ``TeamSpec``；``scope`` 是 booted cordis Context。
        返回 frozen ``TeamGraph``。
        """
        ...


# ── Module-level helpers (ADR-0015) ──────────────────────────────────


def merge_agent_graphs(*graphs: AgentGraph) -> AgentGraph:
    """Merge partial ``AgentGraph`` values without discarding prior fields.

    Sub-composers each own a disjoint part of the graph.  A ``None`` field is
    therefore absence of a contribution, not an instruction to clear a
    dependency supplied by an earlier composer.  When more than one composer
    supplies a non-null value for the same field, the later composer wins.
    """
    if not graphs:
        raise ValueError("merge_agent_graphs requires at least one graph")
    merged = graphs[0]
    for graph in graphs[1:]:
        merged = AgentGraph(
            brain=graph.brain if graph.brain is not None else merged.brain,
            body=graph.body if graph.body is not None else merged.body,
            memory=graph.memory if graph.memory is not None else merged.memory,
            state_store=graph.state_store if graph.state_store is not None else merged.state_store,
            perceive_hub=(
                graph.perceive_hub if graph.perceive_hub is not None else merged.perceive_hub
            ),
            hooks=graph.hooks if graph.hooks is not None else merged.hooks,
            observability=(
                graph.observability if graph.observability is not None else merged.observability
            ),
            llm=graph.llm if graph.llm is not None else merged.llm,
            stop_rule=graph.stop_rule if graph.stop_rule is not None else merged.stop_rule,
            metadata={**merged.metadata, **graph.metadata},
        )
    return merged


__all__ = [
    "AgentGraph",
    "Composer",
    "TeamGraph",
    "agent_graph_has_body",
    "agent_graph_has_brain",
    "merge_agent_graphs",
    "team_graph_member_count",
]
