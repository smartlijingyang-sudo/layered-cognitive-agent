# PR-C — Lab session provider tests
"""Tests for the lab.session provider (PR-C) and the runtime_bind cleanup."""

import pytest
from lca.plugins.lab.internal.loader import (
    get_instance,
    list_ids,
    load_all,
    reset_for_tests,
)


class TestSessionProviderMarker:
    """Verify the lab.session provider marker is registered."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_lab_session_marker_registered(self):
        """load_all() should register the lab.session marker."""
        load_all()
        ids = list_ids()
        assert "lab.session" in ids

    def test_lab_session_marker_shape(self):
        """The marker must carry plan_ref=agent_lab_act and id=lab.session."""
        load_all()
        marker = get_instance("lab.session")
        assert marker is not None
        assert marker.get("id") == "lab.session"
        assert marker.get("plan_ref") == "agent_lab_act"

    def test_plan_ref_helper_retained(self):
        """plan_ref() must return 'agent_lab_act' for backwards compat."""
        load_all()
        from lca.plugins.lab.session.provider.plugin import plan_ref, PLAN_REF
        assert plan_ref() == "agent_lab_act"
        assert PLAN_REF == "agent_lab_act"


class TestRuntimeBindCleanup:
    """Verify the agent_lab/nodes/ directory (which contained runtime_bind.py)
    is deleted. The runtime_bind machinery was replaced by
    lca.plugins.lab.session.provider in PR-C; the directory itself was
    deleted in PR-D final cleanup."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_agent_lab_nodes_dir_deleted(self):
        """agent_lab/nodes/ must not exist after PR-D final cleanup."""
        import pathlib
        nodes_dir = pathlib.Path("agent_lab/nodes")
        assert not nodes_dir.exists(), (
            f"{nodes_dir} still exists; PR-D final cleanup must delete it"
        )

    def test_plan_ref_re_exported_from_lab_session(self):
        """plan_ref() is now sourced from lca.plugins.lab.session.provider."""
        from lca.plugins.lab.session.provider.plugin import plan_ref
        assert plan_ref() == "agent_lab_act"


class TestLoaderClosedSet:
    """Verify loader allow-list includes the PR-C session provider."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_known_subpackages_includes_session_provider(self):
        """known_subpackages must include the lab session provider module."""
        from lca.plugins.lab.internal.loader import known_subpackages
        known = set(known_subpackages())
        assert "lca.plugins.lab.session.provider.plugin" in known


class TestNoGlobalInAgentLab:
    """Verify no global Session publishing tokens remain in agent_lab/."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_no_set_publish_session_under_nodes(self):
        """set_publish_session must not be called from any node file (excluding
        __pycache__ and docstring mentions)."""
        import subprocess, re, pathlib
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "set_publish_session", "agent_lab/nodes/"],
            capture_output=True, text=True
        )
        actual = []
        for line in result.stdout.splitlines():
            if "__pycache__" in line:
                continue
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            content = pathlib.Path(parts[0]).read_text()
            content_no_doc = re.sub(r'"""[\s\S]*?"?""|\'\'\'[\s\S]*?\'\'\'', '', content)
            if "set_publish_session" in content_no_doc:
                actual.append(line)
        assert not actual, (
            f"set_publish_session leaked into code: {actual}"
        )