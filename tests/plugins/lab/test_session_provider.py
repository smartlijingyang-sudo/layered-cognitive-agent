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
    """Verify the legacy runtime_bind no longer has the global token or
    ensure_act_runtime."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_runtime_bind_no_global_token(self):
        """agent_lab.nodes.act.execute.runtime_bind must not have _PUBLISH_TOKEN as
        a binding (docstring mentions are OK; only identifier usage counts)."""
        import pathlib, re
        rb = pathlib.Path("agent_lab/nodes/act/execute/runtime_bind.py")
        content = rb.read_text()
        # Strip docstrings before matching
        no_doc = re.sub(r'"""[\s\S]*?"""', '', content)
        assert "_PUBLISH_TOKEN" not in no_doc, (
            "runtime_bind.py must not bind or use _PUBLISH_TOKEN after PR-C"
        )

    def test_runtime_bind_no_ensure_act_runtime(self):
        """ensure_act_runtime must be removed from runtime_bind.py."""
        import pathlib, re
        rb = pathlib.Path("agent_lab/nodes/act/execute/runtime_bind.py")
        content = rb.read_text()
        no_doc = re.sub(r'"""[\s\S]*?"""', '', content)
        assert "ensure_act_runtime" not in no_doc, (
            "ensure_act_runtime must be removed from runtime_bind.py after PR-C"
        )

    def test_runtime_bind_no_set_publish_session(self):
        """set_publish_session must not be imported/called in runtime_bind.py."""
        import pathlib, re
        rb = pathlib.Path("agent_lab/nodes/act/execute/runtime_bind.py")
        content = rb.read_text()
        no_doc = re.sub(r'"""[\s\S]*?"""', '', content)
        assert "set_publish_session" not in no_doc, (
            "set_publish_session must not appear in runtime_bind.py code; "
            "Session binding now lives in lca.plugins.lab.session.provider"
        )

    def test_plan_ref_still_exported(self):
        """plan_ref() must still be importable from runtime_bind (backwards compat).

        Skipped when cordis is not available (runtime_bind is in the same
        import chain that requires the full LCA runtime; the lint-based
        tests above already verify the file contents).
        """
        pytest.importorskip("cordis")
        from agent_lab.nodes.act.execute.runtime_bind import plan_ref
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