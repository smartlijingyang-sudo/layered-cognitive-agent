"""CLI JSON success is the command outcome, not the process exit code."""

from __future__ import annotations

import unittest

from lca.infrastructure.computer.cli_json import cli_json_success
from lca.infrastructure.computer.office_plane import normalize_officecli_command
from lca.infrastructure.workspace.deliverable import (
    is_office_name,
    is_office_publish_intent,
    officecli_verb,
    publishable_file_parts,
)


class TestCliJsonSuccess(unittest.TestCase):
    def test_success_true_despite_warnings(self) -> None:
        stdout = (
            '{"success": true, "data": "Added slide at /slide[1]", '
            '"warnings": [{"code": "unsupported_property"}]}'
        )
        self.assertTrue(cli_json_success(stdout))

    def test_success_false(self) -> None:
        self.assertFalse(cli_json_success('{"success": false, "error": "not_found"}'))

    def test_plain_text_is_unknown(self) -> None:
        self.assertIsNone(cli_json_success("ok\n"))


class TestOfficePublishPolicy(unittest.TestCase):
    def test_office_create_is_not_a_deliverable(self) -> None:
        parts = [{"name": "deck.pptx", "url": "/files/file_aaa"}]
        cmd = "officecli create /mnt/data/outputs/deck.pptx --json"
        self.assertEqual(officecli_verb(cmd), "create")
        self.assertFalse(is_office_publish_intent(tool_name="run_command", command=cmd))
        self.assertEqual(publishable_file_parts(parts, command=cmd, tool_name="run_command"), [])

    def test_office_add_is_not_a_deliverable(self) -> None:
        parts = [{"name": "deck.pptx", "url": "/files/file_bbb"}]
        cmd = "officecli add /mnt/data/outputs/deck.pptx / --type slide --json"
        self.assertEqual(
            publishable_file_parts(
                parts,
                stdout='{"success": true, "data": "Added slide"}',
                tool_name="run_command",
                command=cmd,
            ),
            [],
        )

    def test_office_close_is_publishable(self) -> None:
        parts = [{"name": "deck.pptx", "url": "/files/file_ccc"}]
        cmd = "officecli close /mnt/data/outputs/deck.pptx --json"
        self.assertTrue(is_office_publish_intent(tool_name="run_command", command=cmd))
        self.assertEqual(
            publishable_file_parts(parts, tool_name="run_command", command=cmd),
            parts,
        )

    def test_export_file_publishes_office(self) -> None:
        parts = [{"name": "deck.pptx", "url": "/files/file_ddd"}]
        self.assertEqual(
            publishable_file_parts(parts, tool_name="exportFile"),
            parts,
        )

    def test_png_is_always_publishable(self) -> None:
        parts = [{"name": "chart.png", "url": "/files/file_eee"}]
        self.assertEqual(
            publishable_file_parts(parts, tool_name="executeCode"),
            parts,
        )

    def test_office_name_matrix(self) -> None:
        self.assertTrue(is_office_name("a.pptx"))
        self.assertFalse(is_office_name("a.preview.html"))
        self.assertFalse(is_office_name("a.pdf"))

    def test_verb_inside_compound_shell(self) -> None:
        cmd = "mkdir -p /mnt/data/outputs && officecli create /mnt/data/outputs/a.pptx --json"
        self.assertEqual(officecli_verb(cmd), "create")


class TestOfficecliBatchNormalize(unittest.TestCase):
    def test_rewrites_json_prop_to_props(self) -> None:
        command = (
            "officecli batch /mnt/data/outputs/deck.pptx --json <<'BATCH'\n"
            '[{"op":"add","path":"/","type":"slide","prop":{"title":"Hi"}}]\n'
            "BATCH"
        )
        out = normalize_officecli_command(command)
        self.assertIn('"props"', out)
        self.assertNotIn('"prop":', out)

    def test_rewrites_cli_lines_to_json(self) -> None:
        command = (
            "officecli batch /mnt/data/outputs/deck.pptx --json <<'BATCH'\n"
            'add / --type slide --prop title="背景" --prop background=1A1A2E\n'
            "BATCH"
        )
        out = normalize_officecli_command(command)
        self.assertIn('"op": "add"', out)
        self.assertIn('"props"', out)
        self.assertIn("背景", out)

    def test_leaves_plain_add_alone(self) -> None:
        command = "officecli add /mnt/data/outputs/deck.pptx / --type slide --json"
        self.assertEqual(normalize_officecli_command(command), command)
