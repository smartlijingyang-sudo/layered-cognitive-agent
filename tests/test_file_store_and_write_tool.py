"""Phase C: LocalFileStore + WriteFileTool."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.tools.write_file import build_tools as build_write_file_tools


class LocalFileStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_put_get_roundtrip(self) -> None:
        stored = self.store.put(
            data=b"hello world",
            name="notes.txt",
            mime_type="text/plain",
            conversation_id="conv-1",
        )
        self.assertTrue(stored.attachment_id.startswith("file_"))
        self.assertEqual(stored.name, "notes.txt")
        self.assertEqual(stored.size_bytes, 11)
        self.assertTrue(self.store.exists(stored.attachment_id))
        loaded = self.store.get(stored.attachment_id)
        assert loaded is not None
        self.assertEqual(loaded.mime_type, "text/plain")
        self.assertEqual(self.store.read_bytes(stored.attachment_id), b"hello world")

    async def test_write_file_tool_creates_downloadable_product(self) -> None:
        tool = build_write_file_tools(store=self.store)[0]
        self.assertIsNone(tool.validate({"name": "report.md", "content": "# Hi"}))
        obs = await tool.execute(
            {"name": "report.md", "content": "# Hi\n\nbody", "mime_type": "text/markdown"}
        )
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertEqual(obs.payload["name"], "report.md")
        self.assertEqual(obs.payload["mimeType"], "text/markdown")
        self.assertIn("url", obs.payload)
        self.assertTrue(obs.payload["previewable"])
        self.assertNotIn("previewHtml", obs.payload)
        self.assertIn("files", obs.extra)
        attachment_id = str(obs.payload["attachmentId"])
        self.assertEqual(self.store.read_bytes(attachment_id), b"# Hi\n\nbody")

    def test_previewable_matrix_for_products(self) -> None:
        md = self.store.put(data=b"# x", name="a.md", mime_type="text/markdown")
        png = self.store.put(data=b"\x89PNG", name="c.png", mime_type="image/png")
        html = self.store.put(data=b"<html></html>", name="r.html", mime_type="text/html")
        bin_ = self.store.put(data=b"\x00\x01", name="x.bin", mime_type="application/octet-stream")
        self.assertTrue(md.previewable)
        self.assertTrue(png.previewable)
        self.assertTrue(html.previewable)
        self.assertFalse(bin_.previewable)

    def test_html_has_no_text_preview(self) -> None:
        stored = self.store.put(
            data=b"<!DOCTYPE html><html><body>huge</body></html>",
            name="loan_trend.html",
            mime_type="text/html",
        )
        self.assertIsNone(self.store.read_text_preview(stored.attachment_id))

    def test_pdf_is_previewable(self) -> None:
        stored = self.store.put(
            data=b"%PDF-1.4 fake",
            name="report.pdf",
            mime_type="application/pdf",
        )
        self.assertTrue(stored.previewable)

    async def test_write_file_tool_rejects_empty_name(self) -> None:
        tool = build_write_file_tools(store=self.store)[0]
        self.assertIsNotNone(tool.validate({"name": "  ", "content": "x"}))


if __name__ == "__main__":
    unittest.main()
