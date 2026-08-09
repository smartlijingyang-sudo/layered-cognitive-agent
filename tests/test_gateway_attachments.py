"""Phase C: gateway attachment upload / download / create_run attachment_ids."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.conversation_store import ConversationStore
from gateway.run_registry import RunRegistry
from lca.layer0_infra.file_store import LocalFileStore
from tests.support.gateway_scripted import ScriptedLLMResolver


class GatewayAttachmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.registry = RunRegistry(runs_dir=root / "runs")
        self.store = ConversationStore(db_path=root / "conversations.db")
        self.files = LocalFileStore(root / "files")
        self.client = TestClient(
            create_app(
                registry=self.registry,
                conversation_store=self.store,
                llm_resolver=ScriptedLLMResolver(),
                file_store=self.files,
            )
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_upload_and_download(self) -> None:
        conv = self.client.post("/conversations", json={"title": "files"}).json()
        conversation_id = conv["conversation_id"]
        response = self.client.post(
            f"/conversations/{conversation_id}/attachments",
            files={"file": ("hello.txt", b"hello phase c", "text/plain")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertIn("attachment_id", body)
        self.assertEqual(body["name"], "hello.txt")
        self.assertEqual(body["mime_type"], "text/plain")
        self.assertTrue(body["url"].startswith("/files/"))

        download = self.client.get(body["url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"hello phase c")

        meta = self.client.get(f"{body['url']}/meta")
        self.assertEqual(meta.status_code, 200)
        self.assertEqual(meta.json()["attachment_id"], body["attachment_id"])

    def test_create_run_rejects_unknown_attachment(self) -> None:
        response = self.client.post(
            "/runs",
            json={
                "question": "use file",
                "mode": "solo",
                "attachment_ids": ["file_does_not_exist"],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "unknown_attachment")

    def test_create_run_accepts_known_attachment(self) -> None:
        stored = self.files.put(data=b"spec", name="spec.md", mime_type="text/markdown")
        response = self.client.post(
            "/runs",
            json={
                "question": "summarize the attachment",
                "mode": "solo",
                "attachment_ids": [stored.attachment_id],
            },
        )
        # 201 when LLM available via ScriptedLLMResolver
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn("run_id", response.json())
        session = self.registry.get(response.json()["run_id"])
        assert session is not None
        self.assertEqual(session.attachment_ids, (stored.attachment_id,))
        # Question embeds guest path so the model writes correct open() paths.
        self.assertIn(f"/mnt/data/{stored.name}", session.question)
        self.assertIn("已挂载", session.question)
        self.assertIn("activate_skill", session.question)
        self.assertIn("run_skill_script", session.question)

    def test_create_run_session_stores_attachment_ids(self) -> None:
        from gateway.run_executor import create_run_session

        session = create_run_session(
            self.registry,
            question="q",
            mode="solo",
            attachment_ids=[" file_a ", "", "file_b"],
        )
        self.assertEqual(session.attachment_ids, ("file_a", "file_b"))


if __name__ == "__main__":
    unittest.main()
