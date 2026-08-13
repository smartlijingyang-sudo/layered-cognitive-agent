"""Computer use — LobeHub cloud-sandbox / Manus parity tests."""

from __future__ import annotations

import json
import unittest

from gateway.runs.wire import WIRE, resolve
from lca.layer0_infra.computer.constants import COMPUTER_RESULT_BEGIN, COMPUTER_RESULT_END
from lca.layer0_infra.computer.parse_result import parse_computer_stdout
from lca.layer0_infra.tools.computer.tool_set import (
    EXECUTE_CODE,
    LIST_FILES,
    RUN_COMMAND,
    build_computer_tools,
)
from lca.layer0_infra.tools.default_set import build_default_tools
from tests.support.inline_sandbox import InlineSandbox


class TestComputerParse(unittest.TestCase):
    def test_parse_marker_block(self) -> None:
        payload = {"success": True, "files": []}
        stdout = f"{COMPUTER_RESULT_BEGIN}{json.dumps(payload)}{COMPUTER_RESULT_END}"
        parsed = parse_computer_stdout(stdout)
        assert parsed is not None
        self.assertTrue(parsed["success"])

    def test_parse_prefers_marker_over_trailing_json(self) -> None:
        inner = {"success": True, "via": "marker"}
        stdout = (
            f"{COMPUTER_RESULT_BEGIN}{json.dumps(inner)}{COMPUTER_RESULT_END}\n"
            '{"success": true, "via": "line"}\n'
        )
        parsed = parse_computer_stdout(stdout)
        assert parsed is not None
        self.assertEqual(parsed["via"], "marker")


class TestCloudSandboxWire(unittest.TestCase):
    def test_run_command_wire_name(self) -> None:
        self.assertEqual(resolve(RUN_COMMAND), ("lobe-cloud-sandbox", "runCommand"))

    def test_all_computer_tools_registered(self) -> None:
        sandbox = [name for name, pair in WIRE.items() if pair[0] == "lobe-cloud-sandbox"]
        self.assertEqual(len(sandbox), 13)
        for name in sandbox:
            self.assertIsNotNone(resolve(name))


class TestDefaultToolsComputer(unittest.TestCase):
    def test_includes_computer_tools_when_sandbox(self) -> None:
        sandbox = InlineSandbox()
        names = {t.name for t in build_computer_tools(sandbox=sandbox)}
        self.assertIn(EXECUTE_CODE, names)
        self.assertIn(RUN_COMMAND, names)
        self.assertIn(LIST_FILES, names)

    def test_default_set_prefers_computer_over_legacy(self) -> None:
        from unittest.mock import patch

        with patch("lca.layer0_infra.tools.default_set.resolve_sandbox") as mock:
            mock.return_value = InlineSandbox()
            names = {t.name for t in build_default_tools()}
        self.assertIn("list_files", names)
        self.assertIn("run_skill_script", names)
        self.assertIn("write_file", names)
        self.assertNotIn("sandbox_inspect", names)


class TestBuildComputerObservationFiles(unittest.TestCase):
    """build_computer_observation should pipe generated_files into Observation.extra['files']."""

    def test_files_in_extra_when_generated(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from lca.contracts.models.core.sandbox import SandboxFile
        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.file_store import LocalFileStore
        from lca.layer0_infra.tools.computer.observations import build_computer_observation

        result = ComputerOpResult(
            success=True,
            content="output text",
            state={"output": "output text"},
            generated_files=(
                SandboxFile(name="primes.pdf", mime_type="application/pdf", data=b"%PDF-1.4"),
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=Path(os.path.join(tmpdir, "files")))
            obs = build_computer_observation(
                result, tool_name="execute_code", start=0.0, store=store
            )

        self.assertTrue(obs.success)
        files = (obs.extra or {}).get("files", [])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "primes.pdf")
        self.assertEqual(files[0]["mimeType"], "application/pdf")
        self.assertIn("url", files[0])
        self.assertIn("attachmentId", files[0])
        self.assertTrue(files[0].get("previewable"))
        state = (obs.payload or {}).get("state", {})
        self.assertEqual(state.get("output"), "output text")
        self.assertEqual(state.get("files"), files)

    def test_observation_reuses_runtime_file_parts_without_second_put(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from lca.contracts.models.core.sandbox import SandboxFile
        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.file_store import LocalFileStore
        from lca.layer0_infra.tools.computer.observations import build_computer_observation

        existing = {
            "name": "loan.pdf",
            "mimeType": "application/pdf",
            "sizeBytes": 4,
            "url": "/files/file_already",
            "previewable": True,
            "attachmentId": "file_already",
        }
        result = ComputerOpResult(
            success=True,
            content="ok",
            state={"output": "ok", "files": [existing]},
            generated_files=(
                SandboxFile(name="loan.pdf", mime_type="application/pdf", data=b"%PDF"),
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=Path(os.path.join(tmpdir, "files")))
            obs = build_computer_observation(
                result, tool_name="execute_code", start=0.0, store=store
            )
            self.assertEqual(list(store.root.iterdir()), [])
        files = (obs.extra or {}).get("files", [])
        self.assertEqual(files[0]["url"], "/files/file_already")

    def test_failed_office_mutation_does_not_enter_ledger(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.file_store import LocalFileStore
        from lca.layer0_infra.tools.computer.observations import build_computer_observation
        from lca.layer0_infra.workspace.scope import run_workspace_scope

        existing = {
            "name": "deck.pptx",
            "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "sizeBytes": 9890,
            "url": "/files/file_mid",
            "previewable": False,
            "attachmentId": "file_mid",
        }
        result = ComputerOpResult(
            success=False,
            content="batch failed",
            error="batch failed",
            state={"stdout": '{"success": false}', "files": [existing]},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=Path(os.path.join(tmpdir, "files")))
            with run_workspace_scope("run_fail_harvest", wall_clock_seconds=60) as workspace:
                obs = build_computer_observation(
                    result, tool_name="run_command", start=0.0, store=store
                )
                arts = workspace.artifacts.snapshot().artifacts
        self.assertFalse(obs.success)
        self.assertEqual(len(arts), 0)
        self.assertFalse((obs.extra or {}).get("files"))

    def test_plugin_state_from_nested_state(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.file_store import LocalFileStore
        from lca.layer0_infra.tools.computer.observations import build_computer_observation
        from lca.layer1_cognitive.body.tool_result_preview import tool_plugin_state

        result = ComputerOpResult(
            success=True,
            content="42",
            state={"output": "42", "code": "print(42)", "language": "python", "success": True},
            generated_files=(),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=Path(os.path.join(tmpdir, "files")))
            obs = build_computer_observation(
                result, tool_name="execute_code", start=0.0, store=store
            )
        plugin = tool_plugin_state(obs)
        self.assertEqual(plugin.get("code"), "print(42)")
        self.assertEqual(plugin.get("output"), "42")

    def test_no_files_when_empty(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from lca.layer0_infra.computer.runtime import ComputerOpResult
        from lca.layer0_infra.file_store import LocalFileStore
        from lca.layer0_infra.tools.computer.observations import build_computer_observation

        result = ComputerOpResult(
            success=True,
            content="ok",
            state={},
            generated_files=(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileStore(root=Path(os.path.join(tmpdir, "files")))
            obs = build_computer_observation(
                result, tool_name="execute_code", start=0.0, store=store
            )

        self.assertTrue(obs.success)
        self.assertNotIn("files", obs.extra or {})


if __name__ == "__main__":
    unittest.main()
