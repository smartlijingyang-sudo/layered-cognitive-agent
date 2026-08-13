"""Guest computer ops must take JSON params, never interpolate Python literals.

Regression: default read_file emitted ``start_line = null`` and crashed with
``NameError: name 'null' is not defined``. Native LobeHub runJsonScript does not.
"""

from __future__ import annotations

import ast
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from lca.layer0_infra.computer.guest.file_ops import (
    build_edit_file_script,
    build_read_file_script,
    build_write_file_script,
)
from lca.layer0_infra.computer.guest.search_ops import build_grep_content_script
from lca.layer0_infra.computer.parse_result import parse_computer_stdout
from lca.layer0_infra.computer.runtime import ComputerRuntime
from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.sandbox.onlyboxes_artifacts import ARTIFACT_BEGIN
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime, unbind_sandbox_runtime
from lca.layer0_infra.tools.run_finalizer import run_id_scope
from tests.support.inline_sandbox import InlineSandbox

_PY_NULL_ASSIGN = re.compile(r"^\s*\w+\s*=\s*null\s*$", re.MULTILINE)
_PY_BOOL_ASSIGN = re.compile(r"^\s*\w+\s*=\s*(true|false)\s*$", re.MULTILINE)


class TestJsonScriptDoesNotEmitPythonNull(unittest.TestCase):
    def test_default_read_file_compiles_with_omitted_line_range(self) -> None:
        script = build_read_file_script(path="/mnt/data/loan_trend.html")
        ast.parse(script)
        self.assertIsNone(_PY_NULL_ASSIGN.search(script))
        self.assertNotIn("start_line = null", script)
        self.assertNotIn("end_line = null", script)
        self.assertNotIn("__LCA_COMPUTER__", script)

    def test_default_write_and_edit_bools_are_not_json_tokens(self) -> None:
        write = build_write_file_script(
            path="/mnt/data/a.txt", content="x", create_directories=True
        )
        edit = build_edit_file_script(
            path="/mnt/data/a.txt", search="a", replace="b", replace_all=False
        )
        grep = build_grep_content_script(pattern="x", directory="/mnt/data", recursive=True)
        for script in (write, edit, grep):
            ast.parse(script)
            self.assertIsNone(_PY_BOOL_ASSIGN.search(script), script[-200:])

    def test_read_file_returns_content_when_line_range_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "loan_trend.html"
            target.write_text("<html>hello</html>\n", encoding="utf-8")
            script = build_read_file_script(path=str(target))
            buf = io.StringIO()
            with redirect_stdout(buf):
                exec(compile(script, "<guest>", "exec"), {})  # noqa: S102
            payload = parse_computer_stdout(buf.getvalue())
        assert payload is not None
        self.assertTrue(payload["success"])
        self.assertIn("hello", payload["content"])
        self.assertEqual(payload["filename"], "loan_trend.html")

    def test_parse_accepts_native_plain_json_line(self) -> None:
        payload = parse_computer_stdout('noise\n{"success": true, "content": "ok"}\n')
        assert payload is not None
        self.assertEqual(payload["content"], "ok")


class TestReadFileThroughRuntime(IsolatedAsyncioTestCase):
    async def test_default_read_file_returns_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "loan_trend.html"
            target.write_text("<html>loan chart</html>\n", encoding="utf-8")
            store = LocalFileStore(root=Path(tmp) / "files")
            sandbox = InlineSandbox()
            runtime = ComputerRuntime(sandbox=sandbox, store=store)
            rid = "read_file_run"
            await bind_sandbox_runtime(rid, sandbox, store, ())
            try:
                with run_id_scope(rid):
                    result = await runtime.read_file(path=str(target))
            finally:
                await unbind_sandbox_runtime(rid)
            self.assertTrue(result.success, result.error)
            self.assertIn("loan chart", result.content)
            guest = sandbox.session_run_calls[-1][1]
            self.assertNotIn(ARTIFACT_BEGIN, guest)
            self.assertNotIn("start_line = null", guest)


if __name__ == "__main__":
    unittest.main()
