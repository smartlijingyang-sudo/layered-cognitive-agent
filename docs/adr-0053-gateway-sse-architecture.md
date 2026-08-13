# ADR-0053: Gateway SSE 链路架构重构

**状态**: Superseded  
**日期**: 2026-08-12  
**决策者**: 架构评审  
**Superseded by**: `docs/superpowers/specs/2026-08-13-run-live-architecture-design.md`（Journal SSE + LiveTail + JournalTransport；`timeline.v1` 已废）


---

## 背景

当前 Gateway SSE 链路承载 LobeHub 前端 → LCA 后端 → LobeHub 前端的实时事件流。
链路经过多轮迭代，积累了七层抽象，存在以下问题：

1. **协议伪装**: Agent 路径挂在 `/v1/chat/completions`，返回的却不是 OpenAI chunk，而是 `timeline.v1` SSE
2. **职责泄漏**: `TimelineProjector` 同时做领域投影和 LobeHub 协议适配
3. **多余间接层**: `ObservabilityHub` → `EventBusProjector` → `EventBus` 三层传递，中间两层各无独立存在价值
4. **重复代码**: `stream.py` 和 `routes.py` 各自实现了一遍流组装逻辑
5. **观测盲区**: Queue full 静默丢弃 subscriber；dropped events 计数无观测端点

## 第一性原理

> Gateway 链路解决的根本问题：**Agent 执行过程产生的认知事件，需要同时到达两个地方——一个 SSE 连接（给活人看），一个 JSONL 文件（给未来的自己看）。**

一个 Python 进程，一个 Agent run，一到十几个 SSE 消费者。不需要 Kafka，不需要多副本，不需要跨进程。

从这个事实出发，链路只需要三个概念：**事件分发**、**领域映射**、**协议翻译**。

## 当前架构（七层）

```
Agent/Team 执行代码
  → journal.record(StampedEvent)            ← ① Journal（事件源）
    → ObservabilityHub._apply()             ← ② 框架调度层
      → EventBusProjector.on_event()        ← ③ 过滤 + 适配
        → EventBus.publish()                ← ④ 传输（广播+缓冲）
          → EventBus.subscribe()            ← ⑤ 订阅（回放+live）
            → TimelineProjector.project()   ← ⑥ 投影（混合适配）
              → encode_sse_bytes()          ← ⑦ 编码
```

## 新架构（四层）

```
Agent/Team 执行代码
  → journal.record(StampedEvent)
      │
      ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  层 1 · EventStream                                              │
  │  环形缓冲 + 发布/订阅 + 断线回放                                   │
  │  约 60 行，不知道 Journal / SSE / LobeHub 是什么                   │
  └───┬──────────────────────────────────────┬───────────────────────┘
      │                                      │
      ▼                                      ▼
  消费 A: JSONL                            消费 B: SSE
  (后台 task, aiofiles 写文件)             (HTTP handler)
                                              │
                                              ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  层 2 · TimelineProjection                                       │
  │  Journal StampedEvent → Timeline 领域事件                         │
  │  纯映射，无副作用，不关心前端协议                                   │
  │  输出是领域中立结构：tool="execute_code"，不是 wire_name="lca____…" │
  └────────────────────────────┬─────────────────────────────────────┘
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  层 3 · LobeHub SSE Adapter                                      │
  │  Timeline 领域事件 → LobeHub 前端需要的 SSE 帧                     │
  │  wire 名解析、plugin state 拼装、文件 URL absolutize               │
  │  如果换前端，这一层重写，上面不动                                    │
  └────────────────────────────┬─────────────────────────────────────┘
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  层 4 · SSE Encode                                               │
  │  dict → "id: {seq}\nevent: {type}\ndata: {json}\n\n"            │
  │  无状态工具函数                                                    │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 各层详细设计

### 层 1: EventStream — 唯一的事件分发原语

**替代**: `EventBus` + `EventBusProjector` + `ObservabilityHub`

```python
# gateway/event_stream.py
from collections import deque


@dataclass(frozen=True, slots=True)
class StampedEvent:
    """已有类型，不变。"""

    seq: int
    event: JournalEvent
    scope: EventScope
    ts: datetime


@dataclass(frozen=True, slots=True)
class GapEvent:
    """subscribe() 检测到 after_seq 已被环形缓冲淘汰时 yield 的信号。

    消费侧收到后可决定是否回退到 JSONL 重放。
    这不是 StampedEvent 的子类——它是一个控制信号，不是领域事件。
    """

    requested_seq: int
    oldest_available_seq: int


@dataclass(slots=True)
class _Subscriber:
    """单个订阅者的运行时状态。

    overflow_count 可变（非 frozen），因为 publish 需要原地更新。
    用 dataclass 替代裸 tuple，避免 `self._subscribers[idx] = (q, new_count)` 这种
    需要同时解构和重建的可读性陷阱。
    """

    queue: asyncio.Queue[StampedEvent | None]
    overflow_count: int = 0


class EventStream:
    """
    事件分发原语。不知道 Journal、SSE、LobeHub。

    职责边界：
      - 环形缓冲（有界内存，back-pressure 通过丢弃最老事件实现）
      - 发布/订阅（多消费者广播）
      - 断线回放（after_seq），原子化注册+回放，无竞态窗口
      - Buffer gap 检测（after_seq 被淘汰时发 GapEvent）
      - 关闭信号（run 结束）

    不做的事：
      - 不做事件过滤（过滤在 TimelineProjection 层，见层 2）
      - 不做序列化（编码在 SSE adapter 层）
      - 不做格式转换（投影在 Projection 层）
    """

    _MAX_BUFFERED: int = 4096
    _MAX_QUEUE: int = 256
    _OVERFLOW_THRESHOLD: int = 3  # 连续溢出 N 次后移除 subscriber

    _frames: deque[StampedEvent]
    _subscribers: list[_Subscriber]
    _closed: bool

    def publish(self, stamped: StampedEvent) -> None:
        """广播到所有活跃订阅者。

        溢出策略（改进）：
          - 单次 queue full：记 warning 日志 + overflow_count++，不移除
          - 连续溢出 >= _OVERFLOW_THRESHOLD 次：记 error 日志 + 移除（判定为死消费者）
          - 成功投递：overflow_count 归零

        改进动机：高频 thinking.delta 事件可能瞬时打满 queue，但消费者仍在读取。
        单次 overflow 就移除过于激进，导致 SSE 连接意外断开。
        """
        if self._closed:
            return
        # 环形缓冲（deque maxlen 自动丢弃最老）
        self._frames.append(stamped)

        dead: list[int] = []
        for idx, sub in enumerate(self._subscribers):
            try:
                sub.queue.put_nowait(stamped)
                # 成功投递，重置 overflow 计数
                sub.overflow_count = 0
            except asyncio.QueueFull:
                sub.overflow_count += 1
                if sub.overflow_count >= self._OVERFLOW_THRESHOLD:
                    dead.append(idx)
                    structlog.get_logger(__name__).error(
                        "event_stream_subscriber_evicted",
                        consecutive_overflows=sub.overflow_count,
                        queue_size=self._MAX_QUEUE,
                        seq=stamped.seq,
                    )
                else:
                    structlog.get_logger(__name__).warning(
                        "event_stream_subscriber_overflow",
                        overflow_count=sub.overflow_count,
                        queue_utilization=sub.queue.qsize() / self._MAX_QUEUE,
                        threshold=self._OVERFLOW_THRESHOLD,
                        queue_size=self._MAX_QUEUE,
                        seq=stamped.seq,
                    )
        for idx in reversed(dead):
            self._subscribers.pop(idx)

    def subscribe(self, after_seq: int = 0) -> AsyncIterator[StampedEvent | GapEvent]:
        """原子化订阅：注册队列 → 回放缓冲 → 流式 live。

        返回类型：AsyncIterator[StampedEvent | GapEvent]
          - 首条可能是 GapEvent（缓冲已淘汰 after_seq 之前的事件）
          - 后续全部是 StampedEvent
          - 调用者需要用 isinstance(item, GapEvent) 区分，或在上层 try/except 处理

        关键：注册发生在回放之前，因此回放期间 publish 的事件
        不会丢失——它们会进入已注册的 queue，在回放结束后被消费。

        如果 after_seq 小于缓冲中最老的 seq（即发生了 buffer evict），
        首条 yield 一个 GapEvent，携带 oldest_available_seq，
        消费侧可据此决定是否回退到 JSONL 重放。
        """
        queue: asyncio.Queue[StampedEvent | None] = asyncio.Queue(self._MAX_QUEUE)
        self._subscribers.append(_Subscriber(queue=queue))

        oldest_seq = self._frames[0].seq if self._frames else None
        if oldest_seq is not None and after_seq < oldest_seq:
            yield GapEvent(
                requested_seq=after_seq,
                oldest_available_seq=oldest_seq,
            )

        # 回放阶段：如果缓冲很大，需要 cooperative yield 防止阻塞 event loop
        replay_count = 0
        for stamped in self._frames:
            if stamped.seq > after_seq:
                yield stamped
                replay_count += 1
                # 每 64 个事件让出一次控制权
                if replay_count % 64 == 0:
                    await asyncio.sleep(0)

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if item.seq > after_seq:
                    yield item
        finally:
            self._subscribers = [sub for sub in self._subscribers if sub.queue is not queue]

    def buffered_after(self, after_seq: int = 0) -> list[StampedEvent]:
        """非阻塞快照：返回 seq > after_seq 的缓冲事件。仅供调试端点使用。"""
        ...

    def close(self) -> None:
        """发送 sentinel，通知所有订阅者流结束。

        幂等：如果已经 close 过（_closed=True），立即返回，不做二次广播。
        这保证了 _finalize_run 中多处调用 close_stream() 不会重复发送 sentinel。

        异常保护：如果 subscriber 的 queue 已满，put_nowait(None) 会抛 QueueFull。
        此时强制清空 queue 再投递 sentinel，确保所有 subscriber 都能收到关闭信号。
        """
        if self._closed:
            return
        self._closed = True
        for sub in self._subscribers:
            try:
                sub.queue.put_nowait(None)
            except asyncio.QueueFull:
                # queue 已满，强制清空后投递 sentinel
                sub.queue.get_nowait()  # 丢弃一个旧事件
                sub.queue.put_nowait(None)
        self._subscribers.clear()

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def subscriber_count(self) -> int:
        """暴露给观测端点。"""
        return len(self._subscribers)
```

**关键变更点**：

| 项目 | 旧 (`EventBus`) | 新 (`EventStream`) |
|---|---|---|
| 定位 | ObservabilityHub 的内部 projector 输出 | 一等公民，独立组件 |
| 过滤 | 无（由 `EventBusProjector` 在外部过滤） | 无（过滤移到 `TimelineProjection` 层，见下文） |
| 环形缓冲 | `list` + `pop(0)` O(n) | `deque(maxlen=N)` O(1) |
| 溢出处理 | 静默移除 dead subscriber | 连续 N 次溢出才移除；单次溢出记 warning + queue_utilization |
| Buffer gap | 无检测 | `subscribe()` 检测 gap 并 yield `GapEvent` |
| 订阅原子性 | 先回放再注册（竞态窗口） | 注册 → 回放 → live，无竞态 |
| 可观测 | 无 | `subscriber_count` + `buffer_size` 属性 |

**过滤移到哪里？**

当前 `EventBusProjector` 过滤 `RunInsight` 和 `decision` channel。这些过滤逻辑移到 `TimelineProjection.project()` 中——投影层决定"什么事件产生什么 timeline 事件"，过滤是其天然职责的一部分。JSONL consumer 需要完整事件，不过滤。

### 层 2: TimelineProjection — 纯领域映射

**替代**: `TimelineProjector`（去掉其中的 LobeHub 适配逻辑）

```python
# gateway/timeline/projection.py


@dataclass
class TimelineProjection:
    """
    Journal StampedEvent → Timeline 领域事件。

    设计原则：
      1. 输出是领域中立结构
         - tool 事件用 LCA 内部名 (execute_code)，不是 wire 名 (lca____executeCode)
         - file 事件保留原始路径，不拼 gateway URL
         - plugin_state 只保留原始 plugin_state，不拼装 LobeHub 特有字段
      2. 过滤在这里做（RunInsight / decision channel 不产生 timeline 事件）
      3. 声明式 dispatch table，新增事件类型只加一行

    不做的事：
      - 不 resolve_tool_wire()（Adapter 层）
      - 不 build_tool_plugin_state()（Adapter 层）
      - 不 absolutize_file_parts()（Adapter 层）
      - 不 transform_tool_arguments()（Adapter 层）
    """

    dropped: Counter[str]
    _finished: bool
    _reasoning: dict[int, str]
    _answer: str
    _invocation_ids: dict[str, str]

    def project(self, stamped: StampedEvent) -> list[TimelineEvent]:
        """纯映射。每个 TimelineEvent 是领域中立 frozen dataclass。

        seq 赋值规则：
          - 1:1 映射的事件直接继承 stamped.seq
          - 1:N 映射的事件（如 tool.start 产生种子 tool.delta）共享 stamped.seq，
            由 SSE 客户端按 event_type 区分

        1:N 共享 seq 与 Last-Event-ID 重连的 tradeoff：
          当客户端用 Last-Event-ID=seq 重连时，subscribe(after_seq=seq) 会
          过滤掉 seq ≤ after_seq 的事件。如果 tool.start 和其种子 tool.delta
          共享同一个 seq，它们会被一起重放或一起跳过——不会出现"只有 start 没有
          种子 delta"的中间态。这是可接受的行为：种子 delta 的语义是"初始状态快照"，
          如果客户端已经收到过该 seq 的完整事件组，跳过整组是正确的。
          如果客户端从未收到过该 seq（即 seq > after_seq），整组都会被重放。
          结论：共享 seq 在重连语义下是自洽的，不需要子序号。
        """
        ...


# ── Timeline 领域事件定义（类型安全的 dataclass，不再用裸 dict） ──

# 所有 Timeline 领域事件共享两个字段：seq: int 和 type: str。
# 不用基类继承——Python 不是 Java，不需要基类来"统一接口"。
# 用 frozen dataclass 保证不可变，用 Union 做类型标注和 match/case。


@dataclass(frozen=True)
class RunStartEvent:
    seq: int = 0
    type: Literal["run.start"] = "run.start"
    run_id: str = ""
    trace_id: str = ""
    objective_preview: str = ""


@dataclass(frozen=True)
class ThinkingDeltaEvent:
    seq: int = 0
    type: Literal["thinking.delta"] = "thinking.delta"
    step: int = 0
    text: str = ""


@dataclass(frozen=True)
class ThinkingEndEvent:
    seq: int = 0
    type: Literal["thinking.end"] = "thinking.end"
    step: int = 0
    content: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class AnswerDeltaEvent:
    seq: int = 0
    type: Literal["answer.delta"] = "answer.delta"
    step: int = 0
    text: str = ""


@dataclass(frozen=True)
class ToolStartEvent:
    seq: int = 0
    type: Literal["tool.start"] = "tool.start"
    tool_call_id: str = ""
    tool_name: str = ""  # LCA 内部名，如 "execute_code"
    arguments: dict[str, Any] = field(default_factory=dict)
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDeltaEvent:
    seq: int = 0
    type: Literal["tool.delta"] = "tool.delta"
    tool_call_id: str = ""
    stream: str = "stdout"
    text: str = ""
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolEndEvent:
    seq: int = 0
    type: Literal["tool.end"] = "tool.end"
    tool_call_id: str = ""
    tool_name: str = ""
    ok: bool = True
    content: str = ""
    plugin_state: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)  # 原始文件 dict


@dataclass(frozen=True)
class RunEndEvent:
    seq: int = 0
    type: Literal["run.end"] = "run.end"
    status: str = "completed"
    steps: int = 0
    output: str = ""
    error: str = ""


# 联合类型（用于类型标注和 match/case exhaustiveness checking）
# 所有 dataclass 都包含 seq: int 和 type: str 字段，
# mypy 通过 Union narrowing 做 exhaustiveness 检查。
TimelineEvent = (
    RunStartEvent
    | ThinkingDeltaEvent
    | ThinkingEndEvent
    | AnswerDeltaEvent
    | ToolStartEvent
    | ToolDeltaEvent
    | ToolEndEvent
    | RunEndEvent
)
```

**关键变更**：

- `TimelineEvent` 从裸 `dict[str, Any]` 变为 **frozen dataclass 联合类型**，获得编译期类型检查
- 所有 dataclass 共享 `seq: int` 和 `type: str` 字段，mypy 通过 Union narrowing 做 exhaustiveness 检查
- 每个 dataclass 直接声明 `seq: int`，由投影层从 `StampedEvent.seq` 赋值
- 去掉所有 LobeHub 适配逻辑（wire_name, plugin_state 拼装, file URL absolutize）
- 过滤 `RunInsight` / `decision` channel 在这里做（投影层的天然职责）

### 层 3: LobeHub SSE Adapter — 协议翻译

**新增模块**。把当前散落在 `TimelineProjector` 各 handler 里的适配逻辑集中到一个地方。

```python
# gateway/timeline/lobehub_adapter.py

"""
LobeHub 前端协议适配器。

将 Timeline 领域事件翻译为 LobeHub 前端 UI 需要的格式：
  - tool_name → wire_name (identifier____apiName)
  - arguments → transform_tool_arguments(wire)
  - plugin_state → build_tool_plugin_state(wire, ...)
  - files → absolutize_file_parts()

如果未来换前端（自建 SPA / CLI / API），写一个新的 adapter，这一层整体替换。
TimelineProjection 一行不改。
"""

from gateway.lobehub_bridge.lobehub_adapter import (
    build_tool_plugin_state,
    resolve_tool_wire,
    split_wire_name,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import safe_json_string
from gateway.lobehub_bridge.file_urls import absolutize_file_parts
from lca.layer0_infra.computer.constants import STREAMING_WIRE_APIS


@dataclass
class LobeHubSSEAdapter:
    """
    有状态适配器，一个实例严格绑定一个 run stream。

    ⚠️ 不可跨 stream 复用：实例内部维护的累积状态（_invocation_ids、_pending、
    _exec_buf）与特定 run 的工具调用上下文绑定。复用到另一个 stream 会导致
    tool_call_id 碰撞和 state 污染。

    生命周期：由 compose_sse_stream() 创建，随 HTTP 连接关闭而释放。

    维护 LobeHub 前端需要的累积状态：
      - invocation_ids: tool_call_id 映射
      - pending_tools: 工具调用上下文（用于 delta 时拼装 state）
      - exec_buffers: sandbox 工具 stdout/stderr 累积
    """

    _invocation_ids: dict[str, str]
    _pending: dict[str, dict[str, Any]]
    _exec_buf: dict[str, dict[str, str]]

    def adapt(self, event: TimelineEvent) -> list[dict[str, Any]]:
        """
        将一个领域事件翻译为 0~N 个 LobeHub SSE payload dict。
        每个 dict 可直接 encode_sse。

        关键：这是唯一知道 wire_name / plugin_state / file URL 的地方。
        """
        match event:
            case ToolStartEvent():
                return self._adapt_tool_start(event)
            case ToolDeltaEvent():
                return self._adapt_tool_delta(event)
            case ToolEndEvent():
                return self._adapt_tool_end(event)
            case _:
                # 其他事件类型直接透传（领域 dict → LobeHub dict）
                return [self._passthrough(event)]

    def _adapt_tool_start(self, event: ToolStartEvent) -> list[dict]:
        wire = resolve_tool_wire(event.tool_name, safe_json_string(event.arguments))
        wire_name = wire.wire_name if wire else event.tool_name
        args_json = (
            transform_tool_arguments(wire, event.arguments)
            if wire
            else safe_json_string(event.arguments)
        )
        identifier, api_name = split_wire_name(wire_name)

        self._invocation_ids[event.tool_call_id] = event.tool_call_id
        self._pending[event.tool_call_id] = {
            "tool_name": event.tool_name,
            "arguments": event.arguments,
            "plugin_state": event.plugin_state,
        }

        out = [
            {
                "type": "tool.start",
                "tool_call_id": event.tool_call_id,
                "name": event.tool_name,
                "wire_name": wire_name,
                "identifier": identifier,
                "api_name": api_name,
                "arguments": args_json,
                "state": dict(event.plugin_state),
            }
        ]

        # sandbox 工具种子 tool.delta
        if event.plugin_state and wire and wire.api_name in STREAMING_WIRE_APIS:
            seed = dict(event.plugin_state)
            seed.setdefault("executionEnv", "sandbox")
            seed.setdefault("success", True)
            out.append(
                {
                    "type": "tool.delta",
                    "tool_call_id": event.tool_call_id,
                    "stream": "stdout",
                    "text": "",
                    "state": seed,
                    "snapshot_seq": 0,
                }
            )
        return out

    def _adapt_tool_end(self, event: ToolEndEvent) -> list[dict]:
        # ... 从 self._pending 取上下文，调用 build_tool_plugin_state，absolutize_file_parts
        ...
        # 清理已完成工具的上下文，防止长 run 内存泄漏
        self._pending.pop(event.tool_call_id, None)
        self._exec_buf.pop(event.tool_call_id, None)

    def _adapt_tool_delta(self, event: ToolDeltaEvent) -> list[dict]:
        # ... 累积 exec_buf，拼装 streaming state
        ...
```

### 层 4: SSE Encode — 无状态工具

```python
# gateway/timeline/sse_encode.py


def encode_sse(event: dict, *, seq: int, event_type: str) -> bytes:
    """dict → SSE 帧 bytes。纯函数，无状态。"""
    payload = {"v": "timeline.v1", **event}
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n".encode()
```

---

## HTTP 路由重构

### 消除协议伪装

```python
# gateway/openai_compat_api.py — 重构后


async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    """OpenAI-compatible /v1/chat/completions — 只处理非 agent 请求。"""
    body = await request.json()
    messages = body.get("messages") or []

    # title 类 → 真正的 OpenAI 兼容 response
    if classify_lobehub_chat_request(messages) == "title":
        return await _passthrough_chat_completion(...)

    # Agent 请求 → Phase 3a 先 deprecation，Phase 3b 再 hard cut
    return await _deprecated_agent_via_chat_completions(request, body)
```

> **渐进迁移策略（两阶段）**：
>
> **Phase 3a — Deprecation（默认行为）**：
> 1. 保留原有 agent 路径功能不变
> 2. 在 response header 中加 `X-LCA-Deprecated: chat.completions-for-agent`
> 3. 记 structlog warning `deprecated_agent_via_chat_completions`
> 4. 设置淘汰时间线（如 2 个版本后移除）
> 5. 同时修复该路径缺失的 `after_seq` 参数传递，使断线重连在旧路径也可用
>
> **Phase 3b — Hard Cut（确认零流量后）**：
> 1. 确认 structlog 中 `deprecated_agent_via_chat_completions` 连续 7 天零触发
> 2. 将旧路径改为返回 400 + 迁移指引
> 3. 清理前端 patch 中残留的 chat.completions agent 路径

### 统一 SSE 流组装

消除 `stream.py` 和 `routes.py` 的重复：

```python
# gateway/timeline/stream.py — 重构后


async def compose_sse_stream(
    session: RunSession,
    *,
    after_seq: int = 0,
    projection: TimelineProjection | None = None,
    adapter: SSEAdapter | None = None,
) -> AsyncIterator[bytes]:
    """
    唯一的 SSE 流组装点。
    被 /v1/agent/runs/{id}/timeline 和所有其他 SSE endpoint 调用。

    Pipeline 可组合：
      - 默认组装：TimelineProjection → LobeHubSSEAdapter → encode_sse
      - Raw 模式（调试端点）：跳过 adapter，直接 encode 领域事件
      - 自定义前端：传入自定义 adapter 替换 LobeHubSSEAdapter

    组装顺序：
      1. subscribe()（原子化注册 + 回放 + live）
      2. 投影（TimelineProjection）
      3. 适配（SSEAdapter）
      4. 编码（encode_sse）
    """
    projection = projection or TimelineProjection()
    adapter = adapter or LobeHubSSEAdapter()

    async def _pipeline() -> AsyncIterator[bytes]:
        async for item in session.stream.subscribe(after_seq=after_seq):
            if isinstance(item, GapEvent):
                yield encode_sse(
                    {
                        "type": "reconnect.gap",
                        "requested_seq": item.requested_seq,
                        "oldest_available_seq": item.oldest_available_seq,
                    },
                    seq=item.oldest_available_seq,
                    event_type="reconnect.gap",
                )
                continue
            for domain_event in projection.project(item):
                for payload in adapter.adapt(domain_event):
                    yield encode_sse(
                        payload,
                        seq=domain_event.seq,
                        event_type=domain_event.type,
                    )

    return _pipeline()
```

---

## RunSession 重构

```python
# gateway/run_registry.py — 重构后


@dataclass
class RunSession:
    """单次 run 的会话。"""

    run_id: str
    trace_id: str
    jsonl_path: Path
    stream: EventStream  # ← 替代 hub + bus
    question: str
    user_text: str
    mode: str
    prior_turns: tuple[ConversationTurn, ...] = field(default_factory=tuple)
    attachment_ids: tuple[str, ...] = field(default_factory=tuple)
    status: RunStatus = RunStatus.PENDING
    error: str = ""
    task: asyncio.Task[Any] | None = None
    cancel_requested: bool = False
    snapshot: Any = None
    runnable: Any = None
    approval_request: dict[str, Any] | None = None

    def close_stream(self) -> None:
        self.stream.close()
```

**移除**:
- `hub: ObservabilityHub` — 不再需要
- `bus: EventBus` — 被 `stream: EventStream` 替代

### 调试端点保留

当前 `RunRegistry.event_stream()` 提供 `/runs/{id}/events` 调试端点，直接 yield 原始 `StampedEvent`（不经 Projection/Adapter）。此端点保留，改为从 `EventStream.subscribe()` 消费：

```python
# gateway/run_registry.py — event_stream() 重构


async def event_stream(self, run_id: str, after_seq: int = 0) -> AsyncIterator[StampedEvent]:
    """调试用：原始事件流，不经 timeline 投影。
    直接使用 subscribe() 的原子化回放+live，无竞态窗口。
    """
    session = self.get(run_id)
    async for item in session.stream.subscribe(after_seq=after_seq):
        if isinstance(item, GapEvent):
            structlog.get_logger(__name__).warning(
                "debug_event_stream_buffer_gap",
                requested_seq=item.requested_seq,
                oldest_available=item.oldest_available_seq,
            )
            continue
        yield item
```

---

## Run Executor 重构

```python
# gateway/run_executor.py — 重构后

def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    user_text: str,
    mode: str = DEFAULT_MODE,
    attachment_ids: Sequence[str] = (),
    prior_turns: Sequence[ConversationTurn] = (),
) -> RunSession:
    run_id = new_id("run")
    trace_id = new_id("trace")
    jsonl_path = registry.jsonl_path_for(run_id)
    stream = EventStream()

    # 关键：JSONL consumer 必须在任何 publish 可能发生之前完成注册。
    # subscribe() 内部先注册 queue 再回放，因此注册本身是同步的、无竞态。
    # 但 _jsonl_consumer 是 async 函数，其内部 subscribe() 调用
    # 需要等到协程被调度时才执行。因此这里用同步注册 + 异步消费的两步模式。
    jsonl_queue: asyncio.Queue[StampedEvent | None] = asyncio.Queue(EventStream._MAX_QUEUE)
    stream.register_subscriber(jsonl_queue)

    session = RunSession(
        run_id=run_id,
        trace_id=trace_id,
        jsonl_path=jsonl_path,
        stream=stream,
        question=question,
        user_text=user_text,
        mode=mode,
        prior_turns=tuple(prior_turns),
        attachment_ids=tuple(str(i).strip() for i in attachment_ids if str(i).strip()),
    )
    registry.put(session)

    # 注册完成后再启动消费循环，保证不丢事件
    asyncio.create_task(_jsonl_consumer(jsonl_queue, jsonl_path))
    return session


def EventStream.register_subscriber(
    self, queue: asyncio.Queue[StampedEvent | None]
) -> None:
    """同步注册一个 subscriber queue。供需要在 publish 前确保注册的场景使用。"""
    self._subscribers.append((queue, 0))


async def _jsonl_consumer(
    queue: asyncio.Queue[StampedEvent | None], path: Path
) -> None:
    """JSONL 落盘 — 一个普通 consumer，不是 projector。
    queue 已在调用前同步注册，不会丢失任何事件。

    错误处理：如果 aiofiles.open 或 write 失败（磁盘满、权限问题），
    记录 error 日志但不 raise——避免 task 静默失败无人知晓。
    """
    try:
        async with aiofiles.open(path, "a") as f:
            while True:
                stamped = await queue.get()
                if stamped is None:
                    break
                line = json.dumps(stamped_to_dict(stamped), default=str)
                await f.write(line + "\n")
    except Exception:
        structlog.get_logger(__name__).exception(
            "jsonl_consumer_failed",
            path=str(path),
        )
```

**变更**:
- `GatewayCollector` 被移除
- JSONL 落盘从"projector"变为普通 `asyncio.create_task` consumer
- `EventStream` 是一等公民，不再藏在 `ObservabilityHub` 内部
- `_jsonl_consumer` 加 try/except 包裹，防止磁盘/权限错误导致 task 静默死亡

### 统一 Run Teardown — 消除 `execute_run` / `_resume_run` 重复

**问题**: 当前 `run_executor.py:execute_run` 的 `finally` 块和 `app.py:_resume_run` 的 `finally` 块各自独立维护了一套 teardown 逻辑（stream close、finalize_run、status update、inflight cleanup）。任何 teardown 顺序变更必须同步两处，否则导致资源泄漏或状态不一致。

```python
# gateway/run_executor.py — 新增


async def _finalize_run(
    session: RunSession,
    registry: RunRegistry,
    *,
    status: RunStatus,
    error: str = "",
) -> None:
    """
    统一的 run 终结逻辑。被 execute_run 和 _resume_run 共同调用。

    调用顺序由嵌套 finally 保证（不可乱）：
      1. artifact closure safety net（可失败，不影响后续）
      2. finalize_run（JSONL 收尾、指标记录；可失败，不影响后续）
      3. stream.close（发送 sentinel，解除所有 subscriber 阻塞；必定执行）
      4. status 更新 + error 记录（必定执行）
      5. inflight dedup 清理（必定执行）

    即使步骤 1 或 2 抛异常，步骤 3-5 仍会执行。

    registry 作为参数传入，不挂在 RunSession 上——
    避免 session → registry → session 的循环引用。
    """
    try:
        _emit_artifact_closure_if_needed(...)
        await finalize_run(session)
    except Exception:
        structlog.get_logger(__name__).exception(
            "finalize_run_pre_close_failed",
            run_id=session.run_id,
        )
    finally:
        try:
            session.close_stream()
        finally:
            session.status = status
            session.error = error
            registry.clear_inflight(session.run_id)
```

**`execute_run` 和 `_resume_run` 的 `finally` 块统一改为调用 `_finalize_run()`**。

---

## 文件结构对照

### 删除

| 文件 | 原因 |
|---|---|
| `gateway/events.py` (EventBus + EventBusProjector) | 被 `gateway/event_stream.py` 替代 |
| `gateway/collector.py` (GatewayCollector) | 无存在价值，ObservabilityHub 间接层移除 |

### 新增

| 文件 | 职责 |
|---|---|
| `gateway/event_stream.py` | EventStream — 事件分发原语 |
| `gateway/timeline/projection.py` | TimelineProjection — 纯领域映射 |
| `gateway/timeline/lobehub_adapter.py` | LobeHubSSEAdapter — 协议翻译 |
| `gateway/timeline/sse_encode.py` | encode_sse — 无状态 SSE 编码 |
| `gateway/timeline/types.py` | `TimelineEvent` dataclass 联合类型定义 |

### 重构

| 文件 | 变更 |
|---|---|
| `gateway/timeline/projector.py` | 删除（拆分为 projection.py + lobehub_adapter.py） |
| `gateway/timeline/stream.py` | 大幅简化，只保留 `compose_sse_stream()` |
| `gateway/timeline/protocol.py` | 简化为只保留 EVENT_TYPES 白名单 |
| `gateway/timeline/routes.py` | 调用 `compose_sse_stream()`，删除重复流组装 |
| `gateway/openai_compat_api.py` | Agent 路径返回 400 + 迁移指引 |
| `gateway/run_registry.py` | `RunSession` 去掉 `hub` / `bus`，改为 `stream` |
| `gateway/run_executor.py` | `create_run_session` 直接构造 EventStream + JSONL consumer；新增 `_finalize_run()` 统一 teardown |
| `gateway/app.py` | `_resume_run` 的 `finally` 块改为调用 `_finalize_run()`，消除与 `execute_run` 的重复 |

### 不变

| 文件/模块 | 原因 |
|---|---|
| `gateway/app.py` 的路由注册 | 路由注册不变，仅 `_resume_run` teardown 改为调用 `_finalize_run()`（见重构表） |
| `gateway/lobehub_bridge/` | 请求解析、附件管理不变 |
| `gateway/lobehub_bridge/lobehub_adapter/` | wire 注册表、参数转换、state 构建不变（被新 adapter 调用） |
| `gateway/lobehub_bridge/file_urls.py` | 文件 URL absolutize 不变（被新 adapter 调用） |
| `lca/layer0_infra/observability/` | Journal 事件类型体系不变 |
| `deploy/lobehub/patches/runtime/agent_timeline_transport.py` | 前端 Transport 不变 |
| `gateway/run_registry.py` 的 `/runs/{id}/events` 调试端点 | 保留，改为从 `EventStream.subscribe()` 消费 |

---

## 排查路径对比

### 旧：前端收到的事件不对

```
1. Journal 有没有 record？            → 查 JSONL
2. EventBusProjector 有没有过滤？      → 读 EventBusProjector.on_event 的两个 if
3. EventBus 有没有丢？                → 无日志，无法判断（盲区）
4. TimelineProjector 有没有映射错？    → 读 projector.py 的 dispatch table + 状态累积
5. TimelineProjector 有没有适配错？    → 同一个文件里混杂的 wire_name / plugin_state 逻辑
6. SSE 编码有没有问题？               → protocol.py encode_sse
```

### 新：前端收到的事件不对

```
1. Journal 有没有 record？            → 查 JSONL
2. TimelineProjection 有没有映射错？   → projection.py，纯映射，dispatch table 清晰
3. LobeHubAdapter 有没有适配错？       → lobehub_adapter.py，所有 LobeHub 逻辑集中在此
4. SSE 编码有没有问题？               → sse_encode.py，纯函数
```

从 6 步降到 4 步。关键改进：步骤 2 和步骤 3 的边界清晰——如果领域事件对但前端格式错，问题在 adapter；如果领域事件就错，问题在 projection。

---

## 扩展场景验证

### 场景 1: 新增前端（自建 SPA，不用 LobeHub）

| | 旧 | 新 |
|---|---|---|
| 需要改 | `TimelineProjector`（混杂 LobeHub 逻辑）或写新的 HTTP handler | `LobeHubSSEAdapter` 整体替换为 `MySPAAdapter` |
| 不需要改 | — | `TimelineProjection`、`EventStream` |

### 场景 2: 新增事件类型（如 `error.fatal`）

| | 旧 | 新 |
|---|---|---|
| 需要改 | `_HANDLERS` dict + `TimelineProjector` 内部状态 + `EVENT_TYPES` frozenset | `TimelineEvent` 新增 dataclass + `TimelineProjection` 新增 handler + `LobeHubSSEAdapter` 新增 adapt case |
| 类型安全 | 无（裸 dict） | dataclass frozen，mypy 可检查 |

### 场景 3: LobeHub 前端 UI 格式变了（如 plugin_state 需要新字段）

| | 旧 | 新 |
|---|---|---|
| 需要改 | `TimelineProjector` 中的 wire_name / plugin_state / file URL 逻辑 | 只改 `LobeHubSSEAdapter` |
| 不需要改 | — | `TimelineProjection`、`EventStream` |

### 场景 4: 新增 consumer（如 WebSocket 推送）

| | 旧 | 新 |
|---|---|---|
| 需要改 | `EventBus` 内部 + 新 projector + 新 handler | `EventStream.subscribe()` + 新 handler |
| 不需要改 | — | Projection、Adapter |

---

## 迁移策略

### Phase 1: 引入 EventStream（消除中间层）

1. 新建 `gateway/event_stream.py`
2. `RunSession` 新增 `stream: EventStream` 字段（暂时与 `bus` 并存）
3. `create_run_session` 同时创建 `EventStream` 和 `EventBus`
4. JSONL 落盘迁移到 `_jsonl_consumer` 后台 task
5. 新 SSE handler 使用 `stream`
6. 验证通过后移除 `bus`、`hub`、`GatewayCollector`、`EventBus`、`EventBusProjector`

### Gate: Golden Comparison 回归验证（Phase 1 → Phase 2 之间）

Phase 1 完成后、Phase 2 开始前，必须通过 golden comparison 验证：

1. 准备 3~5 个真实 run 的 JSONL 记录（覆盖 solo / team / HIL 场景）
2. 用旧链路（`EventBus` → `TimelineProjector` → `encode_sse_bytes`）重放，收集 SSE 输出
3. 用新链路（`EventStream` → `TimelineProjector` → `encode_sse_bytes`）重放，收集 SSE 输出
4. 逐字节对比，差异必须可解释（如日志格式变更）或视为 bug

**此 gate 不通过，不进入 Phase 2。**

### Phase 2: 拆分 Projection 和 Adapter

1. 新建 `gateway/timeline/types.py`，定义 `TimelineEvent` dataclass 联合类型
2. 新建 `gateway/timeline/projection.py`，从 `TimelineProjector` 提取纯映射逻辑
3. 新建 `gateway/timeline/lobehub_adapter.py`，从 `TimelineProjector` 提取适配逻辑
4. 新建 `gateway/timeline/sse_encode.py`
5. 重构 `gateway/timeline/stream.py`，只保留 `compose_sse_stream()`
6. 删除 `gateway/timeline/projector.py`

### Gate: Golden Comparison 回归验证（Phase 2 → Phase 3 之间）

Phase 2 完成后，再次执行 golden comparison：

1. 同一组 JSONL 输入，经新链路（`EventStream` → `TimelineProjection` → `LobeHubSSEAdapter` → `encode_sse`）输出
2. 与 Phase 1 gate 的 golden output 逐字节对比
3. 差异必须可解释或视为 bug

**此 gate 不通过，不进入 Phase 3。**

### Phase 3a: 协议伪装 Deprecation（先观察，再切割）

1. `openai_compat_api.py` 中 agent 路径保留功能，但加 deprecation header + structlog warning
2. 修复该路径缺失的 `after_seq` 参数传递，使断线重连在旧路径也可用
3. 确认 LobeHub `AgentTimelineTransport` 已完全使用 `/v1/agent/runs`
4. 观察 `deprecated_agent_via_chat_completions` 日志，等待连续 7 天零触发

**迁移收益（不仅是清理）**：

当前 `/v1/chat/completions` 的 agent 路径调用 `session.bus.subscribe()` 时**不传 `after_seq`**，意味着客户端断线后无法重连回放。Phase 3a 即修复此问题，使旧路径也具备断线重连能力。

### Phase 3b: Hard Cut（确认零流量后）

1. `openai_compat_api.py` 中 agent 路径改为返回 400 + 迁移指引
2. 清理前端 patch 中残留的 chat.completions agent 路径

**兼容性验证清单**：

- [ ] LobeHub `AgentTimelineTransport` 已使用 `/v1/agent/runs` + `Last-Event-ID`
- [ ] `deprecated_agent_via_chat_completions` 连续 7 天零触发
- [ ] 前端 patch 中无残留的 chat.completions agent 路径
- [ ] 集成测试覆盖：断线 → 重连 → 回放缺失事件
- [ ] 集成测试覆盖：buffer gap → `reconnect.gap` 事件 → 客户端回退 JSONL 重放

---

## 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| `TimelineEvent` dataclass 序列化性能 | 低 | `dataclasses.asdict()` 或手写 `to_dict()`，dict 构造本身不是瓶颈 |
| LobeHub Adapter 遗漏边界 case | 中 | Phase 1→2 gate 的 golden comparison 覆盖 |
| EventStream 与 Journal 类型不匹配 | 低 | EventStream 泛型参数化，`StampedEvent` 类型不变 |
| 前端 patch 未适配新端点 | 低 | Phase 3a 先 deprecation 观察零流量，Phase 3b 再 hard cut；旧路径同步修复 `after_seq` |
| `_finalize_run` teardown 顺序错误 | 低（已缓解） | 嵌套 `finally` 保证步骤 3-5 必定执行；步骤 1-2 失败记 structlog error 不阻塞后续 |
| per-subscriber overflow 阈值不当 | 低 | `_OVERFLOW_THRESHOLD=3` 作为初始值，通过 `queue_utilization` structlog 指标观察实际分布后调优 |
| Buffer gap 导致断线重连失败 | 中 | `subscribe()` 检测 gap 并 yield `GapEvent`；消费侧可回退 JSONL 重放；集成测试覆盖 |
| JSONL consumer 注册前丢事件 | 低（已消除） | `register_subscriber()` 同步注册在 `create_run_session` 返回前完成，无竞态窗口 |
| Adapter 状态泄漏（长 run） | 低（已消除） | `_adapt_tool_end()` 清理 `_pending` 和 `_exec_buf` 中对应条目 |
| `subscribe()` 回放阶段阻塞 event loop | 低（已缓解） | 回放阶段每 64 个事件 `await asyncio.sleep(0)` 做 cooperative yield |
| `close()` 时 queue 已满导致 sentinel 丢失 | 低（已缓解） | `close()` 捕获 `QueueFull`，强制清空一个位置后投递 sentinel |

---

## 总结

| 维度 | 旧 | 新 |
|---|---|---|
| **层次数** | 7 | 4 |
| **核心概念数** | 7 (Journal, Hub, Projector, EventBus, Subscribe, TimelineProjector, SSE Encode) | 4 (EventStream, Projection, Adapter, SSE Encode) |
| **排查路径** | 6 步，含 1 个观测盲区 | 4 步，每步可独立验证 |
| **类型安全** | 裸 dict 贯穿全链路 | frozen dataclass 联合类型，mypy Union narrowing |
| **新前端接入** | 改 Projection（混杂适配） | 替换 Adapter，Projection 不动；`compose_sse_stream` 支持注入自定义 adapter |
| **新事件类型** | 改 dispatch table + 适配逻辑混在一起 | Projection handler + Adapter case，职责分离 |
| **前端格式变更** | 改 Projection（含非投影逻辑） | 只改 Adapter |
| **JSONL 落盘** | 通过 Hub projector | 普通 asyncio consumer，同步注册保证不丢事件 |
| **Run teardown** | execute_run / _resume_run 两处重复 finally | 统一 `_finalize_run(session, registry)` |
| **环形缓冲** | `list.pop(0)` O(n) | `deque(maxlen=N)` O(1) |
| **溢出处理** | 静默移除 subscriber | 连续 N 次溢出才移除，单次记 warning + queue_utilization |
| **订阅原子性** | 先回放再注册（竞态窗口） | `subscribe()` 原子化：注册 → 回放 → live |
| **Buffer gap** | 无检测，静默丢事件 | `GapEvent` 信号 + 消费侧可回退 JSONL |
| **断线重连** | `/v1/chat/completions` 路径不支持 | Phase 3a 旧路径修复 `after_seq`；Phase 3b 迁移到 `/v1/agent/runs/{id}/timeline` + `Last-Event-ID` |
| **协议迁移** | 直接 hard cut | Phase 3a deprecation 观察 → Phase 3b 零流量后 hard cut |
| **迁移验证** | 无 | Phase 间 golden comparison gate |
| **代码行数（估计）** | ~1100 行 | ~800 行（减少重复和间接层） |
