"""异常归一化 SSOT —— Spine-side canonical form of a Python exception.

ADR-0169 + ADR-2026-09-02-i17-stream-align §B: 不论异常来自装饰器路径
(``instrument_wrap._safe_append``) 还是 transport 兜底路径
(``lifecycle.execute`` 的顶层 ``except``),都必须先归一化成
:class:`ExceptionRecord`,再交给唯一的 :func:`emit_exception_caught`。

字段语义与 ``instrument_wrap._exception_payload`` 对齐(后者是这条
SSOT 的首个 caller),同时为 transport 路径补全 ``traceback_text`` /
``call_frames`` / ``source_location`` / ``cause_chain``。FileSink
``_ATOMIC_THRESHOLD=4096`` 会根据序列化后 payload 大小自动 offload
到 ``<sha256>.json`` sidecar,所以一个带 traceback 的 ExceptionRecord
必然产生 sidecar —— 这是 FileSink 的本职,不是这条 SSOT 的设计目标。
"""

from __future__ import annotations

import traceback
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_TRACEBACK_CAPPED_BYTES = 4096  # 与 instrument_wrap._exception_payload 对齐


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
    展开成 ``{file, line, function}`` 三键。整个 payload 序列化后
    必然超过 ``_ATOMIC_THRESHOLD``(traceback 文本即使被 cap 到 4 KiB
    仍然显著大于空 payload),FileSink 自动 offload。
    """

    boundary: str
    """捕获边界标识 —— ``"lifecycle.execute"`` / ``"phase_graph.node.end"`` 等。"""

    exception_class: str
    """``type(exc).__qualname__``(与 instrument_wrap._exception_payload 对齐)。"""

    exception_message: str
    """``str(exc)``(可能为空)。"""

    traceback_text: str
    """``traceback.format_exception(...)`` 输出,UTF-8 cap 到 4 KiB。"""

    source_location: SourceLocation | None
    """异常最末帧(file:line:function);``None`` 表示无 ``__traceback__``。"""

    call_frames: tuple[SourceLocation, ...]
    """完整 traceback 链,从最末帧向最早帧。所有帧 file:line 完整保留。"""

    cause_chain: tuple[str, ...]
    """``__cause__`` / ``__context__`` 的类型链(去重,跳过 self)。"""

    run_id: str
    """调用方所在 run_id;空字符串表示 non-run context(boot/shutdown)。"""

    trace_id: str
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


def exc_to_record(
    exc: BaseException,
    *,
    boundary: str,
    run_id: str = "",
    trace_id: str = "",
) -> ExceptionRecord:
    """归一化任意 ``BaseException`` 为 ``ExceptionRecord``(SSOT 工厂)。

    - ``boundary`` 必须由 caller 提供(对应捕获位置 EP 名)。
    - ``exception_class`` 用 ``__qualname__``,与历史 instrument_wrap 字段对齐。
    - ``traceback_text`` UTF-8 cap 到 4 KiB(与 instrument_wrap 一致)。
    - ``call_frames`` 完整保留,便于 sidecar reader 精确到行。
    - ``cause_chain`` 走 ``__cause__`` / ``__context__``,去重 + 跳过 self。
    """
    exc_type = type(exc).__qualname__
    exc_message = str(exc)
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    tb_capped = tb_text.encode("utf-8", errors="replace")[:_TRACEBACK_CAPPED_BYTES]
    traceback_text = tb_capped.decode("utf-8", errors="ignore")

    tb = exc.__traceback__
    source_location: SourceLocation | None = None
    call_frames_list: list[SourceLocation] = []
    if tb is not None:
        frames = traceback.extract_tb(tb)
        for frame in frames:
            call_frames_list.append(_frame_to_source_location(frame))
        if frames:
            source_location = _frame_to_source_location(frames[-1])

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

    return ExceptionRecord(
        boundary=boundary,
        exception_class=exc_type,
        exception_message=exc_message,
        traceback_text=traceback_text,
        source_location=source_location,
        call_frames=tuple(call_frames_list),
        cause_chain=tuple(cause_chain),
        run_id=run_id,
        trace_id=trace_id,
    )


__all__ = [
    "ExceptionRecord",
    "SourceLocation",
    "exc_to_record",
]
