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

# ── Group services (ADR-0056) ────────────────────────────────────────

PERCEIVE = Capability[object]("perceive", cardinality="one")
GATES = Capability[object]("gates", cardinality="one")

# ── Named factories / drivers ───────────────────────────────────────

LLM_RESOLVER = Capability[object]("llm_resolver", cardinality="one")
BRAIN_FACTORY = Capability[object]("brain_factory", cardinality="factory")
BODY_SIMPLE = Capability[object]("body.simple", cardinality="factory")
SAFE_EXECUTOR_SIMPLE = Capability[object]("safe_executor.simple", cardinality="factory")
STOP_RULE_DEFAULT = Capability[object]("stop_rule.default", cardinality="factory")
HOOK_REGISTRY_SIMPLE = Capability[object]("hook_registry.simple", cardinality="factory")
MIDDLEWARE_REGISTRY_MEMORY = Capability[object]("middleware_registry.memory", cardinality="factory")
REASONER_PROMPT = Capability[object]("reasoner.prompt", cardinality="factory")
CRITIC_SIMPLE = Capability[object]("critic.simple", cardinality="factory")
JOURNAL_STORE = Capability[object]("journal_store", cardinality="factory")
RUN_LOOP_DRIVER_REGISTRY = Capability[object]("run_loop_driver_registry", cardinality="one")
TOOLS_COMPOSE_SERVICE = Capability[object]("tools.compose_service", cardinality="factory")
TRANSPORT_COMPOSE_SERVICE = Capability[object]("transport.compose_service", cardinality="factory")
