"""Regression test: phase.perceive.fold must output a typed Observation.

The reflect critic reads ``Observation.success``. If the fold node leaks a raw
``ContextManifest`` through the ``observation`` port, ``phase.reflect.score``
crashes with ``'ContextManifest' object has no attribute 'success'``.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.perceive.fold.fold import PerceiveFoldExecutor


async def test_perceive_fold_outputs_typed_observation() -> None:
    executor = PerceiveFoldExecutor()
    manifest = ContextManifest(items=())
    context = NodeContext(runtime={}, metadata={}, budget=None)
    node_input = NodeInput(port_values={"manifest": manifest})

    output = await executor.node_execute(context, node_input)

    assert output.port_values["in_assembled_manifest"] is manifest
    observation = output.port_values["observation"]
    assert isinstance(observation, Observation)
    assert observation.success is True
    assert observation.payload is manifest
