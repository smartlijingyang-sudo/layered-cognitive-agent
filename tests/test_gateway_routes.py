"""Gateway HTTP 路由冒烟测试。"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.conversation_store import ConversationStore
from gateway.run_registry import RunRegistry


class _HangRunnable:
    async def run(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        await asyncio.Event().wait()


class GatewayRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = RunRegistry()
        self.store = ConversationStore(db_path=self.registry.runs_dir() / "test_conversations.db")
        self.client = TestClient(create_app(registry=self.registry, conversation_store=self.store))

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("llm_available", payload)

    @patch("gateway.run_executor.build_solo_agent", return_value=_HangRunnable())
    def test_create_and_cancel_run(self, _mock_build: Any) -> None:
        create = self.client.post("/runs", json={"question": "hello", "mode": "solo"})
        self.assertEqual(create.status_code, 201)
        run_id = create.json()["run_id"]
        cancel = self.client.post(f"/runs/{run_id}/cancel")
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json()["status"], "canceled")

    def test_conversation_crud(self) -> None:
        created = self.client.post("/conversations", json={"title": "测试会话"})
        self.assertEqual(created.status_code, 201)
        conversation_id = created.json()["conversation_id"]
        listed = self.client.get("/conversations")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(
            any(c["conversation_id"] == conversation_id for c in listed.json()["conversations"])
        )
        detail = self.client.get(f"/conversations/{conversation_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["title"], "测试会话")


if __name__ == "__main__":
    unittest.main()
