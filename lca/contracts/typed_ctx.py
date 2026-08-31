"""Typed accessor for cordis Context — Protocol-only references.

Each property corresponds to a Tier-1 Definition's `provide` key. cordis's
ReflectService resolves attribute reads through this typing, so:
- `ctx.llm` is type-checked (mypy knows returns LLMAdapter)
- `ctx.inject("llm")` is still valid (untyped fallback)

Constraint: this module is in `lca.contracts/`, which is FORBIDDEN by
importlinter from importing `lca.infrastructure` / `lca.harness` / `lca.plugins`.
Therefore TypedContext references ONLY Protocol types already declared in
`lca/contracts/protocols/`. Concrete service classes (`LlmService`,
`ToolsService`, `CommandGateway`, etc.) are not imported here.
"""

from __future__ import annotations

from typing import Protocol

from lca.contracts.protocols.journal.observability import ObservabilityBackend
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.contracts.protocols.memory.operational_skills import SkillPackageInstaller
from lca.contracts.protocols.runtime.infra import (
    AgentTransport,
    AttachmentIdentity,
    LLMAdapter,
    Sandbox,
    StateStore,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.runtime.runtime import Runtime
from lca.contracts.protocols.think.cognition import Brain, BrainFactory


class TypedContext(Protocol):
    """Typed property accessor for cordis Context.

    All property types are Protocol declarations from `lca.contracts.protocols`.
    Concrete classes (LlmService / ToolsService / etc.) satisfy these
    Protocols structurally — no inheritance required.
    """

    @property
    def llm(self) -> LLMAdapter: ...

    @property
    def tools(self) -> ToolRegistry: ...

    @property
    def transport(self) -> TransportRegistryProtocol: ...

    @property
    def memory(self) -> MemorySystem: ...

    @property
    def state_store(self) -> StateStore: ...

    @property
    def skills(self) -> SkillPackageInstaller: ...

    @property
    def observability(self) -> ObservabilityBackend: ...

    @property
    def sandbox(self) -> Sandbox: ...

    @property
    def attachment(self) -> AttachmentIdentity: ...

    @property
    def brain(self) -> Brain: ...

    @property
    def brain_factory(self) -> BrainFactory: ...

    @property
    def runtime(self) -> Runtime: ...

    @property
    def agent_transport(self) -> AgentTransport: ...
