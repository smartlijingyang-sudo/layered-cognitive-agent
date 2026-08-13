"""wire.py coordinate table — the only remaining tool wire contract."""

from __future__ import annotations

import unittest

from gateway.runs.wire import WIRE, resolve


class TestToolWireTable(unittest.TestCase):
    def test_activate_skill_wire(self) -> None:
        self.assertEqual(resolve("activate_skill"), ("lobe-skills", "activateSkill"))

    def test_run_skill_script_maps_to_exec_script(self) -> None:
        self.assertEqual(resolve("run_skill_script"), ("lobe-skills", "execScript"))

    def test_import_skill_base_coordinate(self) -> None:
        self.assertEqual(resolve("import_skill"), ("lobe-skill-store", "importSkill"))

    def test_web_search_wire(self) -> None:
        self.assertEqual(resolve("web_search"), ("lobe-web-browsing", "search"))

    def test_execute_code_wire(self) -> None:
        self.assertEqual(resolve("execute_code"), ("lobe-cloud-sandbox", "executeCode"))

    def test_unknown_is_none(self) -> None:
        self.assertIsNone(resolve("not_registered"))

    def test_table_covers_sandbox_and_skills(self) -> None:
        self.assertIn("run_command", WIRE)
        self.assertIn("read_file", WIRE)
        self.assertIn("search_skill", WIRE)
