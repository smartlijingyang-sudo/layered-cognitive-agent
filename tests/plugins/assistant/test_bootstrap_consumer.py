"""PR-7（ADR-0246）：``phase.perceive.observe`` 消费 assistant.bootstrap 投影。"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.perceive.observe.observe import PerceiveObserveExecutor


class _FakeHub:
    def __init__(self, manifest: ContextManifest) -> None:
        self._manifest = manifest

    async def perceive(self, state: object) -> ContextManifest:
        del state
        return self._manifest


class _FakeBootstrap:
    def __init__(self, assistant_id: str) -> None:
        self._assistant_id = assistant_id

    def project(self, assistant_id: str) -> object:
        assert assistant_id == self._assistant_id
        return _Projection(assistant_id)


class _Projection:
    def __init__(self, assistant_id: str) -> None:
        self.manifest = ContextManifest(
            items=(
                ContextItem(
                    kind="workspace_instructions",
                    payload={"name": "AGENTS.md", "text": "# 助理约定"},
                    provenance=f"assistant.bootstrap.{assistant_id}",
                    extra={"assistant_id": assistant_id},
                    content_class="instruction",
                ),
                ContextItem(
                    kind="workspace_artifacts",
                    payload={"name": "goals.yaml", "goals": []},
                    provenance=f"assistant.bootstrap.{assistant_id}",
                    extra={"assistant_id": assistant_id},
                    content_class="data",
                ),
            )
        )

    def items(self) -> tuple[ContextItem, ...]:
        return self.manifest.items


def _runtime(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "perceive_hub": _FakeHub(ContextManifest(items=())),
        "assistant_bootstrap": _FakeBootstrap("asst_1"),
        "assistant_id": "asst_1",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_observe_merges_bootstrap_projection() -> None:
    executor = PerceiveObserveExecutor()
    context = NodeContext(runtime=_runtime(), metadata={}, budget=None)
    output = await executor.node_execute(context, NodeInput(port_values={"state": None}))

    manifest = output.port_values["manifest"]
    assert isinstance(manifest, ContextManifest)
    instructions = manifest.by_kind("workspace_instructions")
    assert len(instructions) == 1
    assert instructions[0].provenance == "assistant.bootstrap.asst_1"
    artifacts = manifest.by_kind("workspace_artifacts")
    assert len(artifacts) == 1
    assert artifacts[0].provenance == "assistant.bootstrap.asst_1"


@pytest.mark.asyncio
async def test_observe_replaces_global_workspace_instructions() -> None:
    hub_manifest = ContextManifest(
        items=(
            ContextItem(
                kind="workspace_instructions",
                payload="项目 AGENTS.md",
                provenance="workspace_instructions_sensor",
            ),
        )
    )
    executor = PerceiveObserveExecutor()
    context = NodeContext(
        runtime=_runtime(perceive_hub=_FakeHub(hub_manifest)),
        metadata={},
        budget=None,
    )
    output = await executor.node_execute(context, NodeInput(port_values={"state": None}))

    manifest = output.port_values["manifest"]
    instructions = manifest.by_kind("workspace_instructions")
    assert len(instructions) == 1
    assert instructions[0].provenance == "assistant.bootstrap.asst_1"
    assert "workspace_instructions_sensor" not in {i.provenance for i in manifest.items}


@pytest.mark.asyncio
async def test_observe_without_assistant_id_keeps_manifest() -> None:
    executor = PerceiveObserveExecutor()
    context = NodeContext(
        runtime=_runtime(assistant_id=""),
        metadata={},
        budget=None,
    )
    output = await executor.node_execute(context, NodeInput(port_values={"state": None}))

    manifest = output.port_values["manifest"]
    assert isinstance(manifest, ContextManifest)
    assert manifest.by_kind("workspace_instructions") == []


@pytest.mark.asyncio
async def test_observe_without_bootstrap_service_keeps_manifest() -> None:
    executor = PerceiveObserveExecutor()
    context = NodeContext(
        runtime={"perceive_hub": _FakeHub(ContextManifest(items=()))},
        metadata={},
        budget=None,
    )
    output = await executor.node_execute(context, NodeInput(port_values={"state": None}))

    manifest = output.port_values["manifest"]
    assert isinstance(manifest, ContextManifest)
    assert manifest.items == ()
