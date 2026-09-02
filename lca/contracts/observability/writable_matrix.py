"""Writable Matrix —— 写路径五面可替换矩阵（ADR-0167 D11）。

每个「写动作」都被切到一个独立的 Protocol 面。Agent / Brain / Body /
Perceive 只能通过 ``StepCoordinator`` 间接触达，任一面都是可替换插件。

面的链路（每节独立可替换）：

    Agent intent
        → EventEmitter         (Protocol)
        → StepDriver            (Protocol)
        → Coalescer             (Protocol)
        → Serializer            (Protocol)
        → EventStorage          (Protocol)

附加：

    ModelVisibleRecorder      (Protocol)   完整模型可见正文
    ReplayCursor              (Protocol)   零 token 回放

每个 Protocol 在 ``contracts/observability/writable_matrix.py`` 中独立
``@runtime_checkable``，便于 profile 注册表按字符串键解引用与单元测试
isinstance 验证。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.infrastructure.observability.spine.event_record import EventRecord

# ── 主链五面 ──────────────────────────────────────────────────────


@runtime_checkable
class EventEmitter(Protocol):
    """把 ``EventRecord`` 推向下游（默认 = EventSpine.append）。"""

    def emit(self, record: EventRecord) -> None: ...


@runtime_checkable
class StepDriver(Protocol):
    """切步 / 切段 / 切相位（默认 = StandardDriver）。"""

    def begin_step(self, phase: str, **ctx: Any) -> str:
        """返回 step_id；重复 begin 未 close 时抛 RuntimeError。"""
        ...

    def end_step(self, step_id: str, outcome: str) -> None: ...
    def begin_segment(self, step_id: str, kind: str) -> str: ...
    def end_segment(self, segment_id: str, outcome: str) -> None: ...


@runtime_checkable
class Coalescer(Protocol):
    """流式去抖；同一 EP 在窗口内合并（默认 = LineCoalescer）。"""

    def feed(self, channel: str, payload: Any) -> None: ...
    def flush(self) -> tuple[Any, ...]: ...


@runtime_checkable
class Serializer(Protocol):
    """把 ``EventRecord`` 序列化为底层存储写入形态（默认 = NdjsonSerializer）。"""

    def serialize(self, record: EventRecord) -> bytes: ...


@runtime_checkable
class EventStorage(Protocol):
    """写入事件到具体存储（默认 = RoutingFileSink）。"""

    def write(self, payload: bytes) -> None: ...
    def close(self) -> None: ...


# ── 附加 ─────────────────────────────────────────────────────────


@runtime_checkable
class ModelVisibleRecorder(Protocol):
    """完整模型可见正文（默认 = FilesystemRecorder → model_visible/step_NN/）。"""

    def record_header(self, step_id: str, header: Any) -> None: ...
    def record_prompt(self, step_id: str, text: str) -> None: ...
    def record_tools(self, step_id: str, schemas: tuple[Any, ...]) -> None: ...
    def record_manifest(self, step_id: str, manifest: Any) -> None: ...
    def record_messages(self, step_id: str, messages: tuple[Any, ...]) -> None: ...


@runtime_checkable
class ReplayCursor(Protocol):
    """零 token 确定性回放（默认 = StandardCursor）。"""

    def at(self, run_id: str, step_index: int) -> Any: ...


# ── 矩阵元类型 ────────────────────────────────────────────────────

WritableFace = (
    EventEmitter
    | StepDriver
    | Coalescer
    | Serializer
    | EventStorage
    | ModelVisibleRecorder
    | ReplayCursor
)

FACE_NAMES: tuple[str, ...] = (
    "emitter",
    "driver",
    "coalescer",
    "serializer",
    "storage",
    "model_visible_recorder",
    "replay_cursor",
)
