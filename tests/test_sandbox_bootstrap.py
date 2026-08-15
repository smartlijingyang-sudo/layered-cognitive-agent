"""Tests for sandbox bootstrap and prompt helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.sandbox.bootstrap import (
    SANDBOX_FILES_INIT_MARKER,
    build_workspace_init_command,
    sandbox_output_path,
)
from lca.layer0_infra.sandbox.prompt import format_uploaded_files_prompt, sandbox_uploaded_file_path


class SandboxBootstrapTests(unittest.TestCase):
    def test_workspace_init_creates_root_and_outputs(self) -> None:
        cmd = build_workspace_init_command()
        self.assertIn("/mnt/data", cmd)
        self.assertIn(sandbox_output_path(), cmd)
        self.assertIn("mkdir -p", cmd)

    def test_marker_matches_lobehub(self) -> None:
        self.assertEqual(SANDBOX_FILES_INIT_MARKER, "/mnt/data/.lobe-files-initialized")


class SandboxPromptTests(unittest.TestCase):
    def test_format_uploaded_files_prompt_lists_guest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(tmp))
            meta = store.put(data=b"hello", name="data.csv", mime_type="text/csv")
            text = format_uploaded_files_prompt(store, [meta.attachment_id])
            self.assertIn(sandbox_uploaded_file_path("data.csv"), text)
            self.assertIn("session copies", text)


if __name__ == "__main__":
    unittest.main()
