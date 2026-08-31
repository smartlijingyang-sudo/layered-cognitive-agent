from __future__ import annotations
import pytest

from pathlib import Path

from lca_kernel.cli import create_app
from gateway.profile import resolve_profile_path


@pytest.mark.asyncio
async def test_profile_resolution_has_explicit_precedence(tmp_path: Path) -> None:
    default = tmp_path / "profiles" / "web-standard.yaml"
    default.parent.mkdir()
    default.write_text("profile: test\n")

    assert (
        resolve_profile_path(
            "profiles/explicit.yaml",
            environ={"LCA_PROFILE": "profiles/environment.yaml"},
            working_directory=tmp_path,
        )
        == "profiles/explicit.yaml"
    )
    assert (
        resolve_profile_path(
            environ={"LCA_PROFILE": "profiles/environment.yaml"},
            working_directory=tmp_path,
        )
        == "profiles/environment.yaml"
    )
    assert resolve_profile_path(environ={}, working_directory=tmp_path) == (
        "profiles/web-standard.yaml"
    )


@pytest.mark.asyncio
async def test_profile_resolution_returns_none_without_fallback(tmp_path: Path) -> None:
    assert resolve_profile_path(environ={}, working_directory=tmp_path) is None


@pytest.mark.asyncio
async def test_create_app_publishes_one_session_object_graph() -> None:
    import pytest

    pytest.skip(
        "agent_registry / command_gateway / run_registry / run_port moved to "
        "lifespan-driven ctx injection under ADR-0115 决定 6 (thin factory); "
        "see tests/test_thin_factory.py for new shape"
    )
    from gateway.runs.terminal.legacy_adapter import RegistryRunAdapter

    application = await create_app(lifespan=lambda app: None)

    assert application.state.agent_registry is not None
    assert application.state.command_gateway is not None
    assert application.state.run_registry is not None
    assert isinstance(application.state.run_port, RegistryRunAdapter)
