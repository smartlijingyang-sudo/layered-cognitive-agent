"""LobeHub tool wire mapping + timeline pipeline alignment tests."""

from __future__ import annotations

import unittest

from gateway.lobehub_bridge.lobehub_adapter import (
    resolve_tool_wire,
    tool_result_content,
    transform_tool_arguments,
    wire_tool_name,
)
from gateway.lobehub_bridge.lobehub_adapter.protocol import (
    LOBE_SKILLS_ID,
    LOBE_WEB_BROWSING_ID,
    SKILLS_API_ACTIVATE,
    SKILLS_API_EXEC,
    WEB_BROWSING_API_SEARCH,
)
from gateway.timeline import LobeHubSSEAdapter, TimelineProjection
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    RunScope,
    SandboxOutputDelta,
    StampedEvent,
    ToolInvoked,
    ToolStarted,
)


def _stamped(seq: int, event: object) -> StampedEvent:
    return StampedEvent(
        seq=seq,
        ts=float(seq),
        scope=RunScope(trace_id="t", run_id="r"),
        event=event,
    )


def _project_and_adapt(
    stamped: StampedEvent,
    proj: TimelineProjection,
    adapter: LobeHubSSEAdapter,
) -> list[dict]:
    """Run a single stamped event through projection → adapter."""
    out: list[dict] = []
    for domain_event in proj.project(stamped):
        out.extend(adapter.adapt(domain_event))
    return out


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


class TestTimelineToolWire(unittest.TestCase):
    """Tool cards projected via TimelineProjection + LobeHubSSEAdapter."""

    def test_tool_start_wire_name(self) -> None:
        proj = TimelineProjection()
        adapter = LobeHubSSEAdapter()
        evs = _project_and_adapt(
            _stamped(
                1,
                ToolStarted(
                    tool_name="activate_skill",
                    arguments_preview='{"skill_id":"demo-skill"}',
                    invocation_id="inv-1",
                ),
            ),
            proj,
            adapter,
        )
        start = next(e for e in evs if e["type"] == "tool.start")
        self.assertEqual(start["tool_call_id"], "call_inv-1")
        self.assertEqual(
            start["wire_name"],
            wire_tool_name(LOBE_SKILLS_ID, SKILLS_API_ACTIVATE),
        )

    def test_tool_end_has_state(self) -> None:
        proj = TimelineProjection()
        adapter = LobeHubSSEAdapter()
        _project_and_adapt(
            _stamped(
                1,
                ToolStarted(
                    tool_name="run_skill_script",
                    arguments_preview='{"command":"echo hi"}',
                    invocation_id="inv-2",
                ),
            ),
            proj,
            adapter,
        )
        evs = _project_and_adapt(
            _stamped(
                2,
                ToolInvoked(
                    tool_name="run_skill_script",
                    ok=True,
                    latency_ms=10,
                    invocation_id="inv-2",
                    arguments_preview='{"command":"echo hi"}',
                    result_preview='{"stdout":"hi\\n","exit_code":0}',
                ),
            ),
            proj,
            adapter,
        )
        end = next(e for e in evs if e["type"] == "tool.end")
        self.assertEqual(end["tool_call_id"], "call_inv-2")
        self.assertIn("state", end)
        self.assertTrue(end["ok"])

    def test_web_search_plugin_state(self) -> None:
        proj = TimelineProjection()
        adapter = LobeHubSSEAdapter()
        _project_and_adapt(
            _stamped(
                1,
                ToolStarted(
                    tool_name="web_search",
                    arguments_preview='{"query":"today news"}',
                    invocation_id="inv-ws",
                ),
            ),
            proj,
            adapter,
        )
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
        evs = _project_and_adapt(
            _stamped(
                2,
                ToolInvoked(
                    tool_name="web_search",
                    ok=True,
                    latency_ms=120,
                    invocation_id="inv-ws",
                    arguments_preview='{"query":"today news"}',
                    result_preview='{"text":"truncated summary"}',
                    plugin_state=plugin_state,
                ),
            ),
            proj,
            adapter,
        )
        end = next(e for e in evs if e["type"] == "tool.end")
        self.assertEqual(end["state"]["resultNumbers"], 2)
        self.assertEqual(end["state"]["results"][0]["url"], "https://a.example/news")

    def test_sandbox_output_delta(self) -> None:
        proj = TimelineProjection()
        adapter = LobeHubSSEAdapter()
        _project_and_adapt(
            _stamped(
                1,
                ToolStarted(
                    tool_name="execute_code",
                    arguments_preview='{"code":"print(1)","language":"python"}',
                    invocation_id="inv-3",
                ),
            ),
            proj,
            adapter,
        )
        evs = _project_and_adapt(
            _stamped(
                2,
                SandboxOutputDelta(invocation_id="inv-3", stream="stdout", text_delta="1\n", seq=1),
            ),
            proj,
            adapter,
        )
        delta = next(e for e in evs if e["type"] == "tool.delta")
        self.assertEqual(delta["state"]["stdout"], "1\n")
        self.assertEqual(delta["state"]["code"], "print(1)")
        self.assertEqual(delta["text"], "1\n")

    def test_run_end_after_tool(self) -> None:
        proj = TimelineProjection()
        adapter = LobeHubSSEAdapter()
        types: list[str] = []
        start_evs = _project_and_adapt(
            _stamped(
                1,
                ToolStarted(
                    tool_name="run_skill_script",
                    arguments_preview='{"command":"ls"}',
                    invocation_id="inv-9",
                ),
            ),
            proj,
            adapter,
        )
        types.extend(e["type"] for e in start_evs)
        self.assertIn("____", start_evs[0]["wire_name"])
        types.extend(
            e["type"]
            for e in _project_and_adapt(
                _stamped(
                    2,
                    AgentRunFinished(status="completed", output_text="done", steps=1),
                ),
                proj,
                adapter,
            )
        )
        self.assertIn("tool.start", types)
        self.assertEqual(types[-1], "run.end")

    def test_failed_run_end(self) -> None:
        proj = TimelineProjection()
        adapter = LobeHubSSEAdapter()
        evs = _project_and_adapt(
            _stamped(
                1,
                AgentRunFinished(
                    status="failed",
                    output_text="",
                    error="content inspection failed",
                    steps=1,
                ),
            ),
            proj,
            adapter,
        )
        end = next(e for e in evs if e["type"] == "run.end")
        self.assertEqual(end["status"], "failed")
        self.assertIn("content inspection", end["error"])


if __name__ == "__main__":
    unittest.main()
