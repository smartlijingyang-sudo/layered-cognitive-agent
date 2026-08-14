"""Factory plugin_state — LobeHub card fields come from tool_ui_state, not gateway."""

from __future__ import annotations

import unittest
from typing import Any, ClassVar

from gateway.runs.wire import WIRE
from lca.contracts.models.core.decision import Observation
from lca.layer1_cognitive.body.tool_ui_state import (
    build_invoked_plugin_state,
    build_started_plugin_state,
)


def _obs(payload: dict[str, Any], *, ok: bool = True, error: str = "") -> Observation:
    return Observation(observation_id="obs_test", success=ok, payload=payload, error=error)


class TestFactoryPluginState(unittest.TestCase):
    def test_execute_code_started_has_language_and_code(self) -> None:
        state = build_started_plugin_state(
            "execute_code", {"code": "print(1)", "language": "python"}
        )
        self.assertEqual(state["language"], "python")
        self.assertEqual(state["code"], "print(1)")
        self.assertNotIn("success", state)

    def test_run_command_started_has_command(self) -> None:
        state = build_started_plugin_state("run_command", {"command": "ls -la"})
        self.assertEqual(state["command"], "ls -la")

    def test_list_files_invoked_keeps_guest_shape(self) -> None:
        guest = {
            "success": True,
            "files": [{"name": "main.py", "isDirectory": False, "path": "/mnt/data/main.py"}],
            "totalCount": 1,
        }
        state = build_invoked_plugin_state("list_files", {}, _obs({"state": guest}))
        self.assertTrue(state["success"])
        self.assertEqual(state["totalCount"], 1)
        self.assertEqual(state["files"][0]["name"], "main.py")

    def test_read_file_invoked_keeps_content(self) -> None:
        guest = {
            "success": True,
            "path": "/mnt/data/test.py",
            "content": "print('hello')\n",
            "charCount": 14,
            "filename": "test.py",
            "fileType": "text",
        }
        state = build_invoked_plugin_state("read_file", {}, _obs({"state": guest}))
        self.assertEqual(state["content"], "print('hello')\n")
        self.assertEqual(state["filename"], "test.py")

    def test_execute_code_invoked_keeps_output(self) -> None:
        guest = {"success": True, "language": "python", "output": "42\n", "stderr": ""}
        state = build_invoked_plugin_state("execute_code", {}, _obs({"state": guest}))
        self.assertEqual(state["output"], "42\n")
        self.assertEqual(state["language"], "python")

    def test_failed_tool_includes_error(self) -> None:
        guest = {"success": False, "error": "permission denied"}
        state = build_invoked_plugin_state(
            "read_file", {}, _obs({"state": guest}, ok=False, error="permission denied")
        )
        self.assertFalse(state["success"])
        self.assertEqual(state["error"], "permission denied")


class TestWireCoversFactoryTools(unittest.TestCase):
    EXPECTED_TOOLS: ClassVar[frozenset[str]] = frozenset(
        {
            "activate_skill",
            "run_skill_script",
            "read_skill_reference",
            "search_skill",
            "import_skill",
            "search",
            "askUserQuestion",
            "executeCode",
            "runCommand",
            "listFiles",
            "readFile",
            "writeFile",
            "editFile",
            "searchFiles",
            "moveFiles",
            "grepContent",
            "globFiles",
            "getCommandOutput",
            "killCommand",
            "exportFile",
        }
    )

    def test_all_expected_tools_have_coordinates(self) -> None:
        missing = self.EXPECTED_TOOLS - set(WIRE)
        self.assertEqual(missing, set())

    def test_sandbox_tools_share_identifier(self) -> None:
        for name in (
            "executeCode",
            "runCommand",
            "listFiles",
            "readFile",
            "writeFile",
        ):
            self.assertEqual(WIRE[name][0], "lobe-cloud-sandbox")
