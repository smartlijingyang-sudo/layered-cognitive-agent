# PR-B — act phase plugin loading tests
"""Tests for the act.* node plugin migration and provider split.

PR-B — verifies that act.{shape,authorize,execute,observe} and the
body/tool/transport providers all register correctly with the loader.
"""

import pytest
from lca.plugins.lab.internal.loader import (
    get_instance,
    list_ids,
    load_all,
    reset_for_tests,
)


class TestActPhasePlugins:
    """Verify the act.* worker nodes are registered in the loader."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_load_all_includes_act_plugins(self):
        """load_all() should register all 4 act worker plugins."""
        load_all()
        ids = list_ids()
        assert "lab.act.shape" in ids
        assert "lab.act.authorize" in ids
        assert "lab.act.execute" in ids
        assert "lab.act.observe" in ids

    def test_act_shape_plugin_registered(self):
        """lab.act.shape should resolve to the ActShape marker."""
        load_all()
        instance = get_instance("lab.act.shape")
        assert instance is not None
        assert instance.get("id") == "act.shape"

    def test_act_authorize_plugin_registered(self):
        """lab.act.authorize should resolve to the ActAuthorize marker."""
        load_all()
        instance = get_instance("lab.act.authorize")
        assert instance is not None
        assert instance.get("id") == "act.authorize"

    def test_act_execute_plugin_registered(self):
        """lab.act.execute should resolve to the ActExecute marker with needs list."""
        load_all()
        instance = get_instance("lab.act.execute")
        assert instance is not None
        assert instance.get("id") == "act.execute"
        assert "lab.body" in instance.get("needs", [])

    def test_act_observe_plugin_registered(self):
        """lab.act.observe should resolve to the ActObserve marker."""
        load_all()
        instance = get_instance("lab.act.observe")
        assert instance is not None
        assert instance.get("id") == "act.observe"

    def test_act_execute_no_lca_cognition_import(self):
        """Act* plugin files must not import from lca.cognition.* directly."""
        import pathlib
        for subdir in ("shape", "authorize", "execute", "observe"):
            plugin_file = (
                pathlib.Path("lca/plugins/lab/act") / subdir / "plugin.py"
            )
            if plugin_file.exists():
                content = plugin_file.read_text()
                assert "from lca.cognition" not in content, (
                    f"{plugin_file} imports from lca.cognition.* — "
                    "act.* plugins must use provider abstraction"
                )


class TestProviders:
    """Verify the body/tool/transport provider stubs are registered."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_tool_registry_provider_registered(self):
        """lca.plugins.lab.tools.provider should register a marker."""
        load_all()
        from lca.plugins.lab.internal.loader import get_instance
        instance = get_instance("lab.tool_registry")
        assert instance is not None
        assert instance.get("id") == "lab.tool_registry"

    def test_transport_provider_registered(self):
        """lca.plugins.lab.transport.provider should register a marker."""
        load_all()
        from lca.plugins.lab.internal.loader import get_instance
        instance = get_instance("lab.transport")
        assert instance is not None
        assert instance.get("id") == "lab.transport"

    def test_body_provider_registered(self):
        """lca.plugins.lab.act.body_provider should register a marker."""
        load_all()
        from lca.plugins.lab.internal.loader import get_instance
        instance = get_instance("lab.body")
        assert instance is not None
        assert instance.get("id") == "lab.body"


class TestLoaderClosedSet:
    """Verify loader allow-list matches filesystem for PR-B plugins."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_known_subpackages_includes_pr_b(self):
        """known_subpackages should include all PR-B plugin modules."""
        from lca.plugins.lab.internal.loader import known_subpackages
        known = set(known_subpackages())
        # PR-B plugin modules
        assert "lca.plugins.lab.act.shape.plugin" in known
        assert "lca.plugins.lab.act.authorize.plugin" in known
        assert "lca.plugins.lab.act.execute.plugin" in known
        assert "lca.plugins.lab.act.observe.plugin" in known
        assert "lca.plugins.lab.act.body_provider.plugin" in known
        assert "lca.plugins.lab.tools.provider.plugin" in known
        assert "lca.plugins.lab.transport.provider.plugin" in known


class TestNoBuildBodyInActNodes:
    """Verify act.* plugin files do not embed Body construction."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_act_plugin_files_have_no_build_body(self):
        """No act.* plugin file may contain 'build_body' or 'run_body_act'."""
        import pathlib
        for plugin_file in pathlib.Path("lca/plugins/lab/act").rglob("plugin.py"):
            content = plugin_file.read_text()
            assert "build_body" not in content, (
                f"{plugin_file} contains 'build_body' — "
                "act.* plugins must delegate to provider"
            )
            assert "run_body_act" not in content, (
                f"{plugin_file} contains 'run_body_act' — "
                "act.* plugins must delegate to provider"
            )