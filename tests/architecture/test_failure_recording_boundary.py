"""Architecture guards for the lifecycle/observability seam."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

from gateway.runs.terminal.failure import RunFailureFacts

ROOT = Path(__file__).parents[2]
FAILURE_RECORDING = ROOT / "gateway" / "runs" / "failure_recording.py"


def test_failure_recording_does_not_import_mutable_run_carrier() -> None:
    """Journal observation must not own or depend on RunSession lifecycle state."""

    tree = ast.parse(FAILURE_RECORDING.read_text())
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "gateway.runs.session.session" not in imported_modules


def test_failure_facts_are_immutable_and_observation_ready() -> None:
    """The seam accepts only the minimum frozen facts needed by the recorder."""

    facts = RunFailureFacts(
        trace_id="trace-1",
        run_id="run-1",
        agent_role="agent",
        strategy_key="default",
        objective="test",
        error="failed",
        hub=None,
    )

    assert facts.error == "failed"
    assert "hub" in getattr(RunFailureFacts, "__slots__", ())
    try:
        facts.error = "changed"  # type: ignore[misc]
    except (AttributeError, FrozenInstanceError):
        pass
    else:
        raise AssertionError("RunFailureFacts must be immutable")
