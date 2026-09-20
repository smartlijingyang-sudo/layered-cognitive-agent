"""phase.perceive.memory_retrieve — declarative primitive: query and inject contextual memories.

ADR-0244: Retrieves semantic, episodic, and procedural memory context for the
current turn without hardcoded heuristics. Enriches the perceived manifest and
emits the typed ``memories`` port.
ADR-0246 PR-4: passes a textual ``query`` and a ``token_budget`` to the memory
system's ``retrieve`` so injection is budgeted and relevance-ranked, never a
full dump.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

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
from lca.contracts.models.core.conversation.memory import MemoryRecord
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# ADR-0246 PR-4: 默认记忆注入 token 预算（约 2000 token，字符级近似）。
_DEFAULT_MEMORY_TOKEN_BUDGET = 2000


def _query_from_manifest(manifest: object) -> str:
    """从 manifest 条目提取纯文本检索词；无文本时返回空串。"""
    if manifest is None:
        return ""
    parts: list[str] = []
    for item in getattr(manifest, "items", ()) or ():
        payload = getattr(item, "payload", None)
        if isinstance(payload, str):
            parts.append(payload)
        elif isinstance(payload, (list, tuple)):
            for p in payload:
                if isinstance(p, str):
                    parts.append(p)
                    break
    return " ".join(parts)[:500]


def _accepts_kwarg(func: object, name: str) -> bool:
    """判断 ``retrieve`` 是否接受可选关键字参数（兼容旧实现与测试 fake）。"""
    try:
        sig = inspect.signature(func)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return name in sig.parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )


@dataclass(frozen=True, slots=True)
class PerceiveMemoryRetrieveExecutor:
    """Primitive: query memory provider / session store, emit memories and manifest."""

    semantic_name: str = "phase.perceive.memory_retrieve"
    region: str = "perceive"
    declared_inputs: tuple[PortName, ...] = ("manifest",)
    declared_outputs: tuple[PortName, ...] = ("manifest", "memories", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        manifest = input.port_values.get("manifest")
        # Canonical capability is the composed MemorySystem under ``memory``
        # (ADR-0244 D4). ``memory_provider`` remains a test-only fallback.
        memory = getattr(runtime, "memory", None)
        if memory is None and hasattr(runtime, "get"):
            memory = runtime.get("memory")
        if memory is None:
            memory = getattr(runtime, "memory_provider", None)
            if memory is None and hasattr(runtime, "get"):
                memory = runtime.get("memory_provider")

        memories: list[MemoryRecord] = []
        if memory is not None and hasattr(memory, "retrieve"):
            try:
                retrieve = memory.retrieve
                kwargs: dict[str, Any] = {}
                query = _query_from_manifest(manifest)
                if _accepts_kwarg(retrieve, "query"):
                    kwargs["query"] = query
                if _accepts_kwarg(retrieve, "token_budget"):
                    kwargs["token_budget"] = _DEFAULT_MEMORY_TOKEN_BUDGET
                retrieved = await retrieve(manifest=manifest, **kwargs)
                if isinstance(retrieved, (list, tuple)):
                    memories.extend(retrieved)
            except Exception:
                # Memory retrieval is best-effort: empty result must not
                # block the cognitive main flow (ADR-0244).
                memories = []

        routing = RoutingDecision(action_type=ActionType.RESPOND)
        return NodeOutput(
            port_values={
                "manifest": manifest,
                "memories": tuple(memories),
                "routing": routing,
            }
        )


@plugin(
    id="phase.perceive.memory_retrieve",
    provides=("perceive::phase.perceive.memory_retrieve",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/integration/test_memory_and_procedural_distillation.py",
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
                "phase_perceive_memory_retrieve.checked",
                "phase_perceive_memory_retrieve.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    del config
    ctx.provide("perceive::phase.perceive.memory_retrieve", PerceiveMemoryRetrieveExecutor())


__all__ = ["PerceiveMemoryRetrieveExecutor", "setup"]
