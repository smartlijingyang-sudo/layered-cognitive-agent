"""五面矩阵默认实现（ADR-0167 D11）。

每个默认实现都是「最朴素、无副作用」的形态，与既有代码形态一致：

- ``SpineEmitter`` → EventSpine.append（强制 bind，避免伪防御）
- ``StandardDriver`` → 显式栈（list of Frame），不用 dict 假装栈
- ``LineCoalescer`` → 单 buffer（不假装按 channel 分桶）
- ``NdjsonSerializer`` → dataclasses.asdict，自动跟 EventRecord 字段同寿命
- ``RoutingFileStorage`` / ``NullStorage`` → 适配既有 sink

装配由 :mod:`lca.plugins.observability.writable_matrix.assembly` 的 plugin 完成，
本模块只承载可独立复用的 dataclass。
"""

from __future__ import annotations

import json
import os
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from lca.infrastructure.observability.spine.event_record import EventRecord


class SpineLike(Protocol):
    """SpineEmitter 期望的最小表面（duck-typed 协议）。"""

    def append(self, **kwargs: Any) -> Any: ...


# ── Emitter ───────────────────────────────────────────────────────


@dataclass
class SpineEmitter:
    """默认 EventEmitter = 调 EventSpine.append。

    必须先 :meth:`bind` 再调 :meth:`emit` —— 构造时不留 None，
    避免「永远不触发的防御抛错」（ADR-0167 D13）。
    """

    _spine: SpineLike = field(init=False)

    def bind(self, spine: SpineLike) -> None:
        self._spine = spine

    def emit(self, record: EventRecord) -> None:
        self._spine.append(
            execution_point=record.execution_point,
            channel=record.channel,
            caller_payload=record.payload,
            outcome=record.outcome,
            phase=record.phase,
            reason=record.reason,
            when=record.when,
        )


# ── Driver ────────────────────────────────────────────────────────


@dataclass
class _StepFrame:
    phase: str
    started_at: float
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class _SegmentFrame:
    step_id: str
    kind: str
    started_at: float


@dataclass
class StandardDriver:
    """默认 StepDriver = 显式 stack（list of Frame）。

    step 与 segment 都是嵌套栈；begin/end 必须 LIFO。
    """

    _step_stack: list[_StepFrame] = field(default_factory=list)
    _segment_stack: list[_SegmentFrame] = field(default_factory=list)
    _step_seq: int = 0
    _segment_seq: int = 0

    def begin_step(self, phase: str, **ctx: Any) -> str:
        if self._step_stack:
            raise RuntimeError(f"begin_step while step {self._step_stack[-1]} still open")
        self._step_seq += 1
        step_id = f"step_{self._step_seq:03d}"
        self._step_stack.append(_StepFrame(phase, _now(), dict(ctx)))
        return step_id

    def end_step(self, step_id: str, outcome: str) -> None:
        if not self._step_stack or self._step_stack[-1].phase is None:
            raise KeyError("end_step: no step open")
        if self._segment_stack:
            raise RuntimeError(f"end_step({step_id!r}) while segment still open")
        self._step_stack.pop()

    def begin_segment(self, step_id: str, kind: str) -> str:
        if not self._step_stack:
            raise KeyError("begin_segment: no step open")
        self._segment_seq += 1
        seg_id = f"seg_{self._segment_seq:04d}"
        self._segment_stack.append(_SegmentFrame(step_id, kind, _now()))
        return seg_id

    def end_segment(self, segment_id: str, outcome: str) -> None:
        if not self._segment_stack:
            raise KeyError("end_segment: no segment open")
        self._segment_stack.pop()


def _now() -> float:
    import time

    return time.time()


# ── Coalescer ─────────────────────────────────────────────────────


@dataclass
class LineCoalescer:
    """默认 Coalescer = 单 buffer 顺序合并。

    只接受单一逻辑流；如有按 channel 需求请换 ``MultiCoalescer`` 或
    自实现。不假装按 channel 分桶（ADR-0167 D13）。
    """

    _buffer: list[Any] = field(default_factory=list)

    def feed(self, channel: str, payload: Any) -> None:
        del channel  # 默认实现不维护分桶语义
        self._buffer.append(payload)

    def flush(self) -> tuple[Any, ...]:
        out = tuple(self._buffer)
        self._buffer.clear()
        return out


# ── Serializer ────────────────────────────────────────────────────


class NdjsonSerializer:
    """默认 Serializer = utf-8 ndjson 一行一记录。"""

    def serialize(self, record: EventRecord) -> bytes:
        d = asdict(record)
        # datetime → ISO8601；其余由 default=str 兜底
        d["when"] = _iso(d.get("when"))
        d["when_corrected"] = _iso(d.get("when_corrected"))
        return (json.dumps(d, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def _iso(v: Any) -> str | None:
    if isinstance(v, datetime):
        return v.isoformat()
    return None  # type: ignore[returnNone]


# ── Storage ───────────────────────────────────────────────────────


class NullStorage:
    """测试 / 零副作用场景：吞掉所有写入。"""

    def write(self, payload: bytes) -> None:
        del payload

    def close(self) -> None:
        return None


class RoutingFileStorage:
    """默认 Storage = per-run 追加 events.jsonl（O_APPEND 原子写入）。"""

    def __init__(self, run_dir: Path, *, file_name: str = "events.jsonl") -> None:
        self._path = Path(run_dir) / file_name
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        self._fd = os.open(
            str(self._path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
            0o644,
        )

    def write(self, payload: bytes) -> None:
        os.write(self._fd, payload)

    def close(self) -> None:
        with suppress(OSError):
            os.close(self._fd)
