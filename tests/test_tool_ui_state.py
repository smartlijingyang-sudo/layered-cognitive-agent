"""Tool UI state SSOT — started/invoked plugin_state + compact previews + wire merge."""

from __future__ import annotations

import json
import unittest

from lca.contracts.models.core.decision import Observation
from lca.layer1_cognitive.body.tool_ui_state import (
    build_invoked_plugin_state,
    build_started_plugin_state,
    compact_args_preview,
    wire_arguments_json,
)


class TestCompactArgsPreview(unittest.TestCase):
    def test_long_code_stays_valid_json_under_budget(self) -> None:
        code = "print(" + repr("中" * 5000) + ")\n" * 50
        preview = compact_args_preview(
            {"code": code, "language": "python", "description": "生成PDF"}
        )
        self.assertLessEqual(len(preview), 1800)
        parsed = json.loads(preview)
        self.assertEqual(parsed["language"], "python")
        self.assertTrue(parsed.get("code_truncated") or parsed.get("code_chars", 0) > 200)
        self.assertIn("code_chars", parsed)
        self.assertEqual(parsed["code_chars"], len(code))

    def test_short_args_roundtrip(self) -> None:
        args = {"skill_id": "anthropics-skills-xlsx"}
        preview = compact_args_preview(args)
        self.assertEqual(json.loads(preview), args)


class TestStartedPluginState(unittest.TestCase):
    def test_execute_code_includes_full_code(self) -> None:
        code = "x = 1\n" * 2000
        state = build_started_plugin_state(
            "execute_code",
            {"code": code, "language": "python", "description": "big"},
        )
        self.assertEqual(state["code"], code)
        self.assertEqual(state["language"], "python")
        self.assertEqual(state["description"], "big")
        self.assertNotIn("success", state)

    def test_run_command_includes_full_command(self) -> None:
        cmd = "mkdir -p /mnt/data/fonts && curl -L -o /tmp/f.ttf https://example.com/f.ttf"
        state = build_started_plugin_state(
            "run_command",
            {"command": cmd, "description": "Download font", "timeout": 30},
        )
        self.assertEqual(state["command"], cmd)
        self.assertEqual(state["description"], "Download font")

    def test_activate_skill_started(self) -> None:
        state = build_started_plugin_state("activate_skill", {"skill_id": "anthropics-skills-pdf"})
        self.assertEqual(state["skill_id"], "anthropics-skills-pdf")
        self.assertEqual(state["id"], "anthropics-skills-pdf")


class TestInvokedPluginState(unittest.TestCase):
    def test_skill_full_content_from_payload(self) -> None:
        body = "# PDF Processing Guide\n\n## Overview\n\n" + ("detail " * 500)
        obs = Observation(
            observation_id="o1",
            success=True,
            payload={"text": body, "skill_id": "anthropics-skills-pdf"},
        )
        state = build_invoked_plugin_state(
            "activate_skill",
            {"skill_id": "anthropics-skills-pdf"},
            obs,
        )
        self.assertEqual(state["content"], body)
        self.assertIn("PDF Processing Guide", state["title"])
        self.assertTrue(state["success"])
        self.assertGreater(len(state["content"]), 1000)
        self.assertFalse(state["hasResources"])
        self.assertNotIn("resources", state)

    def test_skill_prefers_nested_state(self) -> None:
        body = "# Full\n\nbody content here"
        obs = Observation(
            observation_id="o1",
            success=True,
            payload={
                "text": body[:10],
                "skill_id": "x",
                "state": {
                    "id": "x",
                    "content": body,
                    "title": "Full",
                    "success": True,
                },
            },
        )
        state = build_invoked_plugin_state("activate_skill", {"skill_id": "x"}, obs)
        self.assertEqual(state["content"], body)

    def test_computer_nested_state(self) -> None:
        code = "print(1)\n" * 100
        obs = Observation(
            observation_id="o1",
            success=False,
            payload={
                "state": {
                    "code": code,
                    "stderr": "SyntaxError: boom",
                    "exitCode": 1,
                    "success": False,
                },
                "summary": "err",
            },
            error="SyntaxError: boom",
        )
        state = build_invoked_plugin_state(
            "execute_code",
            {"code": code, "language": "python"},
            obs,
        )
        self.assertEqual(state["code"], code)
        self.assertIn("SyntaxError", state.get("error") or state.get("stderr") or "")


class TestWireArgumentsJson(unittest.TestCase):
    def test_restores_code_from_plugin_state_over_truncated_preview(self) -> None:
        full_code = "from reportlab.pdfgen import canvas\n" + ("# line\n" * 300)
        truncated_preview = compact_args_preview(
            {"code": full_code, "language": "python", "description": "pdf"}
        )
        # Simulate AttributePolicy damage (would break json.loads)
        broken = truncated_preview[:50] + "..."
        wire = wire_arguments_json(
            arguments_preview=broken,
            plugin_state={"code": full_code, "language": "python", "description": "pdf"},
        )
        parsed = json.loads(wire)
        self.assertEqual(parsed["code"], full_code)
        self.assertEqual(parsed["language"], "python")
        self.assertNotIn("code_truncated", parsed)


if __name__ == "__main__":
    unittest.main()
