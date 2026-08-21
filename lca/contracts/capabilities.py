"""Named Capability keys — contracts-layer primitive for plugin interaction.

Stable serialization value is the readable ``key`` string (YAML / logs / CLI).
Plugins declare ``provides`` / ``requires`` against these keys; they must not
couple via concrete classes or module singletons.
"""

from __future__ import annotations

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
SANDBOX = Capability[object]("sandbox", cardinality="registry")
MEMORY = Capability[object]("memory", cardinality="registry")
SEARCH = Capability[object]("search", cardinality="registry")
STATE_STORE = Capability[object]("state_store", cardinality="registry")
EVENT_DESCRIPTOR_REGISTRY = Capability[object]("event_descriptor_registry", cardinality="one")
"""单一事件描述符注册中心（ADR-0063 PR-7 source inversion）。"""

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
STOP_RULES = Capability[object]("stop_rules", cardinality="registry")
HOOKS = Capability[object]("hooks", cardinality="registry")
STRATEGIES = Capability[object]("team_strategies", cardinality="registry")
DRIVERS = Capability[object]("run_loop_driver_registry", cardinality="registry")
COMPONENT_REGISTRY = Capability[object]("component_registry", cardinality="one")

# ── Named factories / drivers ───────────────────────────────────────

LLM_RESOLVER = Capability[object]("llm_resolver", cardinality="one")
SAFE_EXECUTOR_SIMPLE = Capability[object]("safe_executor.simple", cardinality="factory")
MIDDLEWARE_REGISTRY_MEMORY = Capability[object]("middleware_registry.memory", cardinality="factory")
REASONER_PROMPT = Capability[object]("reasoner.prompt", cardinality="factory")
CRITIC_SIMPLE = Capability[object]("critic.simple", cardinality="factory")
JOURNAL_STORE = Capability[object]("journal_store", cardinality="factory")
RUN_LOOP_DRIVER_REGISTRY = DRIVERS
TOOLS_COMPOSE_SERVICE = Capability[object]("tools.compose_service", cardinality="factory")
TRANSPORT_COMPOSE_SERVICE = Capability[object]("transport.compose_service", cardinality="factory")

# ── Creator (§13.3) capability keys ────────────────────────────────
#
# 单进程内「群 Composition」组装者的命名工厂；Tier-2 provider 把 ``CordisComposer``
# 工厂挂到 ``composer.compose_factory``，Tier-3 tool ``cordis_control`` 通过
# ``ctx.inject("composer.compose_factory")`` 取工厂。
COMPOSER_COMPOSE_FACTORY = Capability[object](
    "composer.compose_factory", cardinality="factory"
)
