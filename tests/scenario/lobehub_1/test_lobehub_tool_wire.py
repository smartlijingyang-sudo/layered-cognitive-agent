"""wire.py coordinate table — the only remaining tool wire contract."""

from __future__ import annotations

import unittest

from lca.plugins.transport.webserver.handlers.runs.wire.wire import WIRE, resolve


class TestToolWireTable(unittest.TestCase):
    def test_activate_skill_wire(self) -> None:
        self.assertEqual(resolve("activate_skill"), ("lobe-skills", "activateSkill"))

    def test_run_skill_script_maps_to_exec_script(self) -> None:
        self.assertEqual(resolve("run_skill_script"), ("lobe-skills", "execScript"))

    def test_import_skill_base_coordinate(self) -> None:
        self.assertEqual(resolve("import_skill"), ("lobe-skill-store", "importSkill"))

    def test_web_search_wire(self) -> None:
        self.assertEqual(resolve("search"), ("lobe-web-browsing", "search"))

    def test_execute_code_wire(self) -> None:
        self.assertEqual(resolve("executeCode"), ("lobe-cloud-sandbox", "executeCode"))

    def test_unknown_is_none(self) -> None:
        self.assertIsNone(resolve("not_registered"))

    def test_table_covers_sandbox_and_skills(self) -> None:
        self.assertIn("runCommand", WIRE)
        self.assertIn("readFile", WIRE)
        self.assertIn("search_skill", WIRE)

    def test_create_assistant_maps_to_agent_management(self) -> None:
        """create_assistant must resolve to lobe-agent-management/createAgent
        so the frontend renders the CreateAgent card instead of logging
        'unknown tool' and breaking the assistant message parent chain
        (regression: run_53b7414d67bb final reply invisible)."""
        self.assertEqual(
            resolve("create_assistant"), ("lobe-agent-management", "createAgent")
        )


class TestLcaWireGeneration(unittest.TestCase):
    """The lca_run_driver patch generates lobehub-ui lcaWire.ts from WIRE."""

    def test_generated_wire_includes_create_assistant(self) -> None:
        from deploy.lobehub.patches.runtime.lca_run_driver import render_wire_ts

        output = render_wire_ts(WIRE)
        self.assertIn("'create_assistant'", output)
        self.assertIn("'lobe-agent-management'", output)
        self.assertIn("'createAgent'", output)
