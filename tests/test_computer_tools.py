"""Computer use — LobeHub cloud-sandbox / Manus parity tests."""

from __future__ import annotations

import json
import unittest

from gateway.lobehub_bridge.cloud_sandbox_wire import CLOUD_SANDBOX_WIRE, LOBE_CLOUD_SANDBOX_ID
from gateway.lobehub_bridge.tool_wire import resolve_tool_wire, wire_tool_name
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


class TestCloudSandboxWire(unittest.TestCase):
    def test_run_command_wire_name(self) -> None:
        spec = resolve_tool_wire(RUN_COMMAND, '{"command":"ls","description":"list"}')
        assert spec is not None
        self.assertEqual(
            spec.wire_name,
            wire_tool_name(LOBE_CLOUD_SANDBOX_ID, "runCommand"),
        )

    def test_all_computer_tools_registered(self) -> None:
        self.assertEqual(len(CLOUD_SANDBOX_WIRE), 13)
        for name in CLOUD_SANDBOX_WIRE:
            self.assertIsNotNone(resolve_tool_wire(name, "{}"))


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
