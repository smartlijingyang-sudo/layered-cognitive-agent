"""LobeHub tool wire mapping + OpenAI projector alignment tests."""

from __future__ import annotations

import json
import unittest

from gateway.lobehub_bridge.tool_wire import (
    LOBE_SKILLS_ID,
    LOBE_WEB_BROWSING_ID,
    SKILLS_API_ACTIVATE,
    SKILLS_API_EXEC,
    WEB_BROWSING_API_SEARCH,
    resolve_tool_wire,
    tool_result_content,
    transform_tool_arguments,
    wire_tool_name,
)
from gateway.projection.openai_sse import OpenAISSEProjector, assert_openai_finish_invariant


class TestToolWireRegistry(unittest.TestCase):
    def test_activate_skill_wire_name(self) -> None:
        spec = resolve_tool_wire("activate_skill", '{"skill_id":"anthropics-skills-xlsx"}')
        assert spec is not None
        self.assertEqual(spec.wire_name, wire_tool_name(LOBE_SKILLS_ID, SKILLS_API_ACTIVATE))
        args = transform_tool_arguments(spec, '{"skill_id":"anthropics-skills-xlsx"}')
        self.assertIn('"name": "anthropics-skills-xlsx"', args)

    def test_run_skill_script_maps_to_exec_script(self) -> None:
        spec = resolve_tool_wire("run_skill_script", '{"command":"python analyze.py"}')
        assert spec is not None
        self.assertEqual(spec.api_name, SKILLS_API_EXEC)
        args = transform_tool_arguments(spec, '{"command":"python analyze.py"}')
        self.assertIn("python analyze.py", args)

    def test_import_skill_market_identifier(self) -> None:
        spec = resolve_tool_wire("import_skill", '{"identifier":"foo.bar"}')
        assert spec is not None
        self.assertEqual(spec.api_name, "importFromMarket")

    def test_web_search_wire_name(self) -> None:
        spec = resolve_tool_wire("web_search", '{"query":"today news"}')
        assert spec is not None
        self.assertEqual(
            spec.wire_name,
            wire_tool_name(LOBE_WEB_BROWSING_ID, WEB_BROWSING_API_SEARCH),
        )

    def test_activate_skill_content_extraction(self) -> None:
        raw = '{"text": "# Skill: demo\\n\\nBody here", "skill_id": "demo"}'
        content = tool_result_content(raw, ok=True, error="", lca_tool_name="activate_skill")
        self.assertTrue(content.startswith("# Skill: demo"))


class TestJournalProjectorToolWire(unittest.TestCase):
    def test_tool_started_emits_lca_extension_not_openai_tool_calls(self) -> None:
        projector = OpenAISSEProjector(chat_id="chatcmpl-x", model="solo")
        frame = (
            "id: 1\nevent: ToolStarted\n"
            'data: {"schema":"journal.v1","seq":1,"ts":1.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"ToolStarted","event":{"tool_name":"activate_skill",'
            '"arguments_preview":"{\\"skill_id\\":\\"demo-skill\\"}","invocation_id":"inv-1"}}\n\n'
        )
        chunks = projector.project_frame(frame)
        self.assertTrue(any("lca" in c for c in chunks))
        lca_chunk = next(c for c in chunks if "lca" in c)
        event = lca_chunk["lca"]["events"][0]
        self.assertEqual(event["type"], "tool_started")
        self.assertEqual(event["tool_call_id"], "call_inv-1")
        self.assertEqual(
            event["wire_name"],
            wire_tool_name(LOBE_SKILLS_ID, SKILLS_API_ACTIVATE),
        )
        delta = chunks[0]["choices"][0].get("delta") or {}
        self.assertNotIn("tool_calls", delta)

    def test_tool_invoked_emits_lca_extension_not_markdown(self) -> None:
        projector = OpenAISSEProjector(chat_id="chatcmpl-x", model="solo")
        start = (
            "id: 1\nevent: ToolStarted\n"
            'data: {"schema":"journal.v1","seq":1,"ts":1.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"ToolStarted","event":{"tool_name":"run_skill_script",'
            '"arguments_preview":"{\\"command\\":\\"echo hi\\"}","invocation_id":"inv-2"}}\n\n'
        )
        projector.project_frame(start)
        finish = (
            "id: 2\nevent: ToolInvoked\n"
            'data: {"schema":"journal.v1","seq":2,"ts":2.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"ToolInvoked","event":{"tool_name":"run_skill_script","ok":true,'
            '"latency_ms":10,"invocation_id":"inv-2","arguments_preview":"{\\"command\\":\\"echo hi\\"}",'
            '"result_preview":"{\\"stdout\\":\\"hi\\\\n\\",\\"exit_code\\":0}"}}\n\n'
        )
        chunks = projector.project_frame(finish)
        self.assertTrue(any("lca" in c for c in chunks))
        lca_chunk = next(c for c in chunks if "lca" in c)
        event = lca_chunk["lca"]["events"][0]
        self.assertEqual(event["type"], "tool_result")
        self.assertEqual(event["tool_call_id"], "call_inv-2")
        self.assertIn("state", event)

    def test_web_search_uses_plugin_state_not_truncated_preview(self) -> None:
        projector = OpenAISSEProjector(chat_id="chatcmpl-x", model="solo")
        start = (
            "id: 1\nevent: ToolStarted\n"
            'data: {"schema":"journal.v1","seq":1,"ts":1.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"ToolStarted","event":{"tool_name":"web_search",'
            '"arguments_preview":"{\\"query\\":\\"today news\\"}","invocation_id":"inv-ws"}}\n\n'
        )
        projector.project_frame(start)
        plugin_state = {
            "query": "today news",
            "resultNumbers": 2,
            "results": [
                {"title": "Headline A", "url": "https://a.example/news", "content": "snippet"},
                {"title": "Headline B", "url": "https://b.example/news", "content": "snippet"},
            ],
            "costTime": 120,
            "success": True,
        }
        finish_record = {
            "schema": "journal.v1",
            "seq": 2,
            "ts": 2.0,
            "scope": {
                "trace_id": "t",
                "run_id": "r",
                "parent_run_id": "",
                "delegation_id": "",
                "agent_role": "助手",
            },
            "event_type": "ToolInvoked",
            "event": {
                "tool_name": "web_search",
                "ok": True,
                "latency_ms": 120,
                "invocation_id": "inv-ws",
                "arguments_preview": '{"query":"today news"}',
                "result_preview": '{"text":"truncated summary"}',
                "plugin_state": plugin_state,
            },
        }
        finish = (
            f"id: 2\nevent: ToolInvoked\ndata: {json.dumps(finish_record, ensure_ascii=False)}\n\n"
        )
        chunks = projector.project_frame(finish)
        lca_chunk = next(c for c in chunks if "lca" in c)
        event = lca_chunk["lca"]["events"][0]
        self.assertEqual(event["state"]["resultNumbers"], 2)
        self.assertEqual(len(event["state"]["results"]), 2)
        self.assertEqual(event["state"]["results"][0]["url"], "https://a.example/news")

    def test_sandbox_output_delta_emits_tool_state(self) -> None:
        projector = OpenAISSEProjector(chat_id="chatcmpl-x", model="solo")
        start = (
            "id: 1\nevent: ToolStarted\n"
            'data: {"schema":"journal.v1","seq":1,"ts":1.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"ToolStarted","event":{"tool_name":"execute_code",'
            '"arguments_preview":"{\\"code\\":\\"print(1)\\",\\"language\\":\\"python\\"}","invocation_id":"inv-3"}}\n\n'
        )
        projector.project_frame(start)
        delta = (
            "id: 2\nevent: SandboxOutputDelta\n"
            'data: {"schema":"journal.v1","seq":2,"ts":2.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"SandboxOutputDelta","event":{"invocation_id":"inv-3","stream":"stdout",'
            '"text_delta":"1\\n","seq":1}}\n\n'
        )
        chunks = projector.project_frame(delta)
        event = chunks[0]["lca"]["events"][0]
        self.assertEqual(event["type"], "tool_state")
        self.assertEqual(event["state"]["stdout"], "1\n")
        self.assertEqual(event["state"]["code"], "print(1)")
        self.assertEqual(event.get("content"), "1\n")

    def test_tool_stream_only_ends_with_stop(self) -> None:
        projector = OpenAISSEProjector(chat_id="chatcmpl-x", model="solo")
        chunks: list[dict] = []
        tool_frame = (
            "id: 1\nevent: ToolStarted\n"
            'data: {"schema":"journal.v1","seq":1,"ts":1.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"ToolStarted","event":{"tool_name":"run_skill_script",'
            '"arguments_preview":"{\\"command\\":\\"ls\\"}","invocation_id":"inv-9"}}\n\n'
        )
        chunks.extend(projector.project_frame(tool_frame))
        finish_frame = (
            "id: 2\nevent: AgentRunFinished\n"
            'data: {"schema":"journal.v1","seq":2,"ts":2.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"AgentRunFinished","event":{"status":"completed","output_text":"done","steps":1}}\n\n'
        )
        chunks.extend(projector.project_frame(finish_frame))
        assert_openai_finish_invariant(chunks)
        lca_start = next(c["lca"]["events"][0] for c in chunks if "lca" in c and c["lca"]["events"])
        self.assertEqual(lca_start["type"], "tool_started")
        self.assertIn("____", lca_start["wire_name"])

    def test_failed_run_emits_run_error_event(self) -> None:
        projector = OpenAISSEProjector(chat_id="chatcmpl-x", model="solo")
        finish_frame = (
            "id: 1\nevent: AgentRunFinished\n"
            'data: {"schema":"journal.v1","seq":1,"ts":1.0,'
            '"scope":{"trace_id":"t","run_id":"r","parent_run_id":"","delegation_id":"","agent_role":"助手"},'
            '"event_type":"AgentRunFinished","event":{"status":"failed","output_text":"",'
            '"error":"content inspection failed","steps":1}}\n\n'
        )
        chunks = projector.project_frame(finish_frame)
        error_events = [
            e
            for c in chunks
            if "lca" in c
            for e in c["lca"]["events"]
            if e.get("type") == "run_error"
        ]
        self.assertEqual(len(error_events), 1)
        self.assertIn("content inspection", error_events[0]["message"])


if __name__ == "__main__":
    unittest.main()
