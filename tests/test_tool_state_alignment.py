"""State alignment tests — verify LCA tool states match LobeHub frontend expectations.

These tests validate that each tool's state output conforms to the TypeScript
interfaces that LobeHub's builtin tool Render components expect.

Data flow verified:
  sandbox guest script → ComputerOpResult.state → Observation.payload.state
  → ToolInvoked.plugin_state → lca_tool_result_event(state=...)
  → LobeHub frontend Tool card Render

The guest scripts already produce LobeHub-compatible JSON shapes.
These tests ensure the contract stays aligned as either side evolves.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, ClassVar

from gateway.lobehub_bridge.lobehub_adapter import (
    resolve_tool_wire,
)
from gateway.lobehub_bridge.lobehub_adapter.build_state import merge_success_state
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import parse_args_json
from gateway.lobehub_bridge.lobehub_adapter.protocol import LOBE_CLOUD_SANDBOX_ID


class TestFieldMapperDeclarative(unittest.TestCase):
    """Verify FieldMapper produces correct results for declarative transforms."""

    def test_field_mapper_string_fields(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.adapt_arguments import adapt_read_file

        result = adapt_read_file({"path": "/mnt/data/test.py", "startLine": 1, "endLine": 10})
        self.assertEqual(result["path"], "/mnt/data/test.py")
        self.assertEqual(result["startLine"], 1)
        self.assertEqual(result["endLine"], 10)

    def test_field_mapper_skips_empty_strings(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.adapt_arguments import adapt_glob_files

        result = adapt_glob_files({"pattern": "", "directory": "/mnt"})
        self.assertNotIn("pattern", result)
        self.assertEqual(result["directory"], "/mnt")

    def test_field_mapper_bool_fields(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.adapt_arguments import adapt_grep_content

        result = adapt_grep_content({"pattern": "foo", "recursive": True})
        self.assertEqual(result["pattern"], "foo")
        self.assertTrue(result["recursive"])

    def test_field_mapper_list_fields(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.adapt_arguments import adapt_move_files

        ops = [{"source": "/a", "destination": "/b"}]
        result = adapt_move_files({"operations": ops})
        self.assertEqual(result["operations"], ops)


class TestArgTransformCoverage(unittest.TestCase):
    """Every registered tool must have a working arg transform."""

    def test_all_registered_tools_have_working_transforms(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.tool_registry import TOOL_REGISTRY
        from gateway.lobehub_bridge.lobehub_adapter.tool_spec import ToolWireSpec

        for name, entry in TOOL_REGISTRY.items():
            if not isinstance(entry, ToolWireSpec):
                continue  # Skip dynamic factories
            spec = resolve_tool_wire(name)
            assert spec is not None, f"resolve_tool_wire returned None for {name}"
            # Every transform must accept {} and return a dict
            result = spec.transform_args({})
            self.assertIsInstance(result, dict, f"transform_args for {name} returned non-dict")

    def test_all_transforms_produce_json_serializable_output(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.tool_registry import TOOL_REGISTRY
        from gateway.lobehub_bridge.lobehub_adapter.tool_spec import ToolWireSpec

        sample_args = '{"path": "/mnt/data/test.py", "command": "ls -la"}'
        for name, entry in TOOL_REGISTRY.items():
            if not isinstance(entry, ToolWireSpec):
                continue
            result = entry.transform_args(parse_args_json(sample_args))
            json.dumps(result, ensure_ascii=False)  # Must not raise


class TestSandboxStateAlignment(unittest.TestCase):
    """Verify sandbox tool states match LobeHub frontend TypeScript interfaces.

    These tests simulate the data flow:
    1. Guest script produces JSON result (already LobeHub-compatible)
    2. merge_success_state passes it through as pluginState
    3. The resulting state must have the fields LobeHub renderers expect
    """

    def _simulate_plugin_state(
        self, tool_name: str, guest_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Simulate the plugin_state pipeline for a computer tool."""
        spec = resolve_tool_wire(tool_name)
        assert spec is not None
        result_json = json.dumps(guest_result)
        return spec.build_state(
            {}, parse_args_json(result_json), guest_result.get("success", True), ""
        )

    # ── list_files → ListFilesState ──

    def test_list_files_state_has_files_and_total_count(self) -> None:
        """LobeHub ListFilesState: {files: [{name, isDirectory, path?, size?}], totalCount}"""
        guest_result = {
            "success": True,
            "files": [
                {
                    "name": "main.py",
                    "isDirectory": False,
                    "path": "/mnt/data/main.py",
                    "size": 1234,
                },
                {"name": "src", "isDirectory": True, "path": "/mnt/data/src"},
            ],
            "totalCount": 2,
        }
        state = self._simulate_plugin_state("list_files", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(len(state["files"]), 2)
        self.assertEqual(state["totalCount"], 2)
        self.assertEqual(state["files"][0]["name"], "main.py")
        self.assertFalse(state["files"][0]["isDirectory"])

    # ── read_file → ReadFileState ──

    def test_read_file_state_has_content_and_metadata(self) -> None:
        """LobeHub ReadFileState: {content, path, charCount, filename, fileType, startLine?, endLine?}"""
        guest_result = {
            "success": True,
            "path": "/mnt/data/test.py",
            "content": "print('hello')\n",
            "startLine": 1,
            "endLine": 1,
            "totalLines": 10,
            "charCount": 14,
            "totalCharCount": 200,
            "filename": "test.py",
            "fileType": "text",
        }
        state = self._simulate_plugin_state("read_file", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(state["path"], "/mnt/data/test.py")
        self.assertEqual(state["content"], "print('hello')\n")
        self.assertEqual(state["charCount"], 14)
        self.assertEqual(state["filename"], "test.py")
        self.assertEqual(state["fileType"], "text")

    # ── execute_code → ExecuteCodeState ──

    def test_execute_code_state_has_output_and_language(self) -> None:
        """LobeHub ExecuteCodeState: {language, output, stderr, success, exitCode?}"""
        guest_result = {
            "success": True,
            "language": "python",
            "output": "42\n",
            "stderr": "",
        }
        state = self._simulate_plugin_state("execute_code", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(state["language"], "python")
        self.assertEqual(state["output"], "42\n")

    # ── run_command → RunCommandState ──

    def test_run_command_state_has_command_and_output(self) -> None:
        """LobeHub RunCommandState: {command, isBackground, stdout, stderr, exitCode, success}"""
        guest_result = {
            "success": True,
            "stdout": "file1.py\nfile2.py\n",
            "stderr": "",
            "isBackground": False,
            "exitCode": 0,
        }
        args = {"command": "ls -la"}
        spec = resolve_tool_wire("run_command")
        assert spec is not None
        state = spec.build_state(args, guest_result, True, "")
        self.assertTrue(state["success"])
        self.assertEqual(state["stdout"], "file1.py\nfile2.py\n")
        self.assertFalse(state["isBackground"])
        self.assertEqual(state["exitCode"], 0)

    # ── write_file → WriteFileState ──

    def test_write_file_state_has_path_and_success(self) -> None:
        """LobeHub WriteFileState: {path, success}"""
        guest_result = {"success": True, "path": "/mnt/data/output.txt"}
        state = self._simulate_plugin_state("write_file", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(state["path"], "/mnt/data/output.txt")

    # ── grep_content → GrepContentState ──

    def test_grep_content_state_has_matches_and_pattern(self) -> None:
        """LobeHub GrepContentState: {matches, pattern, totalMatches}"""
        guest_result = {
            "success": True,
            "pattern": "def test_",
            "matches": [
                {"path": "/mnt/data/test_a.py", "lineNumber": 5, "content": "def test_alpha():"},
                {"path": "/mnt/data/test_b.py", "lineNumber": 12, "content": "def test_beta():"},
            ],
            "totalMatches": 2,
        }
        state = self._simulate_plugin_state("grep_content", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(state["pattern"], "def test_")
        self.assertEqual(len(state["matches"]), 2)
        self.assertEqual(state["totalMatches"], 2)

    # ── glob_files → GlobFilesState ──

    def test_glob_files_state_has_files_and_pattern(self) -> None:
        """LobeHub GlobFilesState: {files, pattern, totalCount}"""
        guest_result = {
            "success": True,
            "pattern": "**/*.py",
            "files": ["/mnt/data/a.py", "/mnt/data/src/b.py"],
            "totalCount": 2,
        }
        state = self._simulate_plugin_state("glob_files", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(len(state["files"]), 2)
        self.assertEqual(state["totalCount"], 2)

    # ── edit_file → EditFileState ──

    def test_edit_file_state_has_path_and_replacements(self) -> None:
        """LobeHub EditFileState: {path, replacements, diffText?, linesAdded?, linesDeleted?}"""
        guest_result = {
            "success": True,
            "path": "/mnt/data/config.py",
            "replacements": 1,
            "linesAdded": 2,
            "linesDeleted": 1,
        }
        state = self._simulate_plugin_state("edit_file", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(state["path"], "/mnt/data/config.py")
        self.assertEqual(state["replacements"], 1)

    # ── search_files → SearchFilesState ──

    def test_search_files_state_has_results_and_total_count(self) -> None:
        """LobeHub SearchFilesState: {results: [{path, name?, size?, ...}], totalCount}"""
        guest_result = {
            "success": True,
            "results": [
                {"path": "/mnt/data/test.py", "name": "test.py", "size": 500},
            ],
            "totalCount": 1,
        }
        state = self._simulate_plugin_state("search_files", guest_result)
        self.assertTrue(state["success"])
        self.assertEqual(len(state["results"]), 1)
        self.assertEqual(state["totalCount"], 1)

    # ── export_file → ExportFileState ──

    def test_export_file_state_has_download_url(self) -> None:
        """LobeHub ExportFileState: {path, filename, downloadUrl, success, size?}"""
        spec = resolve_tool_wire("export_file")
        assert spec is not None
        guest_result = {
            "success": True,
            "path": "/mnt/data/chart.png",
            "filename": "chart.png",
            "downloadUrl": "https://example.com/files/abc123",
            "size": 45678,
        }
        state = spec.build_state({"path": "/mnt/data/chart.png"}, guest_result, True, "")
        self.assertTrue(state["success"])
        self.assertEqual(state["path"], "/mnt/data/chart.png")
        self.assertEqual(state["filename"], "chart.png")
        self.assertEqual(state["downloadUrl"], "https://example.com/files/abc123")
        self.assertEqual(state["size"], 45678)

    # ── Error case: merge_success_state preserves error ──

    def test_failed_tool_state_includes_error(self) -> None:
        """All tools: failed operations include error message."""
        guest_result = {"success": False, "error": "permission denied"}
        state = merge_success_state({}, guest_result, False, "permission denied")
        self.assertFalse(state["success"])
        self.assertEqual(state["error"], "permission denied")


class TestToolRegistryCompleteness(unittest.TestCase):
    """Verify all expected tools are registered."""

    EXPECTED_TOOLS: ClassVar[frozenset[str]] = frozenset(
        {
            # Skills
            "activate_skill",
            "run_skill_script",
            "read_skill_reference",
            "search_skill",
            "import_skill",
            # Web
            "web_search",
            # User interaction
            "ask_user_question",
            # Cloud sandbox
            "execute_code",
            "run_command",
            "list_files",
            "read_file",
            "write_file",
            "edit_file",
            "search_files",
            "move_files",
            "grep_content",
            "glob_files",
            "get_command_output",
            "kill_command",
            "export_file",
        }
    )

    def test_all_expected_tools_registered(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.tool_registry import TOOL_REGISTRY

        registered = set(TOOL_REGISTRY.keys())
        missing = self.EXPECTED_TOOLS - registered
        self.assertEqual(missing, set(), f"Missing tool registrations: {missing}")

    def test_all_cloud_sandbox_tools_have_correct_identifier(self) -> None:
        from gateway.lobehub_bridge.lobehub_adapter.tool_registry import TOOL_REGISTRY
        from gateway.lobehub_bridge.lobehub_adapter.tool_spec import ToolWireSpec

        sandbox_tools = {
            "execute_code",
            "run_command",
            "list_files",
            "read_file",
            "write_file",
            "edit_file",
            "search_files",
            "move_files",
            "grep_content",
            "glob_files",
            "get_command_output",
            "kill_command",
            "export_file",
        }
        for name in sandbox_tools:
            entry = TOOL_REGISTRY[name]
            assert isinstance(entry, ToolWireSpec)
            self.assertEqual(
                entry.identifier,
                LOBE_CLOUD_SANDBOX_ID,
                f"{name} has wrong identifier: {entry.identifier}",
            )


if __name__ == "__main__":
    unittest.main()
