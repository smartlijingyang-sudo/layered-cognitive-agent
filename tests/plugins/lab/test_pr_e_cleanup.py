# PR-E.2 — verify adapter/registry cleanup
"""Tests for PR-E.2 deletion of agent_lab/adapters/ and registry."""

import pathlib


class TestAdaptersCleanup:
    """The agent_lab/adapters/ directory must be deleted."""

    def test_adapters_dir_does_not_exist(self):
        adapters = pathlib.Path("agent_lab/adapters")
        assert not adapters.exists(), (
            f"agent_lab/adapters/ still exists; PR-E.2 must delete it"
        )


class TestToolsRegistryCleanup:
    """The agent_lab/tools/registry.{py,yaml} were deleted in PR-E.2.

    A minimal compat shim was restored in PR-D final so the legacy
    ``agent_lab.nodes.act.execute.body`` import still resolves. The
    shim is empty and is itself slated for deletion once the legacy
    body.py is rewritten (PR-D final, next iteration)."""

    def test_tools_registry_yaml_does_not_exist(self):
        """The full named-tool YAML inventory is gone (moved to LCA plugin layer)."""
        reg_yaml = pathlib.Path("agent_lab/tools/registry.yaml")
        assert not reg_yaml.exists(), (
            "agent_lab/tools/registry.yaml still exists; PR-E.2 must delete it"
        )

    def test_tools_init_no_registry_re_export(self):
        """tools/__init__.py must not re-export from the deleted registry."""
        init_file = pathlib.Path("agent_lab/tools/__init__.py")
        content = init_file.read_text()
        assert "from agent_lab.tools.registry" not in content, (
            "tools/__init__.py still imports from deleted registry.py"
        )

    def test_registry_py_is_compat_shim(self):
        """The restored registry.py is documented as a compat shim with delete-when."""
        reg_py = pathlib.Path("agent_lab/tools/registry.py")
        if reg_py.exists():
            content = reg_py.read_text()
            assert "compat shim" in content.lower() or "delete-when" in content.lower(), (
                "restored registry.py must document itself as a compat shim "
                "with delete-when clause (AGENTS.md §4)"
            )


class TestToolProviderMarker:
    """The new lca.plugins.lab.tools.provider must replace the deleted
    registry for the lab tool inventory."""

    def test_tools_provider_marker_registered(self):
        from lca.plugins.lab.internal.loader import get_instance, load_all
        load_all()
        marker = get_instance("lab.tools.provider")
        assert marker is not None
        assert marker.get("id") in ("provider", "tools.provider")


class TestStaleReferences:
    """No NEW code (lca/plugins/lab/, tests/plugins/lab/, profiles/, bundles/)
    should reference the old deleted paths. Old agent_lab/ files are
    themselves slated for PR-D final cleanup."""

    def test_no_imports_in_lca_plugins_lab(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "from agent_lab.adapters", "lca/plugins/lab/"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "", (
            f"lca/plugins/lab/ has stray imports: {result.stdout}"
        )

    def test_no_imports_in_tests_plugins_lab(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "--exclude=test_pr_e_cleanup.py",
             "from agent_lab.adapters", "tests/plugins/lab/"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "", (
            f"tests/plugins/lab/ has stray imports: {result.stdout}"
        )

    def test_no_tools_registry_imports_in_lca_plugins_lab(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "from agent_lab.tools.registry", "lca/plugins/lab/"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "", (
            f"lca/plugins/lab/ has stray registry imports: {result.stdout}"
        )

    def test_no_tools_registry_imports_in_tests_plugins_lab(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "--exclude=test_pr_e_cleanup.py",
             "from agent_lab.tools.registry", "tests/plugins/lab/"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "", (
            f"tests/plugins/lab/ has stray registry imports: {result.stdout}"
        )