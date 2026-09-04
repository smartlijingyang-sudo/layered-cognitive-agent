"""Named Capability keys — contracts-layer primitive for plugin interaction.

Stable serialization value is the readable ``key`` string (YAML / logs / CLI).
Plugins declare ``provides`` / ``requires`` against these keys; they must not
couple via concrete classes or module singletons.

The full set of named capabilities is enumerated below as Python constants for
type-safe imports (``from lca.contracts.capabilities import LLM``). A
``CAPABILITIES_BY_KEY`` index is auto-derived at module load so callers can
also resolve by string key in O(1) without a hand-maintained parallel list.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

T = TypeVar("T")

Cardinality = Literal["one", "factory", "registry"]


@dataclass(frozen=True, slots=True)
class Capability(Generic[T]):
    """Typed capability slot. Equality and hashing are by ``key`` only."""

    key: str
    protocol: type[T] | None = None
    cardinality: Cardinality = "one"

    def __str__(self) -> str:
        return self.key

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Capability):
            return self.key == other.key
        if isinstance(other, str):
            return self.key == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.key)


def cap_key(value: Capability[object] | str) -> str:
    """Normalize a Capability or raw string to its stable key."""
    return value.key if isinstance(value, Capability) else value


# ── Seam / Definition services (Tier-1) ──────────────────────────────

LLM = Capability[object]("llm", cardinality="registry")
TOOLS = Capability[object]("tools", cardinality="registry")
TRANSPORT = Capability[object]("transport", cardinality="registry")
SKILLS = Capability[object]("skills", cardinality="registry")
FILE_STORE = Capability[object]("file_store", cardinality="registry")
OBSERVABILITY = Capability[object]("observability", cardinality="registry")
PHASE_OBSERVER = Capability[object]("phase_observer", cardinality="one")
"""Profile-selected read-only observer for declarative phase execution."""
PHASE_OBSERVER_REGISTRY = Capability[object]("phase_observer_registry", cardinality="one")
"""Neutral boot-time registry for independently contributed phase observers."""
COGNITIVE_THINK_PIPELINE = Capability[object]("cognitive.think_pipeline", cardinality="one")
"""Profile-selected L1 primitive that orchestrates the Think subflow."""
COGNITIVE_REFLECTION_PIPELINE = Capability[object](
    "cognitive.reflection_pipeline", cardinality="one"
)
"""Profile-selected L1 primitive that orchestrates the Reflect subflow."""
RUNTIME_LIFECYCLE_PUBLISHER = Capability[object]("runtime_lifecycle_publisher", cardinality="one")
"""Profile-selected passive publisher for Agent Loop boundary events."""
RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY = Capability[object](
    "runtime_lifecycle_subscriber_registry", cardinality="one"
)
"""Neutral boot-time registry for independently contributed lifecycle subscribers."""
EFFECT_DISPATCHER_FACTORY = Capability[object]("effect_dispatcher_factory", cardinality="one")
"""Profile-selected factory for policy-governed declarative effect execution."""
DELTA_REDUCER_FACTORY = Capability[object]("delta_reducer_factory", cardinality="one")
"""Profile-selected factory for the declared-delta single-writer adapter."""
DECLARATIVE_INTERPRETER_FACTORY = Capability[object](
    "declarative_interpreter_factory", cardinality="one"
)
"""Profile-selected factory that creates the declarative phase-graph interpreter."""
RUNTIME_JOURNAL_FACTORY = Capability[object]("runtime_journal_factory", cardinality="one")
"""Profile-selected factory that creates an isolated journal for each runtime turn."""
CHECKPOINT_STATE_RESOLVER_FACTORY = Capability[object](
    "checkpoint_state_resolver_factory", cardinality="one"
)
"""Profile-selected factory that restores durable checkpoints into AgentState."""
RESULT_FINALIZER_FACTORY = Capability[object]("result_finalizer_factory", cardinality="one")
"""Profile-selected factory that folds terminal outcomes into carrier results."""
RUNTIME_FACTORY = Capability[object]("runtime_factory", cardinality="one")
"""Profile-selected factory that constructs the concrete Agent Loop runtime."""
LOOP_GUARD_EVALUATOR = Capability[object]("loop_guard_evaluator", cardinality="one")
"""Profile-selected pure policy that governs declarative phase-graph loop re-entry."""
SESSION_PERSISTENCE_FACTORY = Capability[object]("session_persistence_factory", cardinality="one")
"""Profile-selected factory that creates durable Session fact-stream backends."""
SESSION_PROJECTION_REGISTRY_FACTORY = Capability[object](
    "session_projection_registry_factory", cardinality="one"
)
"""Profile-selected factory for Session projection storage and default views."""
SESSION_LIVE_BUILDER = Capability[object]("session_live_builder", cardinality="one")
"""Profile-selected callable that creates one live owner agent for a durable Session."""
SESSION_TURN_CONTROLLER_FACTORY = Capability[object](
    "session_turn_controller_factory", cardinality="one"
)
"""Profile-selected factory that owns one in-flight Agent turn per durable Session."""
SESSION_FOLLOWUP_POLICY = Capability[object]("session_followup_policy", cardinality="one")
"""Profile-selected pure policy for concurrent user follow-up admission."""
SESSION_COMMAND_LEDGER = Capability[object]("session_command_ledger", cardinality="one")
"""Profile-selected event-sourced policy for durable Session command idempotency."""
TOOL_BATCH_EXECUTION_POLICY = Capability[object]("tool_batch_execution_policy", cardinality="one")
"""Profile-selected strategy for parallel or ordered model-emitted tool batches."""
CONTINUOUS_CONTROL_PLANE_FACTORY = Capability[object](
    "continuous_control_plane_factory", cardinality="one"
)
"""Profile-selected factory for durable trigger ingestion, work leasing and Session dispatch."""
SANDBOX = Capability[object]("sandbox", cardinality="registry")
MEMORY = Capability[object]("memory", cardinality="registry")
SEARCH = Capability[object]("search", cardinality="registry")
STATE_STORE = Capability[object]("state_store", cardinality="registry")
EVENT_DESCRIPTOR_REGISTRY = Capability[object]("event_descriptor_registry", cardinality="one")
"""单一事件描述符注册中心（ADR-0063 PR-7 source inversion）。"""

# ── ADR-0065 PR-2: Evidence plane ──────────────────────────────────

EVIDENCE_STORE = Capability[object]("evidence_store", cardinality="one")
"""受治理的证据后端契约(L5 / L8)。"""

EVIDENCE_POLICY = Capability[object]("evidence_policy", cardinality="one")
"""载荷分类 / 保留 / 内联决策(L5 / L8)。"""

RUN_LOCATOR = Capability[object]("run_locator", cardinality="one")
"""run_id → 物理路径解析(ADR-0065 §七 / PR-5)。"""

RUN_LEDGER_FACTORY = Capability[object]("run_ledger_factory", cardinality="factory")
"""RunLedgerHandle 创建入口(0065 PR-5);每个 run 一份。"""

W3C_TRACE_CONTEXT_VALIDATOR = Capability[object]("w3c_trace_context_validator", cardinality="one")
"""W3C traceparent / tracestate 入站不可信校验(ADR-0065 §八 / PR-7)。"""

CODING_AGENT_TRACE_INSPECTOR = Capability[object]("coding_agent_trace_inspector", cardinality="one")
"""Coding Agent TraceInspectorTool(0065 §六 / PR-8)。"""

CODING_AGENT_FAILURE_EXPLAINER = Capability[object](
    "coding_agent_failure_explainer", cardinality="one"
)
CODING_AGENT_OPTIMIZATION_FINDER = Capability[object](
    "coding_agent_optimization_finder", cardinality="one"
)
CODING_AGENT_PLUGIN_GRAPH_RENDERER = Capability[object](
    "coding_agent_plugin_graph_renderer", cardinality="one"
)
CODING_AGENT_MINIMAL_REPRODUCTION = Capability[object](
    "coding_agent_minimal_reproduction", cardinality="one"
)
CODING_AGENT_DIFF_CONTEXT = Capability[object]("coding_agent_diff_context", cardinality="one")
CODING_AGENT_RUN_DIFF = Capability[object]("coding_agent_run_diff", cardinality="one")

TRACE_INSPECTOR_TOOLS = Capability[object]("trace_inspector_tools", cardinality="registry")
"""TraceInspector 5 个方法各自作为工具注册（ADR-0063 PR-9）。"""

CLI_DEBUG_COMMAND = Capability[object]("cli_debug_command", cardinality="registry")
"""lca-ops debug <name> 的子命令注册（ADR-0063 PR-9）。"""

GENAI_SEMANTIC_MAPPER = Capability[object]("genai_semantic_mapper", cardinality="registry")
"""OTel GenAI 语义映射器（ADR-0063 PR-10）。"""

OBSERVABILITY_SCORER = Capability[object]("observability_scorer", cardinality="registry")
"""Langfuse / OTel 评估 scorer 注册（ADR-0063 PR-10）。"""

# ── Group services (ADR-0056) ────────────────────────────────────────

PERCEIVE = Capability[object]("perceive", cardinality="one")
GATES = Capability[object]("gates", cardinality="one")

# ── Multi-impl registry seams (ADR-0062 §3 / PR-3) ───────────────────

BODIES = Capability[object]("bodies", cardinality="registry")
BRAINS = Capability[object]("brains", cardinality="registry")
HOOKS = Capability[object]("hooks", cardinality="registry")
RESUME_INPUT_ADAPTERS = Capability[object]("resume_input_adapters", cardinality="registry")
"""恢复输入适配器注册表；每个 Agent 通过声明式键选择其暂停恢复语义。"""
STRATEGIES = Capability[object]("team_strategies", cardinality="registry")
GRAPH_NODE_EXECUTORS = Capability[object]("graph_node_executors", cardinality="one")
"""Profile-selected registry of concrete collaboration graph node primitives."""
DRIVERS = Capability[object]("run_loop_driver_registry", cardinality="registry")
COMPONENT_REGISTRY = Capability[object]("component_registry", cardinality="one")
LEAD_BUDGET_POLICY_RESOLVER = Capability[object]("lead_budget_policy_resolver", cardinality="one")
"""Profile-owned Lead budget-policy selection seam for plan-bound Agent assembly."""
ACTION_HANDLERS = Capability[object]("action_handler_registry", cardinality="one")
"""ADR-0074: ActionHandlerRegistry seam — BodyComposer consumes from scope."""

# ── ADR-0076 §五 + §六: Organization-plane seams ─────────────────────

TEAM_SEAM = Capability[object]("team_seam", cardinality="one")
"""ADR-0076 §五: TeamSharedMemoryStore / TeamTransport / MemberInvoker seam.

TeamComposer consumes the team backend set through this capability; direct
construction of ``TeamSharedMemoryStore(...)`` / ``TransportMemberInvoker(...)``
inside the composer is forbidden by the substitution gate.
"""

TEAM_COMMUNICATION = Capability[object]("team_communication", cardinality="one")
"""Profile-selected Team transport and member-invocation pair.

``team_seam`` consumes this collaborator after member assembly.  A profile may
replace the communication assembler without changing ``TeamComposer`` or the
Team seam factory's assembly order.
"""

TEAM_SHARED_MEMORY_RESOLVER = Capability[object]("team_shared_memory_resolver", cardinality="one")
"""Profile-selected Team shared-memory resolver.

``team_seam`` consumes this collaborator before member assembly.  A profile may
replace shared-memory ownership without changing ``TeamComposer`` or the
communication assembler selected for the same Team.
"""

TEAM_ROLE_LIBRARY = Capability[object]("team_role_library", cardinality="one")
"""Profile-selected catalog used to validate and materialize Team roles.

Team-mode adapters consume this capability instead of selecting a filesystem
catalog themselves, so a deployment may replace role ownership without changing
Gateway mode assembly.
"""

COMPOSITION_INVARIANT_CHECKER = Capability[object](
    "composition.invariant_checker", cardinality="one"
)
"""Profile-selected invariant checker used by CordisComposer mount operations."""

MEMORY_WRITE_POLICY = Capability[object]("memory.write_policy", cardinality="one")
"""Profile-selected admission policy for writes to a MemorySystem."""

MEMORY_COMPACTION_POLICY = Capability[object]("memory.compaction_policy", cardinality="one")
"""Profile-selected compaction policy for an assembled MemorySystem."""

MEMORY_RETRIEVAL_POLICY = Capability[object]("memory.retrieval_policy", cardinality="one")
"""Profile-selected retrieval policy factory for an assembled MemorySystem."""

REASONER_TEMPLATE_CATALOG = Capability[object]("reasoner_template_catalog", cardinality="one")
"""Profile-selected template collection consumed by PromptReasoner factories."""

PROMPT_ASSEMBLER = Capability[object]("prompt_assembler", cardinality="one")
"""Profile-selected cognitive prompt assembler (cognition L1)."""

PROMPT_TEMPLATE_SELECTOR = Capability[object]("prompt_template_selector", cardinality="one")
"""Profile-selected selector that picks the active PromptTemplate per AgentState."""

PROMPT_SECTION_REGISTRY = Capability[object]("prompt_section_registry", cardinality="one")
"""Closed registry collecting typed prompt section providers (kind+name keying)."""

PROMPT_TEMPLATE_PROVIDER = Capability[object]("prompt_template_provider", cardinality="one")
"""Profile-selected provider of compiled PromptTemplate catalog (built-ins + overrides)."""

TEAM_CASTING_PROMPT_RENDERER = Capability[object]("team_casting_prompt_renderer", cardinality="one")
"""Profile-selected renderer for LLM Team-casting prompts.

The Team caster consumes this service rather than loading a built-in prompt,
so content policy can be replaced independently of parsing and governance.
"""

TEAM_CASTER = Capability[object]("team_caster", cardinality="one")
"""Profile-selected policy that produces a validated Team casting plan.

Team-mode adapters consume this capability independently of the role catalog,
allowing a profile to replace casting policy without changing Gateway assembly.
"""

RUN_MODE_REGISTRY = Capability[object]("run_mode_registry", cardinality="one")
"""ADR-0076 §六: gateway run-mode adapter registry.

``gateway/modes.py`` must resolve modes through this registry; each mode
registers as a mode-adapter plugin (solo / team / cordis-creator / future
research / code / creator variants).  String ``if/elif`` branching on
mode keys is forbidden by the substitution gate.
"""

CORDIS_CREATOR_ROLE = Capability[object]("role.cordis_creator", cardinality="one")
"""Profile-selected Cordis Creator persona and its tool-permission manifest.

The Creator mode adapter consumes this capability instead of importing a
persona builder, so deployments can replace role policy through a bundle entry.
"""

CORDIS_CONTROL_TOOL_FACTORY = Capability[object](
    "cordis_control_tool_factory", cardinality="factory"
)
"""Profile-selected factory for a Composer-bound ``cordis_control`` tool.

The factory owns Creator-specific grants and Composer binding. Mode adapters
only request the factory and add its resulting protocol Tool to the role's
allowlisted tool set.
"""

LEARNING_SKILL_ACQUIRER = Capability[object]("learning.skill_acquirer", cardinality="one")
"""Evidence-gated, candidate-only procedural skill acquisition service."""

LEARNING_FAILURE_ANALYZER = Capability[object]("learning.failure_analyzer", cardinality="one")
"""Configured, read-only failure analysis service for completed runs."""

LEARNING_PROFILE_EVOLVER = Capability[object]("learning.profile_evolver", cardinality="one")
"""Held-out profile candidate evaluator that cannot apply or publish changes."""

LEARNING_REVIEW_TICKET_STORE = Capability[object]("learning.review_ticket_store", cardinality="one")
"""Profile-selected durable store for terminal learning-review tickets and lease state."""

LEARNING_REVIEW_SERVICE = Capability[object]("learning.review_service", cardinality="one")
"""Profile-owned terminal review ticket service with candidate-only assessment APIs."""

# ── ADR-0187 PR-2: Assistant domain capability keys ─────────────────────
#
# 薄 Catalog / 助理域 overlay / 进化 / 定时 job 各自独立 capability key；
# 禁止单类同时实现多个（arch test 守住 §6 删除条件「**无** God Catalog」）。
ASSISTANT_CATALOG = Capability[object]("assistant.catalog", cardinality="one")
"""薄 Catalog（Home CRUD + 配置面 revise/reimport + retire）；ADR-0187 §3 D4。"""

ASSISTANT_SKILL_OVERLAY = Capability[object]("assistant.skill_overlay", cardinality="one")
"""助理域 skill overlay（挂 0048 全局 store 之上的 per-assistant 索引）。"""

ASSISTANT_EVOLVE = Capability[object]("assistant.evolve", cardinality="one")
"""助理域 SkillAcquirer 实现（与 learning.skill_acquirer 平行但 capability 独立）。"""

ASSISTANT_JOBS = Capability[object]("assistant.jobs", cardinality="one")
"""JobSpec 收集器，向 continuous_control_plane_factory 注册 WorkItem；ADR-0093 复用。"""

ASSISTANT_BOOTSTRAP = Capability[object]("assistant.bootstrap", cardinality="one")
"""将配置面 SOUL/IDENTITY/USER/AGENTS 投影进 ContextManifest（ADR-0187 §3 D5 + PR-4）。

MEMORY.md / memory/ 不参与投影（I-A13）；只读 + 投影，不写文件。
"""

ASSISTANT_WORKSPACE = Capability[object]("assistant.workspace", cardinality="one")
"""绑定 cwd = home/workspace/ 到 ExecutionSpace 事实（ADR-0187 §3 D5 + PR-4）。

物化 ExecutionSpace dataclass，不直接世界写；ACL ⊆ home/workspace/（I-A5）。
"""

ASSISTANT_FRONTEND_BRIDGE = Capability[object]("assistant.frontend_bridge", cardinality="one")
"""助理 → 前端 agent 投影桥（ADR-0187 §3 D12 创建流 + D7 前端可见）。

把新建助理投影成 LobeHub agents 行（TRPC ``agent.createAgent``），
映射真值 = agents 行 ``agencyConfig.lcaAssistantId``。fail-soft：
注册失败返回 None，不阻断 catalog.create。
"""

ACT_EXECUTION_SPACE = Capability[object]("act.execution_space", cardinality="one")
"""G2 空间事实契约（PR-4）：assistant.workspace 物化的 ExecutionSpace dataclass 的入口。"""

# ── Named factories / drivers ───────────────────────────────────────

LLM_RESOLVER = Capability[object]("llm_resolver", cardinality="one")
SAFE_EXECUTOR_SIMPLE = Capability[object]("safe_executor.simple", cardinality="factory")
REASONER_PROMPT = Capability[object]("reasoner.prompt", cardinality="factory")
BRAIN_PROMPT_CATALOG_FACTORY = Capability[object](
    "brain_prompt_catalog_factory", cardinality="factory"
)
"""Profile-selected factory for the frozen tools and skills view consumed by a Brain."""
CRITIC_SIMPLE = Capability[object]("critic.simple", cardinality="factory")
JOURNAL_STORE = Capability[object]("journal_store", cardinality="factory")
TOOLS_COMPOSE_SERVICE = Capability[object]("tools.compose_service", cardinality="factory")
TRANSPORT_COMPOSE_SERVICE = Capability[object]("transport.compose_service", cardinality="factory")

# ── Creator (§13.3) capability keys ────────────────────────────────
#
# 单进程内「群 Composition」组装者的命名工厂。它不参与 AgentGraph/TeamGraph
# 的计划绑定，因此独立于 ``composer.*`` 图组合器 capability 命名空间；Tier-2
# provider 挂载 ``composition.compose_factory``，Tier-3 ``cordis_control`` 工具通过
# ``ctx.inject("composition.compose_factory")`` 取工厂。
COMPOSITION_COMPOSE_FACTORY = Capability[object](
    "composition.compose_factory", cardinality="factory"
)


# ── Auto-derived key → Capability index ───────────────────────────
#
# Single source of truth: every Capability constant declared above is
# auto-indexed by its ``key``. Adding a new capability stays a one-line edit;
# this index updates without a second maintenance step. ``cap_key`` callers
# can keep using string or Capability interchangeably.


def _build_capability_index() -> Mapping[str, Capability[object]]:
    seen: dict[str, Capability[object]] = {}
    for value in _MODULE_GLOBALS.values():
        if isinstance(value, Capability):
            existing = seen.get(value.key)
            if existing is not None and existing is not value:
                raise RuntimeError(
                    f"duplicate capability key {value.key!r} in lca.contracts.capabilities"
                )
            seen[value.key] = value
    return seen


_MODULE_GLOBALS: Mapping[str, object] = globals()
CAPABILITIES_BY_KEY: Mapping[str, Capability[object]] = _build_capability_index()


__all__ = [
    "CAPABILITIES_BY_KEY",
    "Capability",
    "Cardinality",
    "cap_key",
]
