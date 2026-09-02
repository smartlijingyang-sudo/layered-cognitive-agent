# ADR-0113: 启动 Trace 第一公民 + Sink Seam

> **状态：** Superseded by [ADR-0116](./0116-boot-event-observability-convergence.md)
> **日期：** 2026-08-31
> **说明：** 初版提议 `TraceSink / JsonlFileSink / JournalSink` 三概念,被 3 个 subagent 评审一致 YAGNI;`bundles/observability-default.yaml` + `traces/lca_trace.jsonl` + `JournalEngine` 已覆盖 boot 可观测。ADR-0116 收敛后,本文档所有概念全部由 ADR-0116 接管,**未实现任何代码**。
> **配套 ADR：** [ADR-0083](./0083-deepseek-harness-plugin-implementation-plan.md) W7 Evidence/Replay · [ADR-0063](./0063-run-trace-ssot.md) 运行事件账本 SSOT · [ADR-0065](./0065-recoverable-evidence-ledger.md) 证据保真 · [ADR-0111](./0111-startup-compilation-as-subpackage.md) 启动编译化
>
> ⚠️ **本文被 [ADR-0116](./0116-boot-event-observability-convergence.md) 合并/废弃。3 个 subagent 评审一致认为 `TraceSink / JsonlFileSink / JournalSink` 是 YAGNI(已有 `bundles/observability-default.yaml` + `traces/lca_trace.jsonl` 覆盖),`lca-ops trace boot` 跟 `lca-ops logs --replay` 80% 重叠。详见 ADR-0116 §"为什么砍掉"。**

## 背景

`lca/harness/profile/boot.py` 当前对启动过程的可见性:

1. **裸 stdout**:`print(text, flush=True)`(L191, `gateway/app.py`)
2. **structlog 在 module-load 时跑副作用**:`_configure_structlog()`(L109–117)
3. **三条路径分叉**:boot stdout、structlog stderr、journal(目前 boot 不写 journal)
4. **启动失败时**:`except BaseException: await _dispose_context(ctx); raise` —— 只在内存里 dispose,trace 数据丢失
5. **`lca-ops journal logs --replay`** 对启动阶段空白,失败诊断只能靠 grep stdout

deepseek-harness 在 `host/audit-log` 包里实现了完整 trace 系统:

```typescript
// host/audit-log/src/writer.ts
export class AuditLogWriter {
  static Config = z.object({
    root: z.string().default('./traces/audit'),
    retention: z.number().default(30),
  })
  append(event: AuditEvent): void  // 同步追加 JSONL
  flush(): void
  dispose(): void
}
```

每个 `AuditLogService` 注册一个 writer 到 audit-log seam,默认走 JSONL 文件,可被替换为 stdout/Sentry/OTel。

## 决定

### 决定 1:`TraceEvent / Trace` 不可变数据类

新建 `lca/contracts/models/observability/trace.py`:

```python
@dataclass(frozen=True, slots=True)
class TraceEvent:
    ts: float                  # time.time()
    iso: str                   # datetime.now(timezone.utc).isoformat()
    stage: str                 # Stage 枚举值
    plugin_id: str | None
    duration_ms: float | None
    status: Literal["start", "ok", "fail", "skip"]
    detail: Mapping[str, Any]  # frozen + MappingProxyType

@dataclass(frozen=True, slots=True)
class Trace:
    profile_path: str
    started_at: float
    events: tuple[TraceEvent, ...]
    manifest_hash: str
    outcome: Literal["booted", "failed", "disposed"]
    failure: BaseException | None = None
```

`Trace.events` 是 append-only,`Trace` 本身冻结。这是 ADR-0063 "Journal-as-Truth" 在启动阶段的投影,结构与 SessionEventMap 对齐。

### 决定 2:`TraceSink` Protocol(L0 seam)

```python
class TraceSink(Protocol):
    """Append TraceEvent; flush on demand; dispose on shutdown."""
    name: str
    def append(self, event: TraceEvent) -> None: ...
    def flush(self) -> None: ...
    def dispose(self) -> None: ...
```

`lca/contracts/protocols/trace_sink.py` 定义,`lca/contracts/protocols/trace_sink_registry.py` 定义注册表:

```python
class TraceSinkRegistry(Protocol):
    def register(self, sink: TraceSink) -> Callable[[], None]: ...
    def append(self, event: TraceEvent) -> None: ...   # fan-out
    def flush(self) -> None: ...
```

注册返回 disposer(沿用 deepseek `registry.register() returns () => void`)。

### 决定 3:`JsonlFileSink` 默认实现

`lca/harness/trace/sinks/file.py`:

```python
class JsonlFileSink:
    """Append-only JSONL file sink. One file per UTC day under root.

    Each line is a JSON-encoded TraceEvent. Synchronous writes; boot
    trace volume is low (≤ 200 events per boot).
    """
    def __init__(self, root: Path, retention: int = 7):
        self._root = root
        self._retention = retention
        self._fp = self._open_today()
        self._lock = threading.Lock()

    def append(self, event: TraceEvent) -> None:
        with self._lock:
            self._fp.write(json.dumps(asdict(event), default=str) + "\n")

    def flush(self) -> None:
        with self._lock:
            self._fp.flush()

    def dispose(self) -> None:
        with self._lock:
            self._fp.close()
            self._enforce_retention()

    def _enforce_retention(self) -> None:
        # 删除 N 天前的 jsonl 文件,沿用 deepseek retention 策略
        ...
```

同步写 + 锁 = 简单正确(启动 trace 体积小,不需要异步)。

### 决定 4:`JournalSink` 可选转发

`lca/harness/trace/sinks/journal.py`:

```python
class JournalSink:
    """Forward boot TraceEvent to Journal as well.

    让 lca-ops journal logs --replay 能 replay 启动阶段。
    """
    def __init__(self, journal: Journal):
        self._journal = journal

    def append(self, event: TraceEvent) -> None:
        self._journal.append({
            "kind": "boot.trace",
            "stage": event.stage,
            "status": event.status,
            "plugin_id": event.plugin_id,
            "duration_ms": event.duration_ms,
            "iso": event.iso,
            **event.detail,
        })
```

启用后启动事件进入 Journal Catalog,跟 SessionEventMap 同一检索接口。

### 决定 5:启动期自动装载 + lifecycle 联动

`compilation/__init__.py` 在 `compile_profile` 末尾自动:

```python
def compile_resolved(resolved, *, bootstrap_file_store=None) -> Context:
    ctx = Context()
    sinks = TraceSinkRegistry()
    ctx.provide("trace_sink_registry", sinks)

    # 1. plugin 自动 emit TraceEvent(stage=FIBER_SPAWN.start/ok/fail)
    #    通过 ctx.inject("trace_sink_registry").append(...)
    # 2. boot 末尾 _install_observability(sinks) → Trace
    # 3. ctx.effect(sinks.dispose, label="trace_sinks_dispose")
    ...
```

`Lifecycle 联动`:
- startup:TraceSinkRegistry 创建 → sink register 在 profile/bundle 中声明
- 每个 stage(FIBER_SPAWN.start/.ok/.fail)emit event
- observability install 后 `Trace = Trace(events=tuple(events))` 挂到 ctx scope
- shutdown:registry.dispose() → 所有 sink flush + close + retention cleanup

### 决定 6:lca-ops 子命令

新增 `lca-ops trace boot` 子命令:

```sh
$ lca-ops trace boot --tail 100       # 最近 100 个启动 event
$ lca-ops trace boot --since 1h       # 最近 1 小时
$ lca-ops trace boot --profile web-standard  # 按 profile 过滤
$ lca-ops trace boot --failures       # 仅失败 event
$ lca-ops trace boot --json           # JSON 输出,管道给 jq
```

读取 `traces/boot/*.jsonl`,沿用 lca-ops 现有 `--json` 输出格式(AGENTS.md §6 要求)。

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0063 运行事件账本 SSOT | 本 ADR 是 ADR-0063 在启动阶段的延伸;boot trace 通过 `JournalSink` 投影到 Journal |
| ADR-0065 证据保真 | 启动 trace 也是可恢复证据的一部分;`failure` 字段保留原始异常 |
| ADR-0083 W7 Evidence/Replay | 本 ADR 是 W7 的"启动"子集实现 |
| ADR-0111 启动编译化 | trace emit hook 由 compilation/fiber.py 在 spawn_fiber 内调用,不再由 boot.py 拼接 |
| ADR-0112 Gateway 路由 plugin 化 | `lca-trace-file-sink` / `lca-trace-journal-sink` plugin 跟路由 plugin 同层,统一通过 `bundle/web-app.yaml` 装载 |

## CI 门禁

新增:

- `tests/harness/trace/test_sink_base.py`:`TraceSink` Protocol 一致性,所有实现必须满足协议 + dispose 不抛。
- `tests/harness/trace/test_jsonl_sink.py`:append 幂等性 + retention 清理路径 + 并发 append 安全。
- `tests/harness/trace/test_journal_sink.py`:boot event 进入 Journal 后能被 `lca-ops trace boot --replay` 检索。
- `tests/harness/profile/compilation/test_trace_emitted.py`:启动流程 emit 的 event 数 ≥ N,与 manifest_hash 一致。
- `tests/test_lca_ops_trace.py`:`lca-ops trace boot` 子命令的 --tail / --since / --json 行为。

## 放弃的方案

- **同步 stdout,放弃文件 sink**:deepseek 走 stdout 是 CLI 友好的,但 server 模式下 stderr 容易丢;文件 + retention 是默认。
- **异步写(aiofiles / orjson)**:启动 trace 体积小,同步已经够;避免引入额外依赖。
- **不实现 JournalSink,只走文件**:违背 ADR-0063 "Journal 事实源" 精神;启动事件也是模型可见事实的派生,应该在 Journal 里有位置。
- **直接在 boot.py 里写文件**:违反 ADR-0111 拆分原则;trace sink 是独立 seam,任何 plugin 都可以往里写。

## 后果

正面:
- 启动过程有结构化 trace,失败可回放,`lca-ops trace boot` 一条命令诊断。
- 启动事件进入 Journal,跟 SessionEventMap 同一检索接口。
- sink seam 可被替换:未来加 Langfuse/Sentry/OTel 都只是新加一个 TraceSink plugin。
- 启动 stdout 的 `print(text, flush=True)` 死代码被消除。

负面:
- 启动期每个 fiber spawn 多一次 dict 序列化 + 写文件,实测延迟 < 1ms,体积 < 1MB/boot,可接受。
- `traces/boot/` 目录需要 CI 自动清理(已由 sink retention 处理)。

## 索引

| 主题 | 文档 |
|---|---|
| deepseek audit-log writer | `~/deepseek-harness/packages/host/audit-log/src/writer.ts` |
| deepseek audit-log plugin | `~/deepseek-harness/packages/host/audit-log/src/plugin.ts` |
| TraceEvent / Trace 数据 | `lca/contracts/models/observability/trace.py` |
| TraceSink Protocol | `lca/contracts/protocols/trace_sink.py` |
| JsonlFileSink | `lca/harness/trace/sinks/file.py` |
| JournalSink | `lca/harness/trace/sinks/journal.py` |
| compilation emit hook | `lca/harness/profile/compilation/fiber.py` |
| 运行事件账本 SSOT | [ADR-0063](./0063-run-trace-ssot.md) |
| 证据保真 | [ADR-0065](./0065-recoverable-evidence-ledger.md) |
| 启动编译化 | [ADR-0111](./0111-startup-compilation-as-subpackage.md) |