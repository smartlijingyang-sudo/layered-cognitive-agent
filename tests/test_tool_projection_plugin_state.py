"""End-to-end: journal plugin_state → ToolEventProjector → lca SSE events."""

from __future__ import annotations

import json
import unittest
from typing import Any

from gateway.projection.tool_events import ToolEventProjector
from lca.contracts.models.observability.journal import ToolInvoked, ToolStarted


def _collect() -> tuple[ToolEventProjector, list[dict[str, Any]]]:
    out: list[dict[str, Any]] = []

    def emit_lca(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out.extend(events)
        return [{"lca": {"events": events}}]

    def emit_delta(deltas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out.extend(deltas)
        return deltas

    return ToolEventProjector(emit_lca=emit_lca, emit_delta=emit_delta), out


class TestToolEventProjectorPluginState(unittest.TestCase):
    def test_activate_skill_result_has_full_content(self) -> None:
        body = "# PDF Processing Guide\n\n## Overview\n\n" + ("x" * 2000)
        proj, events = _collect()
        proj.project_started(
            ToolStarted(
                tool_name="activate_skill",
                arguments_preview='{"skill_id":"anthropics-skills-pdf"}',
                invocation_id="inv_skill",
                plugin_state={
                    "skill_id": "anthropics-skills-pdf",
                    "id": "anthropics-skills-pdf",
                    "title": "anthropics-skills-pdf",
                },
            )
        )
        proj.project_invoked(
            ToolInvoked(
                tool_name="activate_skill",
                arguments_preview='{"skill_id":"anthropics-skills-pdf"}',
                result_preview='{"text":"# PDF Processing Guide\\n\\n## Ove...","skill_id":"anthropics-skills-pdf"}',
                ok=True,
                invocation_id="inv_skill",
                plugin_state={
                    "success": True,
                    "id": "anthropics-skills-pdf",
                    "skill_id": "anthropics-skills-pdf",
                    "title": "PDF Processing Guide",
                    "content": body,
                    "hasResources": True,
                },
            )
        )
        result = next(e for e in events if e.get("type") == "tool_result")
        self.assertEqual(result["state"]["content"], body)
        self.assertEqual(result["content"], body)
        self.assertNotIn("Ove…", result["content"][-20:] if len(result["content"]) < 50 else "")
        self.assertGreater(len(result["content"]), 1000)

    def test_execute_code_started_wire_has_full_code_despite_truncated_preview(self) -> None:
        full_code = "from reportlab.lib.pagesizes import A4\n" + ("# c\n" * 800)
        # Lossy preview as journal would store after compact + policy
        preview = json.dumps(
            {
                "code": full_code[:200] + "…",
                "code_chars": len(full_code),
                "code_truncated": True,
                "language": "python",
                "description": "生成PDF",
            },
            ensure_ascii=False,
        )
        proj, events = _collect()
        proj.project_started(
            ToolStarted(
                tool_name="execute_code",
                arguments_preview=preview,
                invocation_id="inv_code",
                plugin_state={
                    "code": full_code,
                    "language": "python",
                    "description": "生成PDF",
                    "executionEnv": "sandbox",
                    "success": True,
                },
            )
        )
        started = next(e for e in events if e.get("type") == "tool_started")
        args = json.loads(started["arguments"])
        wire_code = args.get("code") or args.get("Code") or ""
        # FieldMapper may rstrip trailing newline; body must be complete
        self.assertTrue(wire_code.startswith("from reportlab.lib.pagesizes import A4"))
        self.assertGreater(len(wire_code), 3000)
        self.assertIn("# c\n# c", wire_code)
        # Seed tool_state for streaming card (full code from plugin_state)
        states = [e for e in events if e.get("type") == "tool_state"]
        self.assertTrue(states)
        self.assertEqual(states[0]["state"]["code"], full_code)

    def test_execute_code_failed_result_keeps_code(self) -> None:
        full_code = 'print("符合""不符合")\n'  # intentional bad quotes
        proj, events = _collect()
        proj.project_started(
            ToolStarted(
                tool_name="execute_code",
                arguments_preview='{"code":"print…","language":"python"}',
                invocation_id="inv_err",
                plugin_state={"code": full_code, "language": "python"},
            )
        )
        events.clear()
        proj.project_invoked(
            ToolInvoked(
                tool_name="execute_code",
                arguments_preview='{"code":"print…","language":"python"}',
                result_preview="SyntaxError: invalid syntax. Perhaps you forgot a comma?",
                ok=False,
                error="SyntaxError: invalid syntax. Perhaps you forgot a comma?",
                invocation_id="inv_err",
                plugin_state={
                    "success": False,
                    "code": full_code,
                    "language": "python",
                    "stderr": "SyntaxError: invalid syntax",
                    "exitCode": 1,
                    "error": "SyntaxError: invalid syntax. Perhaps you forgot a comma?",
                },
            )
        )
        result = next(e for e in events if e.get("type") == "tool_result")
        self.assertEqual(result["state"]["code"], full_code)
        self.assertFalse(result["state"]["success"])
        self.assertIn("SyntaxError", result.get("error") or "")

    def test_run_command_keeps_full_command(self) -> None:
        cmd = (
            "mkdir -p /mnt/data/fonts && curl -L -o /mnt/data/fonts/Noto.ttf "
            '"https://github.com/example/font.ttf"'
        )
        proj, events = _collect()
        proj.project_started(
            ToolStarted(
                tool_name="run_command",
                arguments_preview=json.dumps(
                    {"command": cmd, "description": "Download font", "timeout": 30}
                ),
                invocation_id="inv_cmd",
                plugin_state={
                    "command": cmd,
                    "description": "Download font",
                    "executionEnv": "sandbox",
                },
            )
        )
        started = next(e for e in events if e.get("type") == "tool_started")
        args = json.loads(started["arguments"])
        self.assertEqual(args["command"], cmd)
        events.clear()
        proj.project_invoked(
            ToolInvoked(
                tool_name="run_command",
                arguments_preview='{"command":"mkdir…"}',
                result_preview="task timed out",
                ok=False,
                error="task timed out",
                invocation_id="inv_cmd",
                plugin_state={
                    "success": False,
                    "command": cmd,
                    "error": "task timed out",
                    "stderr": "task timed out\n",
                    "exitCode": 1,
                    "executionEnv": "sandbox",
                },
            )
        )
        result = next(e for e in events if e.get("type") == "tool_result")
        self.assertEqual(result["state"]["command"], cmd)


if __name__ == "__main__":
    unittest.main()
