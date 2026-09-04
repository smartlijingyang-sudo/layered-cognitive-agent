from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from lca.contracts.models.observability.journal_totals import SegmentRecord, StepPhase

# ── 5 原语子记录 ────────────────────────────────────────


@dataclass(frozen=True)
class AttachmentRef:
    """附件引用(上传文件 / 写出文件 / 输出 URL)。

    跨 step 不变: objective / attachments 是 step context 的顶层常量,
    同一 run 内所有 step 共享。
    """

    attachment_id: str
    name: str
    mime_type: str
    size_bytes: int
    url: str = ""
    direction: Literal["upload", "output", "intermediate"] = "upload"


@dataclass(frozen=True)
class StepContext:
    """进入 step 时的状态快照, 上下文链 + 文件累加 + 摘要链。

    - ``objective``: 顶层 objective, 跨 step 不变。
    - ``attachments``: 顶层附件(用户上传), 跨 step 不变。
    - ``prior_summary_chain``: 截至上一 step 的反思摘要链, 末元素 = 上一步反思。
    - ``cumulative_files``: 截至本 step 起始, 已写出文件路径累加。
    """

    objective: str
    attachments: tuple[AttachmentRef, ...] = ()
    prior_summary_chain: tuple[str, ...] = ()
    cumulative_files: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallRecord:
    """一次工具调用的事实记录。

    - ``invocation_id``: 跨 step 唯一, 用于关联 tool_call / tool_result。
    - ``arguments``: 完整参数(可能很大, 由 projector 按需裁剪)。canonical 字段。
    - ``arguments_summary``: **deprecated**(ADR-0185 spec §2.5 P5)。
      人话摘要, < 200 字符, 永远保留。
      保留 1 个 minor 版本以兼容 reader / fold 路径(``step_tree_accumulator`` /
      ``step_grouped_reader`` / ``step_narrative_writer`` / ``safe_executor``
      等);caller 应在 viewer / narrative 渲染时按需从 ``arguments`` 派生,
      不要直接读 ``arguments_summary``。
      delete-when:下个 minor 版本后,或所有 caller 迁移完毕时。
      tracking: ADR-0185 spec §2.5 P5。
    """

    invocation_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_summary: str = ""


@dataclass(frozen=True)
class ToolResult:
    """一次工具调用的结果事实。

    - ``stdout_head``: 前 N 字符(由 writer 决定 N, 默认 500)。
    - ``stdout_chars_total``: 完整 stdout 字符数, 便于 UI 提示"已截断"。
    - ``stderr``: 错误 stderr 完整保留, 成功时为空。
    - ``files_created``: 工具写出的文件路径(由 sandbox adapter 提供)。
    - ``delta_summary``: 人话摘要, 永远保留(< 200 字符)。
    """

    ok: bool
    latency_ms: int
    stdout_head: str = ""
    stdout_chars_total: int = 0
    stdout_truncated: bool = False
    stderr: str = ""
    files_created: tuple[str, ...] = ()
    error: str | None = None
    delta_summary: str = ""


@dataclass(frozen=True)
class ThinkingTrace:
    """LLM 决策的认知事实。

    - ``reasoning``: 模型思维链(由 ``ReasoningDelta`` 累积或
      ``ReasoningCompleted`` 一次给出, writer 端归一)。
    - ``decision``: 决策动作(``use_tool`` / ``respond`` / ``stop`` / ...) 字符,
      不引入枚举类型, 避免跟 ActionType 强绑。
    - ``tool_call``: 决策携带的工具调用(可选)。
    """

    model: str
    latency_ms: int
    reasoning: str = ""
    decision: str = ""
    tool_call: ToolCallRecord | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw_response_preview: str = ""


@dataclass(frozen=True)
class ReflectTrace:
    """step 收尾反思(由 reflect phase 给出, 或 tool_result 自动衍生)。

    - ``summary``: 人话摘要, 进入下一步的 prior_summary_chain。
    - ``verdict``: 可选判定(``ok`` / ``retry`` / ``escalate`` / ...)。
    """

    summary: str
    verdict: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpanRecord:
    """step 内部诊断 span, 折叠 RuntimeObserved / ToolRetryProgress /
    ContextCompacted 等"事件级别"诊断。

    spans 是 step 的子级事实, 不是顶层 envelope 的一等事件。 reader
    可选择默认显隐(由 viewer 决定), 但数据本身始终完整保留。
    """

    kind: str
    started_at: float
    ended_at: float | None = None
    summary: dict[str, Any] = field(default_factory=dict)


# ── 顶层真相:JournalStep ────────────────────────────────


StepOutcome = Literal["ok", "fail", "skip"]


@dataclass(frozen=True)
class JournalStep:
    """一个 step = 一个因果闭环(ADR-0164 草案顶层真相)。

    5 原语穷尽 step 语义:
        context_before → thinking? → tool_call? → tool_result? → reflect?

    不要求每 step 都完整经历 5 原语(例如 perceive-only step 不调 LLM;
    think-only step 不调工具), 任何原语可空。 ``outcome`` 在 close_step
    时由调用方决定, ``None`` 表示 step 尚未闭合。

    spans 承载 step 内部的所有诊断事实(RuntimeObserved /
    ToolRetryProgress / ContextCompacted), 默认折叠, 不抢主线。
    """

    step_id: str
    step_index: int
    phase: StepPhase

    entered_at: float
    exited_at: float | None = None
    duration_ms: int | None = None

    parent_step_id: str | None = None
    subagent_role: str | None = None  # 非 None 表示 sub-agent run 的 step

    context_before: StepContext | None = None
    thinking: ThinkingTrace | None = None
    tool_call: ToolCallRecord | None = None
    tool_result: ToolResult | None = None
    reflect: ReflectTrace | None = None

    spans: tuple[SpanRecord, ...] = ()
    outcome: StepOutcome | None = None
    error: str | None = None
    segments: tuple[SegmentRecord, ...] = ()  # 3.1; ADR-0166 D2


# ── helpers ──────────────────────────────────────────────


def make_step_id(step_index: int, subagent_role: str | None = None) -> str:
    """生成 step_id(全局唯一, 跨 run 不要求, 跨 step 唯一)。

    sub-agent step 用 ``<role>:step_<index>`` 形式区分。
    """
    if subagent_role:
        return f"{subagent_role}:step_{step_index}"
    return f"step_{step_index}"


def compute_duration_ms(entered_at: float, exited_at: float | None) -> int | None:
    """从 epoch 差计算 duration_ms。"""
    if exited_at is None:
        return None
    return max(0, int((exited_at - entered_at) * 1000))


def summarize_step(step: JournalStep) -> str:
    """生成 step 的一行人话摘要, 进入下一步 prior_summary_chain。

    规则: outcome=ok → "ok: <reflect.summary>"  →  phase + 关键动作
          outcome=fail → "fail: <error> @ <phase>"
          未闭合 → "<phase> (in progress)"
    """
    if step.outcome is None:
        return f"{step.phase} (in progress)"
    if step.outcome == "fail":
        err = step.error
        if not err and step.tool_result is not None:
            err = step.tool_result.error
        where = err or "unknown"
        return f"fail @ {step.phase}: {where}"
    if step.reflect is not None and step.reflect.summary:
        return f"ok ({step.phase}): {step.reflect.summary}"
    if step.tool_call is not None:
        return f"ok ({step.phase}): {step.tool_call.name}"
    return f"ok ({step.phase})"


def iter_steps(steps: Sequence[JournalStep]):
    """迭代器(测试用, 保证顺序)。"""
    yield from steps


__all__ = [
    "AttachmentRef",
    "JournalStep",
    "ReflectTrace",
    "SpanRecord",
    "StepContext",
    "StepOutcome",
    "StepPhase",
    "ThinkingTrace",
    "ToolCallRecord",
    "ToolResult",
    "compute_duration_ms",
    "iter_steps",
    "make_step_id",
    "summarize_step",
]
"""Journal Step-Tree —— 顶层真相从事件流升级为 step 树（ADR-0164 草案）。

背景：
    原 ``lca.contracts.models.observability.journal`` 把"事实"建模为
    seq 流水 —— 49 种事件类型平铺, step 边界靠 ``scope.step`` 隐式
    累积, 读者必须自己数 seq 才能拼出"这次跑分几步"。这跟人类认知
    "step = 一个因果闭环" 的天然模型错位。

新模型（ADR-0164 草案）：
    - **顶层真相是 step 树**, 不是 seq 流水。 一个 step 是一个
      因果闭环, 由 5 原语穷尽: 上下文 / 思考 / 工具调用 / 工具结果 / 反思。
    - **seq 降级为 step 的实现细节**, 由 runtime 内部使用, 不出现在
      顶层 envelope。
    - **诊断事件 (RuntimeObserved / ToolRetryProgress / ContextCompacted)**
      折叠为 step.spans, 不再是顶层事件。
    - **LLM/工具事实** 折叠为 step.thinking / step.tool_call /
      step.tool_result, 不再是顶层事件。

闭集从 49 减到 12 —— 仅保留容器 / 协作 / 控制 / 附件 / 插件 / boot
等"事件级别"事实 (沿用 ``journal.py`` 中相应 frozen dataclass)。

本模块不删除 ``journal.py``, 但新增 ``journal_step.py`` 作为新主存储的
数据契约。 旧 ``journal.py`` 中的 ``StampedEvent`` 仅供回放 / 迁移使用,
不再作为 live writer 的产物。
"""
