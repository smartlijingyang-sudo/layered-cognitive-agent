"""异常归一化 SSOT —— Spine-side canonical form of a Python exception.

ADR-0169 + ADR-2026-09-02-i17-stream-align §B: 不论异常来自装饰器路径
(``instrument_wrap._safe_append``) 还是 transport 兜底路径
(``lifecycle.execute`` 的顶层 ``except``),都必须先归一化成
:class:`ExceptionRecord`,再交给唯一的 :func:`emit_exception_caught`。

ADR-2026-09-03-debug-clarity: 新增 :class:`ErrKind` —— OpenTelemetry-style
异常分类(NETWORK / SSL / CANCELLED / IDLE_TIMEOUT / ...),贯穿 ``asdict()``,
供 ``lca-ops journal exceptions`` / ``debug-run`` 直接分类统计,而不再用
中文 user-facing 文案 ``error_ref`` 当 SSOT。

Traceback 切分由 **按帧数** 替换 **按字节 cap** —— 4 KiB 字节 cap 在深栈 +
网络/SSL 场景下会把**栈底帧**吃掉,而栈底帧正是 provider tier 的人需要的。
改为保留最近 ``_TRACEBACK_FRAME_BUDGET`` 帧(默认 64),栈顶优先、栈底优先
丢弃。frame 数可在 ``exc_to_record(..., frame_budget=...)`` 覆盖。
"""

from __future__ import annotations

import traceback
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_TRACEBACK_FRAME_BUDGET = 64  # frames retained from the most recent
# Legacy alias kept for the i17 stream-align traceback cap ; byte cap was 4096.
# COMPAT(delete-when: ``_traceback_byte_cap`` 全部 reader 升级到 frame budget,
# tracking: ADR-2026-09-03-debug-clarity)
_TRACEBACK_BYTE_CAP = 4096


class ErrKind(str, Enum):
    """OpenTelemetry-style exception kind —— provider/triage categorical。

    与 OpenTelemetry ``semantic_conventions.exception.type`` 同构。
    任何 caller / CLI / UI 投影只对 enum 操作,不接触中文 user-facing 文案。
    """

    UNKNOWN = "unknown"
    NETWORK = "network"  # LLM provider socket 关闭 / DNS / connect refused
    SSL = "ssl"  # TLS 握手 / aiter_lines 中断 / SSLWantReadError
    CANCELLED = "cancelled"  # asyncio.CancelledError 传播
    IDLE_TIMEOUT = "idle_timeout"  # LLM 流式在 idle 超时被 casted
    PROTOCOL = "protocol"  # upstream 4xx/5xx / 模型服务返回格式错
    VALIDATION = "validation"  # 校验 / schema 错误 / 边界类型不匹配
    SANDBOX = "sandbox"  # Body 沙箱执行错
    AUTHORIZATION = "authorization"  # Approval / policy 拒绝
    INTERNAL = "internal"  # 本仓代码缺陷(unexpected exception)


_STDLIB_EXC_BY_KIND: dict[ErrKind, tuple[type[BaseException], ...]] = {
    ErrKind.CANCELLED: (
        __import__("asyncio").CancelledError,
        __import__("asyncio").exceptions.CancelledError,
    ),
    ErrKind.SSL: (
        __import__("ssl").SSLWantReadError,
        __import__("ssl").SSLWantWriteError,
        __import__("ssl").SSLError,
    ),
    ErrKind.NETWORK: (
        ConnectionError,
        ConnectionResetError,
        ConnectionAbortedError,
    ),
    ErrKind.IDLE_TIMEOUT: (TimeoutError,),
}


def classify_exception(exc: BaseException) -> ErrKind:
    """返回基于类型链的 :class:`ErrKind`。

    不可识别的 builtin 异常(KeyError / ValueError / LookupError /
    AttributeError 等业务 bug 信号)默认归为 :attr:`ErrKind.INTERNAL`,
    表示"本仓代码的意外",提示需要修;不挂 :attr:`ErrKind.UNKNOWN`
    的兜底,UNKNOWN 保留给命名启发式也没命中的、提供给 ``_STDLIB_EXC_BY_KIND``
    之外且无任何命名的类型(例如动态生成的 ``RuntimeError("foo")``)。
    """
    cls = type(exc)
    for kind, candidates in _STDLIB_EXC_BY_KIND.items():
        if isinstance(exc, candidates):
            return kind
    name = cls.__name__
    if name == "ReadError":
        return ErrKind.NETWORK
    if name.startswith("SSL"):
        return ErrKind.SSL
    if name.startswith("RemoteProtocolError"):
        return ErrKind.PROTOCOL
    # 业务 builtin 异常 = 本仓 bug 信号
    if cls.__module__ in ("builtins", "exceptions"):
        return ErrKind.INTERNAL
    # 第三方未名异常 = 未知,留出 fall-through
    return ErrKind.UNKNOWN


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Plain ``{file, line, function}`` triple.

    contracts 层不可 import plugins/observability 的 SourceLocation,
    故此处给出等价简化版;字段语义保持一致。如未来需要合并,迁
    SourceLocation 到 contracts 即可。
    """

    file: str
    line: int
    function: str

    def asdict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "function": self.function}


@dataclass(frozen=True, slots=True)
class ExceptionRecord:
    """Spine-side canonical form of a Python exception (SSOT)。

    不论异常在哪个 seam 被捕获,都必须先归一化成 ExceptionRecord,
    再走唯一的 ``emit_exception_caught``。任何 caller 漏字段 = 残废
    event = 没有 sidecar —— 这是历史回归的根因。

    序列化策略:``asdict()`` 直接展开成 dict,SourceLocation 嵌套
    展开成 ``{file, line, function}`` 三键。FileSink 自动 offload。
    """

    boundary: str
    """捕获边界标识 —— ``"lifecycle.execute"`` / ``"phase_graph.node.end"`` 等。"""

    exception_class: str
    """``type(exc).__qualname__``(与 instrument_wrap._exception_payload 对齐)。"""

    exception_message: str
    """``str(exc)``(可能为空)。"""

    traceback_text: str
    """最近 N 帧 ``traceback.format_exception(...)`` 输出,UTF-8 编码。"""

    source_location: SourceLocation | None
    """异常最末帧(file:line:function);``None`` 表示无 ``__traceback__``。"""

    call_frames: tuple[SourceLocation, ...]
    """完整 traceback 链,从最末帧向最早帧。所有帧 file:line 完整保留。"""

    cause_chain: tuple[str, ...]
    """``__cause__`` / ``__context__`` 的类型链(去重,跳过 self)。"""

    err_kind: ErrKind = ErrKind.UNKNOWN
    """OpenTelemetry-style 异常分类,见 :class:`ErrKind`。"""

    run_id: str = ""
    """调用方所在 run_id;空字符串表示 non-run context(boot/shutdown)。"""

    trace_id: str = ""
    """调用方所在 trace_id;空字符串表示 non-run context。"""

    extra: Mapping[str, Any] = field(default_factory=dict)
    """Caller-specific extension fields(透传,不参与 SSOT 归一化)。

    装饰器路径(``instrument_wrap``)会塞反射增强字段
    (``locals_snapshot`` / ``signature_fingerprint`` /
    ``input_params`` / ``output_schema`` / ``docstring_captured`` /
    ``preconditions`` / ``budget_at_entry``);lifecycle 路径不传。
    ``extra`` 不在 :func:`exc_to_record` 里构造 —— 由 caller 在拿到
    record 后通过 ``dataclasses.replace(record, extra={...})`` 注入。
    """

    def asdict(self) -> dict[str, Any]:
        """JSON-serializable dict(用于 EventRecord payload)。

        保留 legacy alias(``exc_type`` / ``reason``)供旧 reader 兼容:
        trace_inspector / spine.producer.failure 等仍然消费旧字段名。
        新 reader 应优先消费 ``exception_class`` / ``exception_message``。
        """
        base: dict[str, Any] = {
            "boundary": self.boundary,
            "exception_class": self.exception_class,
            "exception_message": self.exception_message,
            "traceback_text": self.traceback_text,
            "source_location": self.source_location.asdict()
            if self.source_location is not None
            else None,
            "call_frames": [frame.asdict() for frame in self.call_frames],
            "cause_chain": list(self.cause_chain),
            "err_kind": self.err_kind.value,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            # Legacy fields —— 不要在新 caller 里构造。caller 提供
            # ``extra`` 时同名键会覆盖这些 alias。
            "exc_type": self.exception_class,
            "reason": self.exception_message,
            **dict(self.extra),
        }
        return base


def _frame_to_source_location(frame: Any) -> SourceLocation:
    """Extract ``(file, line, function)`` from a traceback frame.

    Accepts ``traceback.FrameSummary`` (real frame) or any object with
    the same attribute surface (mocks / dataclasses).
    """
    return SourceLocation(
        file=str(getattr(frame, "filename", "") or ""),
        line=int(getattr(frame, "lineno", 0) or 0),
        function=str(getattr(frame, "name", "") or ""),
    )


def _format_traceback_capped(
    exc: BaseException, *, frame_budget: int
) -> tuple[str, tuple[SourceLocation, ...], SourceLocation | None]:
    """Format ``traceback.format_exception(...)`` output capped by frame count.

    Returns ``(traceback_text, call_frames, source_location)``.

    行为契约:

    - 总是先尝试 ``traceback.extract_tb`` 拿全栈;
    - 取栈最末 ``frame_budget`` 帧(栈顶优先,栈底优先丢),重建一个
      ``traceback.TracebackException`` 仅含这些帧,然后 format。
    - 若 ``exc.__traceback__`` 为 ``None``,返回 ``"ValueError: <msg>\n"``
      风格的最小文本 + 空 frames,``source_location=None``。
    """
    tb = exc.__traceback__
    if tb is None:
        msg = f"{type(exc).__qualname__}: {exc}\n"
        return msg, (), None

    all_frames = traceback.extract_tb(tb)
    frames_for_output = all_frames[-frame_budget:] if len(all_frames) > frame_budget else all_frames

    # 重建 ``TracebackException`` 帧集合 —— 不能改原 tb,也不重新 format。
    # 安全做法:对保留下来的帧,用 ``traceback.format_list`` 渲染,
    # 再拼 header + 末帧例外类名 + message。
    formatted_frames = traceback.format_list(frames_for_output)
    text = (
        "Traceback (most recent call last):\n"
        + "".join(formatted_frames)
        + f"{type(exc).__qualname__}: {exc}\n"
    )

    frames_tuple = tuple(_frame_to_source_location(f) for f in all_frames)
    # source_location 始终取 *最末* 帧(file:line of raising site),即使被 cap
    source_location = _frame_to_source_location(all_frames[-1]) if all_frames else None
    return text, frames_tuple, source_location


def exc_to_record(
    exc: BaseException,
    *,
    boundary: str,
    run_id: str = "",
    trace_id: str = "",
    frame_budget: int = _TRACEBACK_FRAME_BUDGET,
) -> ExceptionRecord:
    """归一化任意 ``BaseException`` 为 ``ExceptionRecord``(SSOT 工厂)。

    - ``boundary`` 必须由 caller 提供(对应捕获位置 EP 名)。
    - ``exception_class`` 用 ``__qualname__``,与历史 instrument_wrap 字段对齐。
    - ``traceback_text`` 按 ``frame_budget`` 帧 cap,栈顶优先;完整 call_frames
      仍保留(file:line 完整)。
    - ``cause_chain`` 走 ``__cause__`` / ``__context__``,去重 + 跳过 self。
    - ``err_kind`` 自动分类(NETWORK / SSL / CANCELLED / ...)。
    """
    exc_type = type(exc).__qualname__
    exc_message = str(exc)
    traceback_text, call_frames, source_location = _format_traceback_capped(
        exc, frame_budget=frame_budget
    )

    cause_chain: list[str] = []
    seen: set[str] = set()
    for link in (exc.__cause__, exc.__context__):
        if link is None or link is exc:
            continue
        link_name = type(link).__qualname__
        if link_name in seen:
            continue
        seen.add(link_name)
        cause_chain.append(link_name)

    err_kind = classify_exception(exc)

    return ExceptionRecord(
        boundary=boundary,
        exception_class=exc_type,
        exception_message=exc_message,
        traceback_text=traceback_text,
        source_location=source_location,
        call_frames=call_frames,
        cause_chain=tuple(cause_chain),
        err_kind=err_kind,
        run_id=run_id,
        trace_id=trace_id,
    )


__all__ = [
    "ErrKind",
    "ExceptionRecord",
    "SourceLocation",
    "classify_exception",
    "exc_to_record",
]
