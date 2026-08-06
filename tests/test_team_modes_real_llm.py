"""Real-LLM smoke for all Team modes (marker: real_llm).

Asserts structured outcomes only (status/steps/topology), never free-text copy.
"""

from __future__ import annotations

import os

import pytest

from lca.contracts.atoms.telemetry import SpanName
from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter
from tests.harness.collector import InMemoryObservability
from tests.harness.runner import run_mode
from tests.harness.trace_assert import assert_must_include_spans

load_dotenv_if_present()

pytestmark = pytest.mark.real_llm

_HAS_KEY = bool(os.getenv("LLM_API_KEY"))

_MODES = (
    "pipeline",
    "fan_out",
    "peer_relay",
    "peer_swarm",
    "debate",
    "graph",
    "routing",
    "consult",
    "board",
    "solo",
)


@pytest.mark.skipif(not _HAS_KEY, reason="LLM_API_KEY not set")
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_mode_real_llm_smoke(mode: str) -> None:
    llm = resolve_llm_adapter()
    collector = InMemoryObservability()
    # Multiplex not required: inject collector via Agent observability in run_mode
    outcome = await run_mode(
        mode,
        llm,
        collector=collector,
        objective=f"Briefly handle mode probe: {mode}. One sentence.",
        max_rounds=1,
    )
    assert outcome.result.status in ("completed", "failed", "input_required")
    # Topology: team modes must emit run.team + delegation（ADR-0037 一等委派）
    names = outcome.bundle.names()
    if mode == "solo":
        assert SpanName.RUN_AGENT.value in names
    else:
        assert_must_include_spans(
            outcome.bundle,
            [SpanName.RUN_TEAM.value, SpanName.DELEGATION.value],
        )
    assert outcome.result.total_steps >= 0
