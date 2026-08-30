"""OpenAI-compatible gateway bridge tests."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.runs.legacy_adapter import RegistryRunAdapter
from gateway.runs.session import RunRegistry, RunSession, RunStatus, run_dedup_key
from lca.infrastructure.observability.journal.live_tail import LiveTail
from lca.infrastructure.openai_compat import (
    extract_json_schema_format,
    normalize_chat_messages,
    normalize_responses_input,
    resolve_upstream_model,
)
from tests.support.gateway_app import create_scripted_app
from tests.support.gateway_scripted import ScriptedLLMResolver


class TestOpenAiCompatGateway(unittest.TestCase):
    def test_list_models_is_lca_ui_catalog(self) -> None:
        client = TestClient(create_scripted_app(RunRegistry(), llm_resolver=ScriptedLLMResolver()))
        response = client.get("/v1/models")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["data"]]
        # Per PR-9 + PR-10 cordis-creator mode, LCA_UI_MODELS = (solo, team, auto, cordis-creator)
        self.assertEqual(ids, ["solo", "team", "auto", "cordis-creator"])

    def test_chat_completions_housekeeper_passthrough(self) -> None:
        registry = RunRegistry()
        with (
            TestClient(create_scripted_app(registry, llm_resolver=ScriptedLLMResolver())) as client,
            patch(
                "gateway.openai_housekeeping.create_simple_completion",
                new=AsyncMock(
                    return_value=("topic title", {"prompt_tokens": 1, "completion_tokens": 2})
                ),
            ),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "solo",
                    "stream": False,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["choices"][0]["message"]["content"],
            "topic title",
        )
        self.assertEqual(registry.status_counts().get("running", 0), 0)

    def test_streamed_mode_id_does_not_start_agent_run(self) -> None:
        """ADR-0100: stream=true with a catalog id is housekeeping, not POST /runs."""
        registry = RunRegistry()
        app = create_scripted_app(registry, llm_resolver=ScriptedLLMResolver())
        spy = AsyncMock()
        app.state.run_port.create_and_dispatch = spy
        with (
            TestClient(app) as client,
            patch(
                "gateway.openai_housekeeping.create_simple_completion",
                new=AsyncMock(
                    return_value=("topic title", {"prompt_tokens": 1, "completion_tokens": 2})
                ),
            ),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "solo",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        spy.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        body = response.content.decode("utf-8")
        self.assertIn("chat.completion.chunk", body)
        self.assertIn("topic title", body)
        self.assertEqual(registry.status_counts().get("running", 0), 0)

    def test_chat_completions_without_llm_returns_503(self) -> None:
        registry = RunRegistry()

        class _Unavailable:
            def is_available(self) -> bool:
                return False

            def resolve(self, *, mode: str | None = None):
                raise RuntimeError("unavailable")

        app = create_app(run_port=RegistryRunAdapter(registry))
        if getattr(app.state, "ctx", None) is not None:
            app.state.ctx.provide("llm_resolver", _Unavailable())
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "solo",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        self.assertEqual(response.status_code, 503)

    def test_unbooted_compat_endpoints_return_503(self) -> None:
        """Missing lifespan context is an availability error, never a server error."""
        client = TestClient(create_app(run_port=RegistryRunAdapter(RunRegistry())))
        for path, payload in (
            ("/v1/embeddings", {"model": "text-embedding-3-small", "input": "hello"}),
            ("/v1/responses", {"model": "solo", "input": "hello"}),
        ):
            with self.subTest(path=path):
                self.assertEqual(client.post(path, json=payload).status_code, 503)


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
            tail=LiveTail(),
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
            tail=LiveTail(),
            question="hello",
            user_text="hello",
            mode="solo",
        )
        session.status = RunStatus.RUNNING
        registry.put(session)
        session.status = RunStatus.COMPLETED
        registry.clear_inflight(session)
        self.assertIsNone(registry.find_inflight_run(user_text="hello", mode="solo"))

    def test_prune_drops_old_terminal_sessions(self) -> None:
        registry = RunRegistry(max_terminal=2, terminal_ttl_s=60)
        for i, status in enumerate(
            (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED, RunStatus.RUNNING)
        ):
            session = RunSession(
                run_id=f"run_{i}",
                trace_id=f"t{i}",
                jsonl_path=registry.jsonl_path_for(f"run_{i}"),
                tail=LiveTail(),
                question="q",
                user_text=f"q{i}",
                mode="solo",
                status=status,
                closed_at=100.0 if status is not RunStatus.RUNNING else None,
            )
            registry.put(session)
        dropped = registry.prune(now=1000.0)
        self.assertGreaterEqual(dropped, 3)
        self.assertIsNone(registry.get("run_0"))
        self.assertIsNotNone(registry.get("run_3"))

    def test_prune_keeps_fresh_terminal_within_cap(self) -> None:
        registry = RunRegistry(max_terminal=8, terminal_ttl_s=3600)
        session = RunSession(
            run_id="run_fresh",
            trace_id="t",
            jsonl_path=registry.jsonl_path_for("run_fresh"),
            tail=LiveTail(),
            question="q",
            user_text="q",
            mode="solo",
            status=RunStatus.COMPLETED,
            closed_at=900.0,
        )
        registry.put(session)
        assert registry.prune(now=1000.0) == 0
        self.assertIs(registry.get("run_fresh"), session)


class TestOpenAiStructuredHelpers(unittest.TestCase):
    def test_normalize_responses_input_string(self) -> None:
        messages = normalize_responses_input("hello")
        self.assertEqual(messages, [{"role": "user", "content": "hello"}])

    def test_normalize_responses_input_maps_developer_to_system(self) -> None:
        messages = normalize_responses_input(
            [{"role": "developer", "content": "be concise"}],
        )
        self.assertEqual(messages, [{"role": "system", "content": "be concise"}])

    def test_normalize_chat_messages_maps_developer_to_system(self) -> None:
        messages = normalize_chat_messages(
            [
                {"role": "developer", "content": "housekeeper rules"},
                {"role": "user", "content": "hello"},
            ],
        )
        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "housekeeper rules"},
                {"role": "user", "content": "hello"},
            ],
        )

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

    def test_resolve_embedding_model_does_not_use_chat_id(self) -> None:
        from lca.infrastructure.openai_compat import resolve_embedding_model

        self.assertNotEqual(resolve_embedding_model("solo"), resolve_upstream_model("solo"))
        self.assertEqual(resolve_embedding_model("text-embedding-3-small"), "text-embedding-v3")


class TestOpenAiEmbeddingsEndpoint(unittest.TestCase):
    def test_embeddings_create_returns_vectors(self) -> None:
        with (
            TestClient(
                create_scripted_app(RunRegistry(), llm_resolver=ScriptedLLMResolver())
            ) as client,
            patch(
                "gateway.openai_endpoints.create_embeddings",
                new=AsyncMock(
                    return_value={
                        "object": "list",
                        "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                        "model": "text-embedding-3-small",
                        "usage": {"prompt_tokens": 2, "total_tokens": 2},
                    }
                ),
            ),
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
    def test_responses_without_schema_is_housekeeper(self) -> None:
        """`/v1/responses` must wrap chat output into a Responses envelope.

        LobeHub's `handleResponseAPIMode` parses `object: "response"` and rejects
        `chat.completion` shapes — so a plain chat completion must be re-emitted
        as a Responses object (with `output_text` populated) regardless of
        whether `response_format` was supplied.
        """
        registry = RunRegistry()
        with (
            TestClient(create_scripted_app(registry, llm_resolver=ScriptedLLMResolver())) as client,
            patch(
                "gateway.openai_housekeeping.create_simple_completion",
                return_value=("ok", {}),
            ),
        ):
            response = client.post(
                "/v1/responses",
                json={
                    "model": "solo",
                    "stream": False,
                    "input": [{"role": "user", "content": "hello via responses"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["object"], "response")
        self.assertEqual(body["output_text"], "ok")

    def test_responses_create_returns_output_text(self) -> None:
        registry = RunRegistry()
        with (
            TestClient(create_scripted_app(registry, llm_resolver=ScriptedLLMResolver())) as client,
            patch(
                "gateway.openai_endpoints.create_structured_completion",
                return_value=(
                    '{"satisfied": true}',
                    {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                ),
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

    def test_responses_create_no_response_format_wraps_into_response_envelope(self) -> None:
        """Title / mini-helper calls must come back as `object: response`.

        Regression: previously `/v1/responses` (no `response_format`) delegated
        straight to chat completions and returned `object: chat.completion`,
        which broke LobeHub's `handleResponseAPIMode` parser and silently
        dropped auto-generated topic titles.
        """
        registry = RunRegistry()
        with (
            TestClient(create_scripted_app(registry, llm_resolver=ScriptedLLMResolver())) as client,
            patch(
                "gateway.openai_endpoints.passthrough_responses_completion",
                new=AsyncMock(
                    return_value=__import__(
                        "starlette.responses", fromlist=["JSONResponse"]
                    ).JSONResponse(
                        {
                            "id": "resp_test",
                            "object": "response",
                            "status": "completed",
                            "output_text": "工作区检查",
                            "output": [
                                {
                                    "id": "msg_test",
                                    "type": "message",
                                    "role": "assistant",
                                    "status": "completed",
                                    "content": [{"type": "output_text", "text": "工作区检查"}],
                                }
                            ],
                        },
                        headers={"Access-Control-Allow-Origin": "*"},
                    )
                ),
            ),
        ):
            response = client.post(
                "/v1/responses",
                json={"model": "solo", "input": "summarize this"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object"], "response")
        self.assertEqual(payload["output_text"], "工作区检查")

    def test_responses_missing_schema_without_user_message_returns_400(self) -> None:
        with TestClient(
            create_scripted_app(RunRegistry(), llm_resolver=ScriptedLLMResolver())
        ) as client:
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
