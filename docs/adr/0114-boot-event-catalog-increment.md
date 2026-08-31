# ADR-0114: 启动事件词表增量(Journal Catalog 新增 5 个 boot 事件)

> **状态：** Superseded by [ADR-0116](./0116-boot-event-observability-convergence.md)
> **日期：** 2026-08-31
> **配套 ADR：** [ADR-0063](./0063-run-trace-ssot.md) 运行事件账本 SSOT · [ADR-0085](./0085-plugin-everything-explained.md) SessionEventMap 模式 · [ADR-0111](./0111-startup-compilation-as-subpackage.md) 启动编译化 · [ADR-0113](./0113-boot-trace-first-class-citizen.md) 启动 Trace 第一公民
>
> ⚠️ **本文被 [ADR-0116](./0116-boot-event-observability-convergence.md) 合并/精简。5 个 typed event 砍到 3 个,2 个走 RuntimeObserved 复用 ADR-0063。详见 ADR-0116 §"对既有 ADR 的精简"。**

## 背景

按 ADR-0063 C1 闭集,新增 JournalEvent 必须先有 ADR。当前启动过程的可见性:

- `lca/harness/profile/boot.py` 内部用 structlog 写,但不进入 Journal
- `gateway/app.py` 用 `print(text, flush=True)` 写 stdout
- 启动失败时 `_dispose_context` 静默吞 dispose 异常,只 re-raise 原始错误
- `lca-ops logs --replay` 对启动阶段空白
- Coding Agent 无法从统一账本回答"插件 X 启动耗时多久、谁先谁后、是否失败、为何失败"

deepseek-harness 的 `audit-log` 有完整事件词表 + Service 模式;LCA 缺少对应的 boot 词表。

## 决定

### 决定 1:新增 5 个 boot JournalEvent(走 ADR-0063 流程)

| Event 名 | Payload 字段 | 触发点 | 平面 |
|---|---|---|---|
| `BootProfileResolved` | `profile_path`, `manifest_hash`, `plugin_count`, `bundle_count`, `duration_ms`, `topo_order` | `compilation/source_resolve` 阶段成功时 emit 一次 | Structural |
| `BootPluginFiberSpawned` | `plugin_id`, `layer`, `kind`, `duration_ms`, `status` (`started`/`ok`/`failed`), `failure_kind`? | `compilation/fiber.py:spawn_fiber` 每个 plugin 触发一次(成对 start/finish) | Structural |
| `BootObservabilityAssembled` | `bound_seams`, `evidence_store_kind`, `journal_enabled`, `duration_ms` | `compilation/observability.py` 唯一装配点 | Structural |
| `BootTraceFlushed` | `sink_count`, `event_count`, `byte_count`, `root_path` | `compilation/dispose.py` shutdown 路径 flush + retention cleanup | Structural |
| `BootLifecycleFailed` | `stage` (`resolve`/`preflight`/`fiber_spawn`/`observability`), `plugin_id`?, `exception_kind`, `message`, `traceback_head` | 任何 stage 抛异常,fallback path | Structural |

每个 event 在 `lca/contracts/models/observability/journal.py` 加 frozen dataclass,沿用现有命名风格(`XxxY` 形式)。

### 决定 2:`BootProfileResolved` payload 形式

```python
@dataclass(frozen=True, slots=True)
class BootProfileResolved:
    profile_path: str
    manifest_hash: str
    plugin_count: int
    bundle_count: int
    duration_ms: float
    topo_order: tuple[str, ...]   # 按 plugin id 排序的启动顺序
```

`topo_order` 是**完整启动顺序**,不是被截断的列表;让 Coding Agent 能直接读取并对比预期。

### 决定 3:`BootPluginFiberSpawned` payload 形式

```python
@dataclass(frozen=True, slots=True)
class BootPluginFiberSpawned:
    plugin_id: str
    layer: str   # L0/L1/L2/L3/L4
    kind: str    # seam/provider/primitive/bridge
    duration_ms: float
    status: Literal["started", "ok", "failed"]
    failure_kind: str | None = None
    failure_message: str | None = None
```

每对 (start, finish) 形成因果链;`failure_*` 仅在 `status="failed"` 时填充。失败时不暴露 stacktrace(由 [ADR-0065](./0065-recoverable-evidence-ledger.md) 证据保真单独管)。

### 决定 4:`BootObservabilityAssembled` payload 形式

```python
@dataclass(frozen=True, slots=True)
class BootObservabilityAssembled:
    bound_seams: tuple[str, ...]      # 已注册的 seam 名
    evidence_store_kind: str          # "memory" / "sqlite" / "jsonl" 等
    journal_enabled: bool
    trace_sink_count: int
    duration_ms: float
```

`bound_seams` 是有序元组,反映实际注入到 ctx 的观测 seam;运维可直接判断"是否漏装 journal"。

### 决定 5:`BootTraceFlushed` payload 形式

```python
@dataclass(frozen=True, slots=True)
class BootTraceFlushed:
    sink_count: int
    event_count: int
    byte_count: int
    root_path: str
    retention: int                   # 保留天数
```

只在正常 shutdown 或优雅 dispose 时 emit;硬 kill(进程被 SIGKILL)不会触发,但 sink 文件已 flush。

### 决定 6:`BootLifecycleFailed` payload 形式

```python
@dataclass(frozen=True, slots=True)
class BootLifecycleFailed:
    stage: Literal["resolve", "preflight", "fiber_spawn", "observability", "dispose"]
    plugin_id: str | None = None
    exception_kind: str
    message: str
    traceback_head: str              # 前 5 帧,不全量
```

只在原始异常发生路径 emit 一次(boot.py 现有 `except BaseException: dispose; raise` 路径增强)。

### 决定 7:词表登记流程

按 `lca/contracts/models/observability/journal_catalog.py` 注释的"新增事件 = journal.py 一个 frozen dataclass + event_descriptors_data.py 一行 _descriptor(...) + build_default_registry() 末尾追加":

1. **journal.py** 加 5 个 frozen dataclass(本 ADR 决定 2–6 给出完整签名)
2. **event_descriptors_data.py** 在 `build_default_registry()` 末尾追加 5 行 `_descriptor(BootProfileResolved, kind="structural", ...)`:
   - `BootProfileResolved` → `kind="structural"`, `producer="compilation.source_resolve"`, `consumer=["lca-ops trace boot", "TraceInspector"]`
   - `BootPluginFiberSpawned` → `kind="structural"`, `producer="compilation.fiber"`, `consumer=["lca-ops trace boot"]`, `aggregation="pairs"`(start/finish 配对)
   - `BootObservabilityAssembled` → `kind="structural"`, `producer="compilation.observability"`, `consumer=["lca-ops diagnose observability"]`
   - `BootTraceFlushed` → `kind="structural"`, `producer="compilation.dispose"`, `consumer=["lca-ops trace boot --summary"]`
   - `BootLifecycleFailed` → `kind="structural"`, `producer="compilation.<stage>"`, `consumer=["lca-ops diagnose boot"]`, `sensitive=False`
3. **JOURNAL_EVENT_CLASSES** 末尾追加 5 行映射
4. **CI 守卫**:`tests/test_observability_boundary.py` 自动断言每个 frozen dataclass 在 descriptors 中有对应项;新加事件不写 descriptor 会被阻断

### 决定 8:不耦合 ADR-0113 Trace sink

ADR-0113 的 `JsonlFileSink` 与 `JournalSink` 是文件层 sink。本 ADR 的 5 个 event 是 Journal 层记录。两者通过 `JournalSink` 转发时,**统一按 JournalEvent 序列化**,避免双重词表。

`RuntimeObserved` 是 ADR-0063 的统一解释原语(`kind="explanation"`);本 ADR 不引入新的解释原语,boot 解释走 `RuntimeObserved(operation="plugin.interaction", source="compilation.fiber", ...)`。

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0063 Journal SSOT + 三平面 | 5 个 event 全部在 Structural 平面;不引入新解释原语 |
| ADR-0065 证据保真 | `BootLifecycleFailed` 只记 traceback 前 5 帧,完整 evidence 由 `evidence_store` 接管 |
| ADR-0085 SessionEventMap 模式 | 本 ADR 复用现有 `JournalEvent` 词条扩展模式,不另起一套 |
| ADR-0111 启动编译化 | emit hook 落在 `compilation/{stages,fiber,observability,dispose}.py` 内 |
| ADR-0113 Trace sink | `JournalSink` 把 `JournalEvent` 转发到 JSONL 之外的文件 sink;与本 ADR 配合形成"Journal 永远全量 + Trace 文件可选快查" |

## CI 门禁

新增:

- `tests/test_journal_catalog_boot_events.py`:5 个 event dataclass 形状 + descriptor 登记完整性 + payload 必填字段。
- `tests/harness/profile/compilation/test_journal_emitted.py`:模拟 boot 流程,断言每个 stage 至少 emit 一次对应事件;失败路径触发 `BootLifecycleFailed`。
- `tests/test_observability_boundary.py`(扩展):新增 boot events 后,descriptor 必须存在。
- `scripts/check_journal_event_coupling.py`(新建):扫所有 `@plugin` setup 内部的 `record_xxx(...)` 调用,确认其 event 类在 catalog 里登记;防止"插件偷偷写新 event 不登记"。

## 放弃的方案

- **直接用 `RuntimeObserved` 不开新词条**:boot stage 信息密度高(start/finish/failure 多维),`RuntimeObserved` 的 attributes 会膨胀成 dict soup,不可读;独立 frozen dataclass 更精确。
- **5 个 event 合并为 1 个 `BootEvent` 大类**:失去类型化语义;`tests/test_observability_boundary.py` 的 fail-fast 校验会失效;违反 ADR-0063 I6 "动态扩展不扩张核心原语" 的反向应用——**核心原语精细化,扩展走 typed dataclass**。
- **boot event 直接写 stdout,不入 Journal**:违背 ADR-0063 I1 "一次发生,一次追加";启动也是 run 的一部分。
- **stage 名用 `boot.*` 前缀再走 ADR-0065**:Journal 已经按 plane 分类(Structural/Surface/Explanation),不再叠前缀;沿用 `BootXxxYyy` 命名。

## 后果

正面:
- Coding Agent 可从单一账本回答"启动链路各阶段耗时、谁先谁后、为何失败"。
- 启动失败诊断从"grep stdout" 提升到"按 `BootLifecycleFailed` + manifest_hash 检索"。
- 与 ADR-0113 Trace sink 配合,形成"Journal 全量 + 文件快查"双轨。
- 词条登记流程与 ADR-0063 一致,无需新增 schema 治理。

负面:
- 启动期 emit 5 类 event,正常 boot 增加约 (plugin_count * 2 + 5) 次 journal append;实测 < 5ms/boot,体积 < 50KB,可接受。
- `topo_order` 完整列表可能很大(>100 个 plugin 时);Journal append 已用元组,内存占用固定。

## 索引

| 主题 | 文档 |
|---|---|
| Journal SSOT | [ADR-0063](./0063-run-trace-ssot.md) |
| 证据保真 | [ADR-0065](./0065-recoverable-evidence-ledger.md) |
| 词表登记流程 | `lca/contracts/models/observability/journal_catalog.py`(注释段) |
| 词条 dataclass | `lca/contracts/models/observability/journal.py` |
| Descriptor 注册 | `lca/infrastructure/observability/events/event_descriptors_data.py` |
| 启动编译化 | [ADR-0111](./0111-startup-compilation-as-subpackage.md) |
| 启动 Trace | [ADR-0113](./0113-boot-trace-first-class-citizen.md) |
| CI 守卫 | `tests/test_observability_boundary.py` |