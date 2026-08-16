"""Integration tests for gateway profile loading (Phase A.4).

Verifies that Gateway startup correctly:
1. Loads profile YAML → plugin tree → app.state
2. Wires plugin_host, plugin_tree, agent_registry, command_gateway
3. Resolves profile path: arg → LCA_PROFILE env → auto-detect
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PROFILE_PATH = Path("profiles/web-standard.yaml")


class TestGatewayProfileIntegration:
    """Gateway startup loads profile and wires plugin tree to app.state"""

    def test_create_app_loads_profile_when_path_provided(self, tmp_path: Path) -> None:
        """create_app(profile_path=...) loads profile and attaches to app.state"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        app = create_app(profile_path=str(PROFILE_PATH))

        # Verify plugin tree is loaded
        assert hasattr(app.state, "plugin_tree")
        assert app.state.plugin_tree is not None
        assert hasattr(app.state.plugin_tree, "host")
        assert hasattr(app.state.plugin_tree, "entries")

        # Verify plugin_host is wrapped
        assert hasattr(app.state, "plugin_host")
        assert app.state.plugin_host is not None

        # Verify profile_path is stored
        assert hasattr(app.state, "profile_path")
        assert app.state.profile_path == str(PROFILE_PATH)

    def test_create_app_has_agent_registry(self, tmp_path: Path) -> None:
        """create_app() attaches agent_registry to app.state"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        app = create_app(profile_path=str(PROFILE_PATH))

        assert hasattr(app.state, "agent_registry")
        assert app.state.agent_registry is not None

    def test_create_app_has_command_gateway(self, tmp_path: Path) -> None:
        """create_app() attaches command_gateway to app.state"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        app = create_app(profile_path=str(PROFILE_PATH))

        assert hasattr(app.state, "command_gateway")
        assert app.state.command_gateway is not None

    def test_profile_resolution_from_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """create_app() resolves LCA_PROFILE env var when no arg provided"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        # Set env var
        monkeypatch.setenv("LCA_PROFILE", str(PROFILE_PATH))

        app = create_app()

        # Should have loaded from env var
        assert hasattr(app.state, "profile_path")
        assert app.state.profile_path == str(PROFILE_PATH)
        assert hasattr(app.state, "plugin_tree")

    def test_profile_resolution_arg_overrides_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """create_app() profile_path arg takes precedence over LCA_PROFILE env"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        # Set env var to different path
        monkeypatch.setenv("LCA_PROFILE", "some/other/profile.yaml")

        # But provide arg
        app = create_app(profile_path=str(PROFILE_PATH))

        # Arg should win
        assert app.state.profile_path == str(PROFILE_PATH)

    def test_plugin_host_has_correct_scope(self, tmp_path: Path) -> None:
        """plugin_host is wrapped with PROFILE scope kind"""
        from gateway.app import create_app
        from lca.contracts.harness.plugin import ScopeKind

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        app = create_app(profile_path=str(PROFILE_PATH))

        # Verify scope kind via property
        assert hasattr(app.state.plugin_host, "scope_kind")
        assert app.state.plugin_host.scope_kind == ScopeKind.PROFILE

        # Verify scope_id is profile name stem via property
        assert hasattr(app.state.plugin_host, "scope_id")
        assert app.state.plugin_host.scope_id == "web-standard"

    def test_plugin_tree_entries_not_empty(self, tmp_path: Path) -> None:
        """Loaded plugin tree has entries from profile"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        app = create_app(profile_path=str(PROFILE_PATH))

        # Tree should have loaded entries
        assert len(app.state.plugin_tree.entries) > 0

    def test_agent_registry_receives_plugin_scope(self, tmp_path: Path) -> None:
        """AgentRegistry is initialized with plugin_scope from plugin_host"""
        from gateway.app import create_app

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        app = create_app(profile_path=str(PROFILE_PATH))

        # AgentRegistry should have plugin_scope set
        registry = app.state.agent_registry
        assert hasattr(registry, "_plugin_scope")
        assert registry._plugin_scope is app.state.plugin_host

    def test_create_app_without_profile_still_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """create_app() works without profile (no plugin tree, but spine binds)"""
        from gateway.app import create_app

        # Ensure no env var
        monkeypatch.delenv("LCA_PROFILE", raising=False)

        # No profile_path arg, and we'll pretend auto-detect doesn't find anything
        # by changing cwd
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            app = create_app()

            # Should not have plugin_tree
            assert not hasattr(app.state, "plugin_tree")

            # But should still have agent_registry and command_gateway
            assert hasattr(app.state, "agent_registry")
            assert hasattr(app.state, "command_gateway")
        finally:
            os.chdir(original_cwd)

    def test_missing_profile_raises_error(self, tmp_path: Path) -> None:
        """create_app() raises FileNotFoundError for non-existent profile"""
        from gateway.app import create_app

        fake_path = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError, match="harness profile not found"):
            create_app(profile_path=str(fake_path))


class TestProfileLoadingInternals:
    """Lower-level tests for _load_harness_profile function"""

    def test_load_harness_profile_sets_all_state(self, tmp_path: Path) -> None:
        """_load_harness_profile sets plugin_tree, plugin_host, profile_path"""
        from starlette.applications import Starlette

        from gateway.app import _load_harness_profile

        if not PROFILE_PATH.exists():
            pytest.skip("profiles/web-standard.yaml not found")

        app = Starlette()
        _load_harness_profile(app, str(PROFILE_PATH))

        assert hasattr(app.state, "plugin_tree")
        assert hasattr(app.state, "plugin_host")
        assert hasattr(app.state, "profile_path")
        assert app.state.profile_path == str(PROFILE_PATH)

    def test_load_harness_profile_missing_file_raises(self, tmp_path: Path) -> None:
        """_load_harness_profile raises FileNotFoundError for missing file"""
        from starlette.applications import Starlette

        from gateway.app import _load_harness_profile

        app = Starlette()
        fake_path = tmp_path / "missing.yaml"

        with pytest.raises(FileNotFoundError):
            _load_harness_profile(app, str(fake_path))
