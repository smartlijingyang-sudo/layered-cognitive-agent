"""OpenAI-compatible gateway bridge tests."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.lobehub_bridge.parser import extract_user_question
from gateway.mode_catalog import resolve_lca_mode
from gateway.openai_structured_llm import (
    extract_json_schema_format,
    normalize_responses_input,
    resolve_upstream_model,
)
from gateway.run_registry import RunRegistry, RunSession, RunStatus, run_dedup_key
from tests.support.gateway_scripted import ScriptedLLMResolver



class TestOpenAiCompatGateway(unittest.TestCase):
    def test_list_models_includes_solo_and_team(self) -> None:
        client = TestClient(create_app(RunRegistry(), llm_resolver=ScriptedLLMResolver()))
        response = client.get("/v1/models")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["data"]}
        self.assertIn("solo", ids)
        self.assertIn("team", ids)

    def test_chat_completions_non_stream_requires_timeline_stream(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "solo",
                "stream": False,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "timeline_stream_required")

    def test_chat_completions_stream_is_timeline_v1(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "solo",
                "stream": True,
                "messages": [{"role": "user", "content": "stream probe"}],
            },
        ) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("x-lca-stream"), "timeline.v1")
            buffer = ""
            saw_run_end = False
            started = time.monotonic()
            for chunk in response.iter_bytes():
                buffer += chunk.decode("utf-8")
                if "event: run.end" in buffer:
                    saw_run_end = True
                    break
                if time.monotonic() - started > 30:
                    break
        self.assertTrue(saw_run_end)

    def test_chat_completions_without_llm_returns_503(self) -> None:
        registry = RunRegistry()
        with patch("gateway.llm_resolver.llm_credentials", return_value=(None, None, None)):
            client = TestClient(create_app(registry))
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "solo",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        self.assertEqual(response.status_code, 503)


class TestRunRegistryDedup(unittest.TestCase):
    def test_run_dedup_key_normalizes_whitespace(self) -> None:
        a = run_dedup_key(user_text="  hello   world ", mode="solo")
        b = run_dedup_key(user_text="hello world", mode="solo")
        self.assertEqual(a, b)

    def test_run_dedup_key_ignores_attachment_prefix_in_question(self) -> None:
        """Dedup uses user_text only — not composed question with attachment blocks."""
        a = run_dedup_key(user_text="今天有什么新闻", mode="solo")
        b = run_dedup_key(
            user_text="今天有什么新闻",
            mode="solo",
            attachment_ids=("att_1",),
        )
        self.assertNotEqual(a, b)

    def test_find_inflight_run_returns_active_session(self) -> None:
        registry = RunRegistry()
        session = RunSession(
            run_id="run_test",
            trace_id="trace_test",
            jsonl_path=registry.jsonl_path_for("run_test"),
            hub=object(),  # type: ignore[arg-type]
            question="今天有什么新闻",
            user_text="今天有什么新闻",
            mode="solo",
        )
        session.status = RunStatus.RUNNING
        registry.put(session)
        found = registry.find_inflight_run(user_text="今天有什么新闻", mode="solo")
        self.assertIs(found, session)

    def test_clear_inflight_after_completion(self) -> None:
        registry = RunRegistry()
        session = RunSession(
            run_id="run_test",
            trace_id="trace_test",
            jsonl_path=registry.jsonl_path_for("run_test"),
            hub=object(),  # type: ignore[arg-type]
            question="hello",
            user_text="hello",
            mode="solo",
        )
        session.status = RunStatus.RUNNING
        registry.put(session)
        session.status = RunStatus.COMPLETED
        registry.clear_inflight(session)
        self.assertIsNone(registry.find_inflight_run(user_text="hello", mode="solo"))


class TestOpenAiStructuredHelpers(unittest.TestCase):
    def test_normalize_responses_input_string(self) -> None:
        messages = normalize_responses_input("hello")
        self.assertEqual(messages, [{"role": "user", "content": "hello"}])

    def test_extract_json_schema_format(self) -> None:
        body = {
            "text": {
                "format": {
                    "type": "json_schema",
                    "strict": True,
                    "name": "FeedbackSatisfaction",
                    "schema": {"type": "object"},
                }
            }
        }
        fmt = extract_json_schema_format(body)
        self.assertIsNotNone(fmt)
        assert fmt is not None
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["json_schema"]["name"], "FeedbackSatisfaction")

    def test_resolve_upstream_model_maps_lca_modes(self) -> None:
        with patch.dict("os.environ", {"LLM_MODEL": "qwen3.7-plus"}, clear=False):
            self.assertEqual(resolve_upstream_model("solo"), "qwen3.7-plus")
        self.assertEqual(resolve_upstream_model("gpt-5.4-mini"), "gpt-5.4-mini")


class TestOpenAiEmbeddingsEndpoint(unittest.TestCase):
    def test_embeddings_create_returns_vectors(self) -> None:
        client = TestClient(create_app(RunRegistry(), llm_resolver=ScriptedLLMResolver()))
        with patch(
            "gateway.openai_compat_api.create_embeddings",
            return_value={
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        ):
            response = client.post(
                "/v1/embeddings",
                json={"model": "text-embedding-3-small", "input": "hello"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "list")
        self.assertEqual(len(payload["data"]), 1)


class TestOpenAiResponsesEndpoint(unittest.TestCase):
    def test_responses_without_schema_routes_to_lca_chat(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
        response = client.post(
            "/v1/responses",
            json={
                "model": "solo",
                "stream": False,
                "input": [{"role": "user", "content": "hello via responses"}],
            },
        )
        # Agent path requires timeline stream
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "timeline_stream_required")

    def test_responses_create_returns_output_text(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
        with patch(
            "gateway.openai_compat_api.create_structured_completion",
            return_value=(
                '{"satisfied": true}',
                {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            ),
        ):
            response = client.post(
                "/v1/responses",
                json={
                    "model": "gpt-5.4-mini",
                    "input": [{"role": "user", "content": "great answer"}],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "FeedbackSatisfaction",
                            "schema": {"type": "object"},
                        }
                    },
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "response")
        self.assertIn("satisfied", payload["output_text"])

    def test_responses_missing_schema_without_user_message_returns_400(self) -> None:
        client = TestClient(create_app(RunRegistry(), llm_resolver=ScriptedLLMResolver()))
        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5.4-mini",
                "input": [],
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
