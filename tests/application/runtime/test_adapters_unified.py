"""Tests verifying the consolidated architecture of application/runtime/adapters (INV-ARCH-15)."""

from pathlib import Path

import pytest

from lca.application.runtime.adapters import (
    CliRunArgs,
    cli_args_to_intent,
    coerce_mode,
    run_request_to_intent,
)
from lca.contracts.runtime.intent import RunIntent


def test_inv_arch_15_adapters_module_exports() -> None:
    """INV-ARCH-15: All adapter components are directly exportable from lca.application.runtime.adapters."""
    assert callable(cli_args_to_intent)
    assert callable(run_request_to_intent)
    assert callable(coerce_mode)
    assert CliRunArgs is not None


def test_inv_arch_15_no_adapters_micro_directory() -> None:
    """INV-ARCH-15: lca/application/runtime/adapters/ directory must not exist (flattened to adapters.py)."""
    adapters_dir = Path(__file__).resolve().parents[3] / "lca" / "application" / "runtime" / "adapters"
    assert not adapters_dir.is_dir(), (
        f"Micro-directory {adapters_dir} still exists! It must be flattened into lca/application/runtime/adapters.py."
    )


def test_inv_arch_15_coerce_mode() -> None:
    """INV-ARCH-15: coerce_mode strictly validates RunMode literals."""
    assert coerce_mode("solo") == "solo"
    assert coerce_mode("team") == "team"
    with pytest.raises(ValueError, match="must be one of"):
        coerce_mode("invalid")


def test_inv_arch_15_cli_args_to_intent() -> None:
    """INV-ARCH-15: cli_args_to_intent converts CliRunArgs to RunIntent correctly."""
    args = CliRunArgs(profile="profiles/test.yaml", user_text="hello", mode="solo")
    intent = cli_args_to_intent(args)
    assert isinstance(intent, RunIntent)
    assert intent.profile_path == "profiles/test.yaml"
    assert intent.user_text == "hello"
    assert intent.mode == "solo"
    assert intent.surface == "cli"


def test_inv_arch_16_coordinator_package_exports() -> None:
    """INV-ARCH-16: Coordinator package cleanly exports all streaming and pump primitives."""
    from lca.application.runtime.coordinator import (
        EventTranslator,
        LcaAgentRuntimeCoordinator,
        MetadataWriter,
        TerminalHint,
        ToolStateWriter,
        is_stream_terminal_status,
        resolve_live_terminal_hint,
        schedule_gateway_session_pump,
        session_event_to_stamped,
    )

    assert EventTranslator is not None
    assert LcaAgentRuntimeCoordinator is not None
    assert MetadataWriter is not None
    assert TerminalHint is not None
    assert ToolStateWriter is not None
    assert callable(is_stream_terminal_status)
    assert callable(resolve_live_terminal_hint)
    assert callable(schedule_gateway_session_pump)
    assert callable(session_event_to_stamped)

