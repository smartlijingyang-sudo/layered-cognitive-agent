"""phase.perceive.observe — primitive node: invoke PerceiveHub, emit raw manifest.

ADR-0221: this is the lowest-level node in the perceive subgraph. It
calls the profile-selected ``perceive_hub`` capability and emits a
typed ``manifest`` port. The next node (``phase.perceive.fold``)
collapses the manifest into the closed ``observation`` shape.

ADR-0246 PR-7: when the runtime carries ``assistant_bootstrap`` +
``assistant_id``, the node merges the per-assistant Home projection
(SOUL/USER/AGENTS + goals.yaml) into the manifest, replacing any global
``workspace_instructions`` items so the assistant Home is the only
producer of that kind.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from lca.cognition.memory.daytime import record_task_episode
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
from lca.contracts.models.core.perceive.perception import ContextManifest
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
from lca.contracts.protocols.think.cognition import PerceiveHub
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveObserveExecutor:
    """Primitive: invoke the PerceiveHub capability; emit raw ``manifest``."""

    semantic_name: str = "phase.perceive.observe"
    region: str = "perceive"
    declared_inputs: tuple[PortName, ...] = (PortName("state"),)
    declared_outputs: tuple[PortName, ...] = (PortName("manifest"),)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        # Tool turns often stop before reflect. The utterance is already here.
        state = input.port_values.get(PortName("state"))
        if state is None and hasattr(runtime, "get"):
            state = runtime.get("agent_state")
        record_task_episode(runtime, state)
        hub = getattr(runtime, "perceive_hub", None)
        if hub is None and hasattr(runtime, "get"):
            hub = runtime.get("perceive_hub")
        routing = RoutingDecision(action_type=ActionType.RESPOND)
        if not isinstance(hub, PerceiveHub):
            return NodeOutput(port_values={PortName("manifest"): None, PortName("routing"): routing})
        manifest = await hub.perceive(state)  # type: ignore[arg-type]
        merged = await self._merge_assistant_bootstrap(runtime, manifest)
        return NodeOutput(port_values={PortName("manifest"): merged, PortName("routing"): routing})

    @staticmethod
    async def _merge_assistant_bootstrap(runtime: object, manifest: object) -> object:
        """合并 per-assistant bootstrap 投影；任何失败保持原 manifest。"""
        if not isinstance(manifest, ContextManifest):
            return manifest
        runtime_get = getattr(runtime, "get", None)
        bootstrap: Any = getattr(runtime, "assistant_bootstrap", None)
        if bootstrap is None and callable(runtime_get):
            bootstrap = runtime_get("assistant_bootstrap")
        assistant_id = getattr(runtime, "assistant_id", None)
        if assistant_id is None and callable(runtime_get):
            assistant_id = runtime_get("assistant_id")
        if bootstrap is None or not str(assistant_id or "").strip():
            return manifest
        project: Any = getattr(bootstrap, "project", None)
        if not callable(project):
            return manifest
        try:
            projection = project(str(assistant_id))
            bootstrap_manifest = getattr(projection, "manifest", None)
            projection_items: Any = getattr(projection, "items", None)
            if isinstance(bootstrap_manifest, ContextManifest):
                items: tuple[object, ...] = bootstrap_manifest.items
            elif callable(projection_items):
                raw_items: Any = projection_items()
                items = tuple(raw_items)
            else:
                items = ()
        except Exception:
            # 投影失败不阻塞感知主流程（fail-soft）。
            return manifest
        # 助理 Home 是 workspace_instructions 唯一生产者：移除全局 sensor 条目。
        hub_items = tuple(item for item in manifest.items if item.kind != "workspace_instructions")
        return replace(manifest, items=hub_items + tuple(items))


@plugin(
    id="phase.perceive.observe",
    provides=("perceive::phase.perceive.observe",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/perceive/test_observe_records_task_episode.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_perceive_observe.checked", "phase_perceive_observe.served")
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
    ctx.provide("perceive::phase.perceive.observe", PerceiveObserveExecutor())


__all__ = ["PerceiveObserveExecutor", "setup"]
