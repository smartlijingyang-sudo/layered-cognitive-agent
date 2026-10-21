"""console 投影的字段展开守卫 —— LLM / Tool / Decision 关键字段必须可读。

之前渲染把 prompt_preview / response_preview 藏在 Verbosity.VERBOSE 后面，
arguments / output_text / files / rationale_preview / response_text 根本不渲染。
这一组测试断言核心调试字段在 standard verbosity 下就出现。
"""

from __future__ import annotations

import pytest

from lca.contracts.models.observability.journal.journal import (
    DecisionMade,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    ToolInvoked,
)
from lca.infrastructure.observability.adapters.policy import Verbosity
from lca.infrastructure.observability.journal.console.fields import (
    INDENT,
    join_parts,
    labeled,
    mapping_repr,
    truncate,
)
from lca.infrastructure.observability.journal.console.projector import ConsoleJournalProjector

_SCOPE = RunScope(trace_id="t", run_id="r")
_TS = 2_000_000.0


def _stamped(seq: int, event: object) -> StampedEvent:
    return StampedEvent(seq=seq, ts=_TS, scope=_SCOPE, event=event)  # type: ignore[arg-type]


@pytest.fixture
def projector() -> ConsoleJournalProjector:
    return ConsoleJournalProjector(verbosity=Verbosity.STANDARD)


# ── LlmCallCompleted ──────────────────────────────────────────


def test_llm_renders_tokens_when_present(projector: ConsoleJournalProjector) -> None:
    event = LlmCallCompleted(
        model="qwen3.7-plus",
        latency_ms=1430,
        prompt_tokens=412,
        completion_tokens=88,
    )
    line = projector._render_llm_completed(_stamped(1, event), event)
    assert "qwen3.7-plus" in line
    assert "1430ms" in line
    assert "tokens 412/88" in line


def test_llm_renders_reasoning_preview(projector: ConsoleJournalProjector) -> None:
    event = LlmCallCompleted(
        model="qwen3.7-plus",
        latency_ms=1430,
        reasoning_preview="The user asked about phase graph compilation.",
    )
    line = projector._render_llm_completed(_stamped(1, event), event)
    assert "think:" in line
    assert "phase graph compilation" in line


def test_llm_multiline_reasoning_continuation_indented(projector: ConsoleJournalProjector) -> None:
    event = LlmCallCompleted(
        model="qwen3.7-plus",
        latency_ms=1430,
        reasoning_preview="line one\nline two\nline three",
    )
    line = projector._render_llm_completed(_stamped(1, event), event)
    think_block = line.split("\n", 1)[1]  # 跳过 "llm.chat ..." 主行
    think_head, *rest = think_block.splitlines()
    assert think_head.startswith(f"{INDENT}think: line one")
    for cont in rest:
        # 续行起点缩进必须能让 ": line" 对齐 think_head 的 ": line"
        assert cont.startswith(INDENT + " " * 6)


def test_llm_marks_failure(projector: ConsoleJournalProjector) -> None:
    event = LlmCallCompleted(model="qwen3.7-plus", latency_ms=500, ok=False)
    line = projector._render_llm_completed(_stamped(1, event), event)
    assert "FAIL" in line


def test_llm_verbose_unlocks_prompt_and_response() -> None:
    proj_v = ConsoleJournalProjector(verbosity=Verbosity.VERBOSE)
    event = LlmCallCompleted(
        model="qwen3.7-plus",
        latency_ms=1430,
        prompt_preview="explain phase graph",
        response_preview="Yes, the plan is compiled.",
    )
    line = proj_v._render_llm_completed(_stamped(1, event), event)
    assert "prompt:" in line
    assert "explain phase graph" in line
    assert "response:" in line
    assert "Yes, the plan is compiled." in line


# ── ToolInvoked ──────────────────────────────────────────


def test_tool_renders_arguments(projector: ConsoleJournalProjector) -> None:
    event = ToolInvoked(
        tool_name="bash",
        latency_ms=12,
        arguments={"command": "ls bundles/"},
        output_text="base.yaml\ncoding-agent-tools.yaml",
    )
    line = projector._render_tool_invoked(_stamped(1, event), event)
    assert "bash" in line
    assert "ok" in line
    assert "args:" in line
    assert "ls bundles/" in line
    assert "output:" in line
    assert "base.yaml" in line


def test_tool_renders_evidence_ref_when_no_inline_output(
    projector: ConsoleJournalProjector,
) -> None:
    from lca.contracts.observability.evidence.evidence import EvidenceRef

    event = ToolInvoked(
        tool_name="bash",
        latency_ms=12,
        arguments={"command": "ls"},
        output_ref=EvidenceRef(digest="abc123def4567890"),
    )
    line = projector._render_tool_invoked(_stamped(1, event), event)
    assert "<evidence:sha256:abc123def456>" in line


def test_tool_renders_files(projector: ConsoleJournalProjector) -> None:
    event = ToolInvoked(
        tool_name="file_write",
        latency_ms=12,
        arguments={"path": "/tmp/x.yaml"},  # noqa: S108
        files=(
            {"path": "/tmp/a.yaml", "size": 100},  # noqa: S108
            {"path": "/tmp/b.yaml", "size": 200},  # noqa: S108
        ),
    )
    line = projector._render_tool_invoked(_stamped(1, event), event)
    assert "files:" in line
    assert "/tmp/a.yaml" in line  # noqa: S108
    assert "/tmp/b.yaml" in line  # noqa: S108


def test_tool_renders_error_on_failure(projector: ConsoleJournalProjector) -> None:
    event = ToolInvoked(
        tool_name="bash",
        latency_ms=1204,
        arguments={"command": "rm -rf /"},
        ok=False,
        error="Permission denied",
    )
    line = projector._render_tool_invoked(_stamped(1, event), event)
    assert "FAIL" in line
    assert "error:" in line
    assert "Permission denied" in line


def test_tool_truncates_long_output(projector: ConsoleJournalProjector) -> None:
    long_output = "x" * 800
    event = ToolInvoked(tool_name="bash", latency_ms=12, output_text=long_output)
    line = projector._render_tool_invoked(_stamped(1, event), event)
    assert "..." in line
    assert len(line) < 600  # truncation applies


# ── DecisionMade ──────────────────────────────────────────


def test_decision_renders_action_and_confidence(projector: ConsoleJournalProjector) -> None:
    event = DecisionMade(
        step=4,
        action_type="RESPOND",
        tool_name="",
        confidence=0.94,
        rationale_preview="The phase graph compiled successfully.",
    )
    line = projector._render_decision_made(_stamped(1, event), event)
    assert "RESPOND" in line
    assert "confidence=0.94" in line
    assert "rationale:" in line


def test_decision_renders_response_text(projector: ConsoleJournalProjector) -> None:
    event = DecisionMade(
        step=4,
        action_type="RESPOND",
        response_text="Yes, the plan is compiled. 6 nodes, 11 edges.",
    )
    line = projector._render_decision_made(_stamped(1, event), event)
    assert "response:" in line
    assert "Yes, the plan is compiled." in line


def test_decision_renders_delegate_target(projector: ConsoleJournalProjector) -> None:
    event = DecisionMade(step=4, action_type="DELEGATE", delegate_target="Alice")
    line = projector._render_decision_made(_stamped(1, event), event)
    assert "DELEGATE" in line
    assert "→ Alice" in line


def test_decision_truncates_long_response(projector: ConsoleJournalProjector) -> None:
    long_resp = "y" * 500
    event = DecisionMade(step=4, action_type="RESPOND", response_text=long_resp)
    line = projector._render_decision_made(_stamped(1, event), event)
    assert "..." in line


# ── fields helpers ──────────────────────────────────────────


def test_labeled_basic() -> None:
    assert labeled("think", "hello") == f"{INDENT}think: hello"


def test_labeled_empty_returns_empty() -> None:
    assert labeled("think", "") == ""


def test_labeled_multiline_aligns_continuation() -> None:
    out = labeled("think", "line one\nline two")
    head, cont = out.splitlines()
    assert head == f"{INDENT}think: line one"
    assert cont.endswith("line two")
    # 续行"line two"的字符起点应与"think:"的字符起点在视觉上对齐
    # head: "    think: line one"  -> "think" 起点 = 4
    # cont: "           line two" -> "line"  起点 = 11 = 4 + len("think: ")
    assert cont.index("line two") - head.index("think") == len("think: ")


def test_truncate_short_unchanged() -> None:
    assert truncate("hello", 10) == "hello"


def test_truncate_over_limit_appends_suffix() -> None:
    result = truncate("hello world", 10)
    assert result.endswith("...")
    assert len(result) == 10
    assert result.startswith("hello")


def test_join_parts_skips_empty() -> None:
    assert join_parts(["a", "", "b"]) == "a · b"


def test_mapping_repr_handles_non_serializable() -> None:
    class Obj:
        def __repr__(self) -> str:
            return "<Obj>"

    text = mapping_repr({"x": Obj()})
    assert "x" in text


# ── record_runtime 兜底 ──────────────────────────────────────────


def test_record_runtime_fallback_on_unknown_category() -> None:
    """record_runtime 收到未知 category 时落 _DEFAULT_KIND（= RuntimeKind.PLUGIN）。

    todo-38 裁决：facade.record() 无 bound Session 时 fail-loud 抛 RuntimeError，
    且生产 run 中工具执行恒有 Session。此处用 cordis e2e 既有的 bind_journal()
    绑定 Session 即是对生产路径的忠实模拟——测试本意是 category→kind 映射，
    必须真实落到 journal 上才能断言。
    """
    from lca.contracts.models.observability.event.event import RuntimeKind
    from lca.infrastructure.observability.facade.facade.facade import (
        _DEFAULT_KIND,
        record_runtime,
    )
    from tests.scenario.cordis.test_cordis_creator_e2e import bind_journal

    assert _DEFAULT_KIND == RuntimeKind.PLUGIN
    with bind_journal() as journal:
        stamped = record_runtime(
            "unknown-category",
            "test.operation",
            plugin="test-plugin",
        )
    assert stamped is not None
    assert stamped.event.kind == RuntimeKind.PLUGIN
    assert len(journal.store.events) == 1
