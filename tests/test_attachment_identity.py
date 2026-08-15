"""Attachment identity plane — LobeHub files_info alignment."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.attachment import AttachmentRecord
from lca.contracts.protocols import AttachmentIdentity
from lca.layer0_infra.attachment import (
    FileStoreAttachmentIdentity,
    get_attachment_policy,
    reset_attachment_settings_for_tests,
)
from lca.layer0_infra.attachment.files_info import FilesInfoDocument
from lca.layer0_infra.attachment.layout import AttachmentLayout
from lca.layer0_infra.attachment.settings import AttachmentPolicyDocument
from lca.layer0_infra.file_store import LocalFileStore


class TestAttachmentPolicy(unittest.TestCase):
    def setUp(self) -> None:
        reset_attachment_settings_for_tests()

    def test_policy_loads_and_validates(self) -> None:
        policy = get_attachment_policy()
        self.assertIsInstance(policy, AttachmentPolicyDocument)
        self.assertEqual(policy.inbox_dir, ".lca/inbox")
        self.assertIn("<!-- SYSTEM CONTEXT", policy.system_context_open_prefix)

    def test_inline_rules_cover_text_and_known_extensions(self) -> None:
        policy = get_attachment_policy()
        self.assertTrue(policy.allows_inline("text/csv", "report.csv"))
        self.assertTrue(policy.allows_inline("application/json", "a.json"))
        self.assertTrue(policy.allows_inline("text/plain", "notes.md"))
        self.assertFalse(policy.allows_inline("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "x.docx"))
        self.assertFalse(policy.allows_inline("image/png", "chart.png"))


class TestAttachmentLayout(unittest.TestCase):
    def test_relative_file_sanitizes_run_and_name(self) -> None:
        policy = get_attachment_policy()
        layout = AttachmentLayout(policy)
        path = layout.relative_file("run/unsafe:abc", "../etc/passwd")
        self.assertNotIn("..", path)
        self.assertTrue(path.startswith(".lca/inbox/run-unsafe-abc/"))
        self.assertTrue(path.endswith("passwd"))

    def test_absolute_file_joins_root(self) -> None:
        policy = get_attachment_policy()
        layout = AttachmentLayout(policy)
        path = layout.absolute_file("/home/sandbox-user", "run_42", "report.md")
        self.assertEqual(path, "/home/sandbox-user/.lca/inbox/run_42/report.md")


class TestFilesInfoDocument(unittest.TestCase):
    def test_empty_records_render_empty_string(self) -> None:
        doc = FilesInfoDocument.from_records([])
        self.assertEqual(doc.render(), "")

    def test_document_emits_lobehub_files_info_block(self) -> None:
        records = [
            AttachmentRecord(
                attachment_id="a1",
                name="report.md",
                mime_type="text/markdown",
                size_bytes=10,
                url="/files/a1",
                content="# title",
            )
        ]
        rendered = FilesInfoDocument.from_records(records).render()
        self.assertIn("<!-- SYSTEM CONTEXT (NOT PART OF USER QUERY) -->", rendered)
        self.assertIn("<files_info>", rendered)
        self.assertIn("here are user upload files", rendered)
        self.assertIn('name="report.md"', rendered)
        self.assertIn("# title", rendered)
        self.assertIn("<!-- END SYSTEM CONTEXT -->", rendered)


class TestFileStoreAttachmentIdentity(unittest.TestCase):
    def setUp(self) -> None:
        reset_attachment_settings_for_tests()
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(root=Path(self._tmp.name))
        self.identity = FileStoreAttachmentIdentity(self.store)
        self.addCleanup(self._tmp.cleanup)

    def test_implements_protocol(self) -> None:
        self.assertIsInstance(self.identity, AttachmentIdentity)

    def test_compose_question_includes_files_info(self) -> None:
        meta = self.store.put(data=b"hello", name="report.md", mime_type="text/markdown")
        question = self.identity.compose_question("分析这个报告", (meta.attachment_id,))
        self.assertIn("分析这个报告", question)
        self.assertIn("<files_info>", question)
        self.assertIn("report.md", question)

    def test_compose_question_without_attachments_is_plain(self) -> None:
        question = self.identity.compose_question("继续", ())
        self.assertEqual(question, "继续")
        self.assertNotIn("<files_info>", question)

    def test_stage_payload_uses_inbox_path(self) -> None:
        meta = self.store.put(data=b"hello", name="report.md", mime_type="text/markdown")
        payload = self.identity.stage_payload("run_42", (meta.attachment_id,))
        self.assertEqual(payload, {".lca/inbox/run_42/report.md": b"hello"})

    def test_stage_payload_never_writes_to_machine_root(self) -> None:
        meta = self.store.put(data=b"hello", name="report.md", mime_type="text/markdown")
        payload = self.identity.stage_payload("run_42", (meta.attachment_id,))
        for key in payload:
            self.assertFalse(key.startswith("/"))
            self.assertNotIn("/home/", key)

    def test_listed_paths_isolated_per_run(self) -> None:
        meta = self.store.put(data=b"hello", name="report.md", mime_type="text/markdown")
        paths_a = self.identity.listed_paths("/home/sandbox-user", "run_a", (meta.attachment_id,))
        paths_b = self.identity.listed_paths("/home/sandbox-user", "run_b", (meta.attachment_id,))
        self.assertNotEqual(paths_a, paths_b)
        self.assertTrue(paths_a[0].startswith("/home/sandbox-user/.lca/inbox/run_a/"))
        self.assertTrue(paths_b[0].startswith("/home/sandbox-user/.lca/inbox/run_b/"))

    def test_unknown_attachment_ids_are_skipped(self) -> None:
        question = self.identity.compose_question("继续", ("nope",))
        self.assertEqual(question, "继续")
        payload = self.identity.stage_payload("run_x", ("nope",))
        self.assertEqual(payload, {})


if __name__ == "__main__":
    unittest.main()
