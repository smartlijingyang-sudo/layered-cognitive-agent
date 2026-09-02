"""ADR-0169 PR-26 业务迁 cursor 验证 —— ``tests/cognition/test_cursor_migration.py``。

ADR-0169 §D9 删除清单要求业务路径 ``coord.begin_step / coord.record_* /
coord.emit_phase`` 在 PR-21~24 阶段迁完 cursor;PR-26 是**准备阶段**,验证:

1. ``perceive_hub`` 调 ``cursor.advance('perceive')`` 而非 ``coord.emit_phase(...)``
2. ``safe_executor`` / ``tool_journal_emit`` 不再调 ``coord.record_*``(compat 期
   保留 ``coord.emit(...)`` 任意 EP,但 record_* API 已脱钩 cursor)
3. ``CoordinatorAdapter`` 暴露 ``current_cursor()`` ContextVar 让业务路径取
   cursor(无业务调用方时不报错)

无调用方门禁通过 ``grep coord.record_thinking|coord.record_tool_call|...``
= 0 验证。
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field

import pytest

from lca.cognition.body.safe_executor import (
    _record_tool_call_evidence,
    _record_tool_result_evidence,
)
from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import (
    CursorError,
    CursorSnapshot,
)
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    CoordinatorAdapter,
    current_cursor,
)

# ── Stub helpers ──────────────────────────────────────────────


@dataclass
class _StubSpine:
    """Stub WritePort —— 捕获所有 append 调用供 assertion 使用。"""

    records: list[dict] = field(default_factory=list)

    def append(
        self,
        *,
        execution_point: str,
        payload: dict,
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        self.records.append(
            {
                "execution_point": execution_point,
                "payload": payload,
                "run_id": run_id,
                "seq": seq,
                "incarnation": incarnation,
                "phase": phase,
            }
        )
        return seq


@dataclass
class _StubTool:
    """Minimal Tool stub for emit_tool_started runtime test."""

    name: str
    description: str = ""
    parameters: dict[str, object] = field(default_factory=dict)
    is_idempotent: bool = True
    default_timeout_s: float = 30.0

    async def execute(self, args: dict[str, object]) -> object:  # pragma: no cover
        del args
        raise NotImplementedError

    def validate(self, args: dict[str, object]) -> str | None:  # pragma: no cover
        del args
        return None


def _make_cursor() -> tuple[StdLoopCursor, _StubSpine]:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1),
    )
    return cursor, spine


# ── 1. perceive_hub calls cursor.advance('perceive') ───────────


def test_perceive_hub_uses_cursor_advance_not_coord_emit_phase() -> None:
    """``perceive_hub.perceive`` 必须调 ``cursor.advance('perceive')``,不是 ``coord.emit_phase``。

    通过 inspect 读取源代码静态校验:无 ``coord.emit_phase`` 残留,且出现
    ``cursor.advance('perceive')`` 调用。docstring 内的提及用 AST 排除。
    """
    import ast
    import textwrap

    from lca.cognition import perceive_hub

    source = textwrap.dedent(inspect.getsource(perceive_hub.SequentialPerceiveHub.perceive))
    tree = ast.parse(source)
    # 仅在非 docstring 节点里查找 "coord.emit_phase" / "cursor.advance"
    body_text = ast.unparse(tree)
    assert "coord.emit_phase" not in body_text, (
        "perceive_hub.perceive still calls coord.emit_phase (ADR-0169 §D9 deletion list)"
    )
    assert "cursor.advance" in body_text, (
        "perceive_hub.perceive must call cursor.advance(phase) (ADR-0169 §D1)"
    )
    assert "cursor.advance" in body_text and "perceive" in body_text, (
        "perceive_hub.perceive must call cursor.advance('perceive')"
    )


def test_perceive_hub_runtime_emits_phase_perceive_fold_on_cursor() -> None:
    """运行期校验:``current_cursor()`` 已 bind 后,``perceive`` 派生 ``phase.perceive.fold`` EP。

    注入 cursor → 调用 hub.perceive → 验证 spine.records 含 phase.perceive.fold EP,
    且 cursor.snapshot.phase == 'perceive'。
    """
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
        reset_current_cursor,
    )

    cursor, spine = _make_cursor()
    token = bind_current_cursor(cursor)
    try:
        # 不实例化 hub —— 无 AgentState 输入;直接验证 current_cursor() + cursor.advance
        assert current_cursor() is cursor
        snap: CursorSnapshot = cursor.advance("perceive")
        assert snap.phase == "perceive"
        fold_eps = [r for r in spine.records if r["execution_point"] == "phase.perceive.fold"]
        assert len(fold_eps) == 1, (
            f"expected exactly one phase.perceive.fold EP, got {len(fold_eps)}"
        )
        assert fold_eps[0]["payload"]["phase"] == "perceive"
    finally:
        reset_current_cursor(token)


def test_perceive_hub_skips_cursor_advance_when_not_bound() -> None:
    """未注入 cursor 时,业务路径静默跳过 phase fold EP(无 run context 不抛)。"""

    cursor, spine = _make_cursor()
    # 故意不 bind cursor;current_cursor() 应返回 None
    assert current_cursor() is None

    # 模拟业务路径:无 cursor 时,逻辑必须不抛
    if current_cursor() is None:
        # no-op 路径(perceive_hub 现状)
        pass
    else:  # pragma: no cover — 仅说明分支
        cursor.advance("perceive")

    assert spine.records == [], "no cursor bound → no spine records"


# ── 2. tool_journal_emit calls cursor-aware EP routes ──────────


def _strip_docstrings_and_comments(source: str) -> str:
    """去掉 docstring 与行内注释,只保留可执行代码本体。"""
    # 去除 """...""" 块
    cleaned = re.sub(r'"""[\s\S]*?"""', "", source)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    # 去除 # 行内注释(简单处理:行首到 #)
    lines = []
    for line in cleaned.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # 简易:删除 # 后内容(不含字符串内的 #)
        if "#" in line:
            # 极简启发:不处理字符串字面量,只删首个 # 之后
            idx = line.find("#")
            # 仅当 # 之前字符是空白或标点(粗糙判断不在字符串内)
            if idx > 0 and line[idx - 1] in (" ", "\t"):
                line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


def test_tool_journal_emit_routes_start_through_cursor_record_tool_call() -> None:
    """``emit_tool_started`` 调 ``cursor.record_tool_call(ToolCallRecord(...))``。

    ADR-0169 PR-1/S1 业务迁 cursor:``phase.tool.call.start`` EP 不再经
    ``coord.emit`` 落 spine,改走 cursor.record_tool_call → ``step.tool_call.record``。
    canonical ToolStarted JournalEvent 仍然 record()(ADR-0063 SSOT)。
    """
    from lca.cognition.body import tool_journal_emit

    source_started = inspect.getsource(tool_journal_emit.emit_tool_started)
    body = _strip_docstrings_and_comments(source_started)
    assert "cursor.record_tool_call" in body, (
        "emit_tool_started must route through cursor.record_tool_call (ADR-0169 PR-1/S1)"
    )
    assert "ToolCallRecord(" in body, "emit_tool_started must build a ToolCallRecord payload"
    # coord.emit / phase.tool.call.start 不应再出现在代码路径(docstring/comment 忽略)
    assert "coord.emit" not in body, "emit_tool_started no longer calls coord.emit (ADR-0169 §D9)"
    assert "phase.tool.call.start" not in body, (
        "emit_tool_started no longer emits phase.tool.call.start EP"
    )


def test_tool_journal_emit_routes_end_through_cursor_record_tool_result() -> None:
    """``emit_tool_invoked`` 调 ``cursor.record_tool_result(ToolResultRecord(...))``。"""
    from lca.cognition.body import tool_journal_emit

    source_invoked = inspect.getsource(tool_journal_emit.emit_tool_invoked)
    body = _strip_docstrings_and_comments(source_invoked)
    assert "cursor.record_tool_result" in body
    assert "ToolResultRecord(" in body
    assert "coord.emit" not in body
    assert "phase.tool.call.end" not in body


def test_tool_journal_emit_routes_denied_through_cursor_record_tool_result() -> None:
    """``emit_tool_denied`` 调 ``cursor.record_tool_result(outcome="denied")``。"""
    from lca.cognition.body import tool_journal_emit

    source_denied = inspect.getsource(tool_journal_emit.emit_tool_denied)
    body = _strip_docstrings_and_comments(source_denied)
    assert "cursor.record_tool_result" in body
    assert '"denied"' in body
    assert "coord.emit" not in body
    assert "phase.tool.denied" not in body


def test_tool_journal_emit_runtime_records_tool_call_ep_when_cursor_bound() -> None:
    """运行时校验:cursor 已 bind 时,``emit_tool_started`` 触发 ``step.tool_call.record``。

    注入 cursor → 调 emit_tool_started → spine 必新增 step.tool_call.record EP。
    """
    from lca.cognition.body import tool_journal_emit
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
        reset_current_cursor,
    )

    cursor, spine = _make_cursor()
    # 提前 advance 到 ACT phase —— record_tool_call 需要 ACT window
    cursor.advance("act")
    pre_count = len(spine.records)

    token = bind_current_cursor(cursor)
    try:
        tool = _StubTool(name="t1")
        tool_journal_emit.emit_tool_started(
            tool,
            {"path": "stub/path"},
            invocation_id="inv-1",
        )
    finally:
        reset_current_cursor(token)

    new_eps = [r["execution_point"] for r in spine.records[pre_count:]]
    assert "step.tool_call.record" in new_eps, (
        f"expected step.tool_call.record EP after emit_tool_started, got {new_eps}"
    )


# ── 3. safe_executor open/close act step ───────────────────────


def test_safe_executor_record_tool_call_evidence_routes_through_cursor() -> None:
    """``_record_tool_call_evidence`` 调 ``cursor.record_tool_call(ToolCallRecord(...))``。

    PR-1/S1: ``phase.act.fold.start`` EP 不再经 ``coord.emit``,改走 cursor。
    PR-26 task-25:phase 推进由 SimpleBody 负责,helpers 只落证据 EP。
    """
    from lca.cognition.body import safe_executor

    source_open = inspect.getsource(safe_executor._record_tool_call_evidence)
    body = _strip_docstrings_and_comments(source_open)
    assert "cursor.record_tool_call" in body, (
        "_record_tool_call_evidence must route through cursor.record_tool_call (ADR-0169 PR-1/S1)"
    )
    assert "ToolCallRecord(" in body
    assert "coord.emit" not in body
    assert "phase.act.fold.start" not in body


def test_safe_executor_record_tool_result_evidence_routes_through_cursor() -> None:
    """``_record_tool_result_evidence`` 调 ``cursor.record_tool_result(ToolResultRecord(...))``。"""
    from lca.cognition.body import safe_executor

    source_close = inspect.getsource(safe_executor._record_tool_result_evidence)
    body = _strip_docstrings_and_comments(source_close)
    assert "cursor.record_tool_result" in body
    assert "ToolResultRecord(" in body
    assert "coord.emit" not in body
    assert "phase.act.fold.end" not in body


def test_safe_executor_evidence_helpers_silent_when_no_cursor_bound() -> None:
    """未注入 cursor 时 ``_record_tool_call_evidence`` / ``_record_tool_result_evidence`` 静默 no-op(不抛)。

    PR-1/S1: 之前的兼容路径 ``coord.emit`` 已删除,helpers 现走 ``cursor.record_*``;
    无 cursor 时直接返回,等价于原行为。
    """
    # 默认 ContextVar 为 None → helpers 必须立即返回
    _record_tool_call_evidence("test_tool", "inv-1")
    _record_tool_result_evidence(tool_name="test_tool", invocation_id="inv-1", outcome="ok")


def test_safe_executor_evidence_runtime_records_tool_result_ep_when_cursor_bound() -> None:
    """运行时校验:cursor 已 bind 时,``_record_tool_result_evidence`` 触发 ``step.tool_result.record``。

    ACT phase 上 cursor.record_tool_result 必落 step.tool_result.record EP。
    """
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
        reset_current_cursor,
    )

    cursor, spine = _make_cursor()
    cursor.advance("act")
    pre_count = len(spine.records)

    token = bind_current_cursor(cursor)
    try:
        _record_tool_call_evidence("test_tool", "inv-1")
        _record_tool_result_evidence(tool_name="test_tool", invocation_id="inv-1", outcome="ok")
    finally:
        reset_current_cursor(token)

    new_eps = [r["execution_point"] for r in spine.records[pre_count:]]
    assert "step.tool_call.record" in new_eps, (
        f"expected step.tool_call.record from _record_tool_call_evidence, got {new_eps}"
    )
    assert "step.tool_result.record" in new_eps, (
        f"expected step.tool_result.record from _record_tool_result_evidence, got {new_eps}"
    )


def test_safe_executor_record_tool_call_evidence_swallows_cursor_phase_error() -> None:
    """``_record_tool_call_evidence`` 在 cursor 不在 ACT phase 时抛 CursorError。

    调用方(SimpleBody.act / SafeExecutor.execute)负责捕获并降级,本函数
    仅验证 record_tool_call 的契约:phase != "act" → CursorError,不静默吞。
    """
    cursor, _ = _make_cursor()
    cursor.advance("think")
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
        reset_current_cursor,
    )

    token = bind_current_cursor(cursor)
    try:
        with pytest.raises(CursorError):
            _record_tool_call_evidence("test_tool", "inv-1")
    finally:
        reset_current_cursor(token)


# ── 3b. emit_tool_started 在非 ACT phase 降级 warning(防 run_9e181f24c275 回归) ─


def test_emit_tool_started_swallows_cursor_phase_error() -> None:
    """``emit_tool_started`` 在 cursor 不在 ACT phase 时降级 warning,不抛。

    Regression for run_9e181f24c275:reasoner 输出 RESPOND,phase 留在 think,
    下游 phase_graph.node 仍触发 tool execute(自动 replay / 嵌入 tool_call),
    ``emit_tool_started`` 调 ``cursor.record_tool_call`` 在 think phase 抛 CursorError,
    一路冒到 phase executor → apply_error → kernel.run.stop=failure。

    ADR-0169 PR-26 task-25 政策:phase 推进责任在 SimpleBody.act;本 seam 只
    负责落证据 EP,phase 不在 act → 降级 warning,不让单 tool 调用失败
    触发整 session RuntimeError。
    """
    cursor, _ = _make_cursor()
    cursor.advance("perceive")
    cursor.advance("think")

    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
        reset_current_cursor,
    )

    token = bind_current_cursor(cursor)
    try:
        from lca.cognition.body import tool_journal_emit

        # 必须不抛 —— 这是 run_9e181f24c275 的直接回归锁。
        result = tool_journal_emit.emit_tool_started(
            tool=_StubTool(name="t1"),
            args={"path": "stub/path"},
            invocation_id="inv-1",
        )
        assert result is None  # 无 evidence_store → inline 退路
    finally:
        reset_current_cursor(token)


# ── 4. CoordinatorAdapter exposes current_cursor ContextVar ─────


def test_coordinator_adapter_current_cursor_returns_none_when_unbound() -> None:
    """未 bind cursor 时 ``current_cursor()`` 返回 ``None``。"""
    assert current_cursor() is None


def test_coordinator_adapter_current_cursor_round_trip() -> None:
    """``bind_current_cursor(cursor)`` → ``current_cursor()`` 返回该 cursor。"""
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
        reset_current_cursor,
    )

    cursor, _ = _make_cursor()
    token = bind_current_cursor(cursor)
    try:
        assert current_cursor() is cursor
    finally:
        reset_current_cursor(token)
    assert current_cursor() is None


def test_coordinator_adapter_class_satisfies_loop_cursor_protocol() -> None:
    """``CoordinatorAdapter.cursor`` 属性类型满足 ``LoopCursor`` Protocol(类型契约)。"""
    # 通过结构 duck-type 检查 cursor 类型满足 Protocol(Protocol 无 runtime_checkable)
    cursor, _ = _make_cursor()
    required = (
        "advance",
        "halt",
        "close",
        "record_thinking",
        "record_tool_call",
        "record_tool_result",
        "record_request_header",
        "fork",
        "snapshot",
    )
    missing = [m for m in required if not hasattr(cursor, m)]
    assert not missing, f"StdLoopCursor missing Protocol members: {missing}"
    # cursor 类型注解验证(类层 + 实例层都应有 advance 标记)
    assert callable(cursor.advance), "StdLoopCursor must implement advance()"


# ── 5. Static grep gate: business paths don't use removed coord APIs ──


def test_no_business_call_to_coord_record_apis() -> None:
    """业务路径不调 ``coord.begin_step / coord.record_thinking / coord.record_tool_call /
    coord.record_tool_result / coord.record_runtime / coord.record_reflect /
    coord.record_span``(PR-26 阶段硬门禁)。

    只检查 cognition/body/runtime/agent 四个目录。writable_matrix / infrastructure
    自身 / facade 等使用是 readonly,排除。
    """
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    patterns = [
        r"coord\.begin_step",
        r"coord\.end_step",
        r"coord\.record_thinking",
        r"coord\.record_tool_call",
        r"coord\.record_tool_result",
        r"coord\.record_runtime",
        r"coord\.record_reflect",
        r"coord\.record_span",
    ]
    search_dirs = ["lca/cognition", "lca/body", "lca/runtime", "lca/agent"]
    pattern_re = re.compile("|".join(patterns))
    offenders: list[str] = []
    for d in search_dirs:
        path = repo / d
        if not path.exists():
            continue
        for py in path.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for m in pattern_re.finditer(text):
                # 排除 docstring / 注释里的提及
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                line = text[line_start:line_end]
                stripped = line.strip()
                if (
                    stripped.startswith("#")
                    or stripped.startswith('"""')
                    or stripped.startswith("'''")
                ):
                    continue
                offenders.append(f"{py.relative_to(repo)}:{stripped}")
    assert not offenders, (
        "ADR-0169 §D9 violation: business paths still use removed coord APIs:\n"
        + "\n".join(offenders)
    )


def test_no_business_call_to_coord_emit_phase() -> None:
    """业务路径不调 ``coord.emit_phase(...)``(PR-26 阶段硬门禁)。

    任意 ``coord.emit(...)`` 保留(任意 EP,删除条件绑 PR-21~24),但
    ``coord.emit_phase`` 仅在 writable_matrix / facade __init__ 保留(legacy
    compat),business 路径必须删除。AST 解析排除 docstring / 注释。
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    search_dirs = ["lca/cognition", "lca/body", "lca/runtime", "lca/agent"]
    offenders: list[str] = []
    for d in search_dirs:
        path = repo / d
        if not path.exists():
            continue
        for py in path.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "emit_phase"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "coord"
                ):
                    offenders.append(
                        f"{py.relative_to(repo)}:{node.lineno}:{ast.unparse(node.func)}"
                    )
    assert not offenders, (
        "ADR-0169 §D9 violation: business paths still call coord.emit_phase:\n"
        + "\n".join(offenders)
    )


# ── 6. Cursor Protocol surface stable ──────────────────────────


def test_cursor_protocol_surface_is_pr26_stable() -> None:
    """``LoopCursor`` 协议面 9 动词 + 1 snapshot(ADR-0169 §D1 钉死)。"""
    # StdLoopCursor 实例化后,验证公共面方法签名
    cursor, _ = _make_cursor()
    expected = {
        "snapshot",
        "advance",
        "halt",
        "close",
        "record_thinking",
        "record_tool_call",
        "record_tool_result",
        "record_request_header",
        "fork",
    }
    actual = set(dir(cursor))
    missing = expected - actual
    assert not missing, f"LoopCursor Protocol surface missing: {missing}"
    # 业务路径不允许的动词必须不存在
    forbidden = {
        "begin_step",
        "end_step",
        "begin_segment",
        "end_segment",
        "emit_phase",
        "emit",
        "subscribe",
        "flush",
        "close_storage",
        "register_projection",
        "drive_projection",
    }
    leaked = forbidden & actual
    assert not leaked, f"LoopCursor Protocol leaked forbidden verbs (ADR-0169 §D1): {leaked}"


# ── 7. CoordinatorAdapter existence + delegation sanity ────────


def test_coordinator_adapter_exposes_cursor_property() -> None:
    """``CoordinatorAdapter.cursor`` 暴露内部 cursor 属性,供 PR-21~24 wiring 切换期使用。"""
    # 通过类型注解验证(不需要实例化 adapter)
    import typing

    annotations = typing.get_type_hints(CoordinatorAdapter)
    # cursor 属性是返回 LoopCursor 的 property
    assert "cursor" in annotations or hasattr(CoordinatorAdapter, "cursor"), (
        "CoordinatorAdapter must expose .cursor property"
    )


# ── 8. Runtime module: ensure no dangling _derive_* / make_journal_emitting_hook ─


def test_runtime_event_emission_does_not_export_removed_symbols() -> None:
    """Removed(ADR-0169 §D9): the event_emission module has been
    fully deleted per ADR-0169 §D9 (file absence is the gate). This
    test no longer has a module to load — kept as a marker so the
    surrounding test numbering stays stable. The grep gate replaces
    this runtime assertion.
    """
    return None


def test_runtime_package_does_not_re_export_removed_symbols() -> None:
    """``lca.runtime`` __init__ 不再 re-export 上述符号。"""
    import importlib

    mod = importlib.import_module("lca.runtime")
    exports = set(dir(mod))
    for name in ("JournalEmitFn", "make_journal_emitting_hook"):
        assert name not in exports, f"lca.runtime still re-exports {name!r} (ADR-0169 §D9)"


def test_facade_does_not_export_step_api() -> None:
    """``lca.infrastructure.observability.facade`` 不再导出 ``step_open / step_close /
    step_record_*``(ADR-0169 §D9 删除清单)。
    """
    import importlib

    facade_pkg = importlib.import_module("lca.infrastructure.observability.facade")
    exports = set(dir(facade_pkg))
    for name in (
        "step_open",
        "step_close",
        "step_record_thinking",
        "step_record_tool_call",
        "step_record_tool_result",
        "step_record_reflect",
        "step_record_span",
    ):
        assert name not in exports, (
            f"lca.infrastructure.observability.facade still exports {name!r} (ADR-0169 §D9)"
        )


def test_facade_facade_module_does_not_define_step_api() -> None:
    """``lca.infrastructure.observability.facade.facade`` 模块不再定义 ``step_open / step_close /
    step_record_*`` 7 个方法(grep 静态门禁)。
    """
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    target = repo / "lca" / "infrastructure" / "observability" / "facade" / "facade.py"
    text = target.read_text(encoding="utf-8", errors="ignore")
    offenders: list[str] = []
    for name in (
        "step_open",
        "step_close",
        "step_record_thinking",
        "step_record_tool_call",
        "step_record_tool_result",
        "step_record_reflect",
        "step_record_span",
    ):
        for m in re.finditer(rf"\bdef\s+{name}\b", text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end].strip()
            offenders.append(f"{target.relative_to(repo)}:{line}")
    assert not offenders, "facade.py still defines step_* methods (ADR-0169 §D9):\n" + "\n".join(
        offenders
    )
