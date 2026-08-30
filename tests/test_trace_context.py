from __future__ import annotations

import pytest

from lca.contracts.harness.trace_context import AgentTraceContext


def test_trace_context_exports_reproducibility_attributes() -> None:
    context = AgentTraceContext("task-1", "step-1", "model-v1", "tool-v2", "policy-v3")

    assert context.as_attributes()["model_version"] == "model-v1"
    assert context.as_attributes()["policy_version"] == "policy-v3"


def test_trace_context_requires_all_versions() -> None:
    with pytest.raises(ValueError):
        AgentTraceContext("task-1", "step-1", "", "tool-v2", "policy-v3")
