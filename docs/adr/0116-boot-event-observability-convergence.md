# ADR-0116: 启动事件词表与可观测性收敛(合并原 ADR-0113 + 0114)

> **状态：** Proposed
> **日期：** 2026-08-31
> **配套 ADR：** [ADR-0063](./0063-run-trace-ssot.md) 运行事件账本 SSOT · [ADR-0085](./0085-plugin-everything-explained.md) 插件哲学 · [ADR-0115](./0115-kernel-transport-boundary.md) Kernel/Transport 边界
>
> **Supersedes:** [ADR-0113](./0113-boot-trace-first-class-citizen.md) 启动 Trace 第一公民 · [ADR-0114](./0114-boot-event-catalog-increment.md) 启动事件词表增量

## 背景

[ADR-0113](./0113-boot-trace-first-class-citizen.md) 初版提议引入 3 个新概念(`TraceSink / JsonlFileSink / JournalSink`)+ 独立文件路径 `traces/boot/*.jsonl`+ `lca-ops trace boot` 子命令。[ADR-0114](./0114-boot-event-catalog-increment.md) 初版提议 5 个 typed JournalEvent。

3 个 subagent 评审一致发现:

| 问题 | 来源 | 严重程度 |
|---|---|---|
| ADR-0113 引入的 3 个新概念与现有 `bundles/observability-default.yaml` + `traces/lca_trace.jsonl` + `JournalEngine` **平行 schema**,违反 ADR-0063 I1 "一次发生一次追加" | 最小改动 + SSOT | BLOCK |
| `JournalSink` 走 `kind: 'boot.trace'` 扁平字段,与 ADR-0114 typed JournalEvent 在同一 Journal 双写,consumer 必须知道两条路径 | 架构 | BLOCK |
| `lca-ops trace boot` 与 `lca-ops logs --replay` 在功能上有 ≥ 80% 重叠(都是按时间窗 + filter 查启动事件),两个 CLI 子命令读两个不同文件,用户被迫猜该用哪个 | 最小改动 | FLAG |
| Stage 词汇在 ADR-0113 (TraceEvent.stage: str) 与 ADR-0114 (BootLifecycleFailed.stage: Literal[...]) 与 ADR-0111 (Stage 枚举) 4 处独立定义,不一致 | 架构 + SSOT | BLOCK |

本 ADR 在 [ADR-0115](./0115-kernel-transport-boundary.md) 决定 1 表中 K5(观测装配)与 K6(可观测 trace 数据)基础上,**收敛** boot 期可观测性。

## 决定

### 决定 1:砍 `TraceSink / JsonlFileSink / JournalSink` 与独立文件路径

**砍掉**(YAGNI):
- `lca/contracts/protocols/trace_sink.py` —— `TraceSink` Protocol
- `lca/contracts/protocols/trace_sink_registry.py` —— `TraceSinkRegistry` Protocol
- `lca/harness/trace/sinks/file.py` —— `JsonlFileSink`
- `lca/harness/trace/sinks/journal.py` —— `JournalSink`
- `lca/plugins/observability/trace_file.py` —— `lca-boot-trace-file-sink` plugin
- `lca/plugins/observability/trace_journal.py` —— `lca-boot-trace-journal-sink` plugin
- `bundles/observability.yaml`(新建)—— 已被 `bundles/observability-default.yaml` 覆盖
- `traces/boot/*.jsonl` 独立目录
- `lca-ops trace boot` 子命令(改用 `lca-ops logs --scope boot`)

**理由**:
- 现有 `lca/infrastructure/observability/journal/` + `bundles/observability-default.yaml` 已经覆盖 boot 可观测性需求
- 新增第三条文件路径会导致"同一事实写多份",违反 ADR-0063 I1
- 启动失败时已经有 `BootLifecycleFailed` JournalEvent + existing journal sink 自动记录(无需新 sink)

### 决定 2:5 个 typed event 收敛为 3 个 + 2 个走 RuntimeObserved

| 原 ADR-0114 的 5 个 event | 命运 | 理由 |
|---|---|---|
| `BootProfileResolved` | **保留** | 真事实:profile resolve 完成的最终状态;不与 RuntimeObserved 重叠 |
| `BootPluginFiberSpawned` | **保留** | 真事实:每个 plugin 的 Fiber spawn 开始/结束;agent 是观察对象,不是 runtime 解释 |
| `BootObservabilityAssembled` | **保留** | 真事实:观测 seam 装配结果;BoundObservability 的 SSOT |
| `BootTraceFlushed` | **改走 RuntimeObserved(operation='boot.trace.flush', source='lca-kernel.dispose')** | 是 kernel 的运行解释,非事实;ADR-0063 RuntimeObserved 已是统一解释原语 |
| `BootLifecycleFailed` | **改走 RuntimeObserved(operation='kernel.lifecycle.fail', source='lca-kernel.lifecycle', failure_kind=...)** | 是 process 生命周期的解释,非事实;复用 ADR-0063 RuntimeObserved 即可 |

**关键**:3 个 typed event + 2 个 RuntimeObserved = 完整 boot 可观测性,**全部走 `lca_journal.jsonl`**(现有 Journal sink),无平行文件。

### 决定 3:Stage 词汇 SSOT = `lca-kernel/stages.py:Stage(IntEnum)`

```python
# lca-kernel/stages.py
from enum import IntEnum

class Stage(IntEnum):
    """启动阶段 SSOT,被 BootJournalEvent stage 字段强引用。

    扩展必须通过 ADR 走 C1 闭集流程;不允许在文件中新增字面量。

    Why a dedicated module
    ----------------------
    Stage 词汇在 4 个文件中独立定义(原 ADR-0111/0113/0114),consumer
    拼字符串易引入 typo。本枚举是 Stage 值的唯一权威定义。
    """
    SOURCE = 1        # K1 输入 adapter 阶段
    RESOLVE = 2       # K1 领域校验阶段
    TOPO = 3          # K1 DAG 拓扑排序
    PLAN = 4          # K2 Plan 编译
    BOOT = 5          # K3 cordis Context + Fiber 启动
    OBSERVABILITY = 6 # K5 BoundObservability 装配
```

**BootJournalEvent.stage** 全部引用 `Stage.X`,不允许字符串字面量。

### 决定 4:`BootProfileResolved` payload(沿用 ADR-0114)

```python
@dataclass(frozen=True, slots=True)
class BootProfileResolved:
    profile_path: str
    manifest_hash: str
    plugin_count: int
    bundle_count: int
    duration_ms: float
    topo_order: tuple[str, ...]   # 完整启动顺序,不是截断
```

### 决定 5:`BootPluginFiberSpawned` payload(收敛 ADR-0114 命名)

```python
from lca_kernel.stages import Stage  # 强引用,不允许 None

@dataclass(frozen=True, slots=True)
class BootPluginFiberSpawned:
    plugin_id: str
    layer: str                    # L0/L1/L2/L3/L4
    kind: str                     # seam/provider/primitive/bridge
    stage: Stage                  # 强类型,引用 lca-kernel.stages.Stage(IntEnum)
    duration_ms: float
    status: Literal["started", "ok", "failed"]
    failure_kind: str | None = None
    failure_message: str | None = None

    def __post_init__(self) -> None:
        # 兜底:不允许 Stage(0) 这种边缘值或 None
        if not isinstance(self.stage, Stage):
            raise TypeError(f"stage must be Stage enum, got {type(self.stage).__name__}")
        # Stage 起始值 1(ADR-0115 D4),允许 SOURCE(1)/RESOLVE(2)/TOPO(3)/PLAN(4)/BOOT(5)/OBSERVABILITY(6)
        if int(self.stage) < 1 or int(self.stage) > 6:
            raise ValueError(f"stage value {self.stage} out of [1, 6] range")
```

**关键修正**(评审 BLOCK + FLAG):
- `stage` 字段引用 `Stage` IntEnum,不再是字符串字面量
- `status` 统一 `started/ok/failed`(ADR-0113 写 `start/ok/fail`,不一致;以本 ADR 为准)
- `__post_init__` 双重断言:类型 + 值域;运行期拒绝任何不属于 `Stage` 枚举的 stage 字段
- Stage 起始值 1(ADR-0115 D4):跟 journal `seq`(从 0 开始)区分,日志可读性

### 决定 6:`BootObservabilityAssembled` payload(沿用 ADR-0114,简化)

```python
@dataclass(frozen=True, slots=True)
class BootObservabilityAssembled:
    bound_seams: tuple[str, ...]
    evidence_store_kind: str
    journal_enabled: bool
    duration_ms: float
```

`trace_sink_count` 字段删除(已无独立 trace sink seam)。

### 决定 7:`lca-ops logs --scope boot` 子命令(扩展现有 CLI)

不新增 `lca-ops trace boot`,扩展现有 `lca-ops logs`:

```sh
$ lca-ops logs --scope boot            # 仅启动阶段事件
$ lca-ops logs --scope boot --tail 50  # 最近 50 条
$ lca-ops logs --scope boot --since 1h # 最近 1 小时
$ lca-ops logs --scope boot --failures # 仅失败事件
$ lca-ops logs --scope boot --json     # JSON 输出
```

实现:`lca/infrastructure/cli/cli.py` 给 `logs` 子命令加 `--scope` flag,内部 filter journal 的 event.stage ∈ Stage enum。

**复用而非新建**:`lca-ops logs` 已经能按时间窗 + filter 查 journal,加 `--scope boot` 是 1 行改动。

### 决定 8:词表登记(沿用 ADR-0063 流程)

按 `lca/contracts/models/observability/journal_catalog.py` 注释的"新增事件"流程:

1. **`journal.py`** 加 3 个 frozen dataclass(`BootProfileResolved / BootPluginFiberSpawned / BootObservabilityAssembled`)+ `stage: Stage` 字段强引用 `lca-kernel/stages.py:Stage`
2. **`event_descriptors_data.py`** 在 `build_default_registry()` 末尾追加 3 行 `_descriptor(...)`:
   - `BootProfileResolved` → `kind="structural"`, `producer="lca-kernel.source_resolve"`, `consumer=["lca-ops logs --scope boot", "TraceInspector"]`
   - `BootPluginFiberSpawned` → `kind="structural"`, `producer="lca-kernel.boot"`, `consumer=["lca-ops logs --scope boot"]`, `aggregation="pairs"`
   - `BootObservabilityAssembled` → `kind="structural"`, `producer="lca-kernel.observability"`, `consumer=["lca-ops diagnose observability"]`
3. **`JOURNAL_EVENT_CLASSES`** dict 加 3 个 entry
4. **CI 守卫**:`tests/test_observability_boundary.py` 自动断言 frozen dataclass 与 descriptor 1:1

**BootTraceFlushed + BootLifecycleFailed 不加 typed dataclass**;走 `RuntimeObserved(operation=..., source='lca-kernel.X')` 复用 ADR-0063 既有路径。

### 决定 9:`lca-kernel/trace.py` 保留(轻数据类,不建 sink seam)

```python
# lca-kernel/trace.py
@dataclass(frozen=True, slots=True)
class BootTrace:
    """in-memory snapshot of one boot's stages;不写入文件。

    只在进程内供 kernel 自身诊断 / 测试用;持久化走 JournalEvent。
    """
    profile_path: str
    started_at: float
    stages: tuple[tuple[Stage, float, Literal["ok", "failed"]], ...]
    outcome: Literal["booted", "failed", "disposed"]
    failure: BaseException | None = None
```

**关键**:`BootTrace` 是**只读数据类**,**不**新建 `TraceSink` 接口;LCA 已经有 Journal sink,BootTrace 跟 Journal 不冲突(后者是结构化事实流,前者是 in-memory snapshot)。

## 对既有 ADR 的修订

### ADR-0113 整体废弃

| 原内容 | 本 ADR |
| |---|| `TraceSink / TraceSinkRegistry` Protocol | 砍 |
| `JsonlFileSink`(含原子写语义、retention、micro-batch) | 砍 |
| `JournalSink` | 砍 |
| `lca-ops trace boot --tail/since/profile/failures/json` | 砍 |
| `traces/boot/*.jsonl` 文件路径 | 砍 |
| `bundles/observability.yaml`(新建) | 砍(用现有 `bundles/observability-default.yaml`) |
| Stage 词汇(str 字面量) | 改用 `Stage` IntEnum(本 ADR 决定 3) |

### ADR-0114 精简

| 原内容 | 本 ADR |
| |---|| 5 个 typed event | 3 个 typed + 2 个 RuntimeObserved |
| `BootLifecycleFailed.stage` Literal[5 个] | 引用 `Stage` IntEnum |
| `BootLifecycleFailed.traceback_head`(前 5 帧) | 删除(走 RuntimeObserved 后由 `evidence_store` 接管) |
| `BootTraceFlushed` typed dataclass | 改走 RuntimeObserved |
| `lca-ops trace boot` 子命令 | 改 `lca-ops logs --scope boot` |
| `topo_order` 完整列表(可能 >100 plugin) | 保留,但加 size 限制(`lca-kernel/stages.py` 顶部 docstring 标注) |

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0063 Journal SSOT + RuntimeObserved 统一解释原语 | 本 ADR 复用 RuntimeObserved,不另起解释原语 |
| ADR-0083 W7 Evidence/Replay | 本 ADR 是 W7 的"启动"子集实现 |
| ADR-0115 Kernel/Transport 边界 | 本 ADR 是 ADR-0115 决定 1 表中 K5(观测装配)的具体实现 |

## CI 门禁

新增 / 复用:

- `tests/test_journal_catalog_boot_events.py`(新建):3 个 event dataclass 形状 + descriptor 完整性 + stage 字段强类型断言
- `tests/lca_kernel/test_stage_enum_is_ssot.py`(新建):Stage(IntEnum) 是 Stage 字段值的唯一来源,任何 typed event 的 stage 字段必须引用 `lca-kernel.stages.Stage`
- `tests/lca_kernel/test_no_trace_sink_seam.py`(新建):`grep -rE 'class.*Sink(?!Service)' lca/` 在 `trace_sink.py` / `trace_sink_registry.py` 之外必须为空(只在 `journal.py` 里的 `JournalSink` 存在)
- `tests/test_lca_ops_logs_scope_boot.py`(新建):`lca-ops logs --scope boot` 输出 filter 正确,跟 `lca-ops logs --scope all` 对比
- `tests/harness/profile/compilation/test_journal_emitted.py`(迁移):验证 boot 流程每个 stage emit 对应事件;走 `lca-kernel/` 而不是 `compilation/`
- `tests/test_observability_boundary.py`(扩展):新增 boot events 后,descriptor 必须存在

## 放弃的方案

- **保留 ADR-0113 全部内容(深 sink seam + JsonlFileSink + JournalSink)**:违反 ADR-0063 I1,且 YAGNI;`bundles/observability-default.yaml` + `traces/lca_trace.jsonl` 已覆盖。
- **保留 ADR-0114 全部 5 个 typed event**:与 RuntimeObserved 语义重叠,冗余;ADR-0063 RuntimeObserved 已是统一解释原语。
- **保留 ADR-0113 `lca-ops trace boot` 子命令**:与 `lca-ops logs --replay` 80% 重叠,用户被迫二选一。
- **Stage 词汇保留 str 字面量**:违反 ADR-0106 §4 "类型化优先于字符串";consumer 拼字符串易引入 typo。

## 后果

正面:
- boot 可观测性走 ADR-0063 单一路径(Journal + RuntimeObserved),无平行 schema
- 3 个 typed event + 2 个 RuntimeObserved 完整覆盖 boot 生命周期
- Stage IntEnum 是 SSOT,4 处独立定义 → 1 处
- `lca-ops logs --scope boot` 复用现有 CLI,新增 flag 仅 1 行
- 词条登记流程与 ADR-0063 完全一致,无需新增 schema 治理

负面:
- `bundles/observability.yaml`(如果之前按 ADR-0113 创建过)需要删除
- ADR-0113 `lca-ops trace boot` 命令如果已被 CI 使用需要迁移到 `lca-ops logs --scope boot`
- `traces/boot/` 目录如果已建需要删除
- 旧 tests(如果有引用 `TraceSinkRegistry` / `JsonlFileSink` / `JournalSink`)需要更新到新路径

## 索引

| 主题 | 文档 |
|---|---|
| deepseek audit-log 借鉴 | `~/deepseek-harness/packages/host/audit-log/src/{plugin,writer,service}.ts` |
| Journal SSOT | [ADR-0063](./0063-run-trace-ssot.md) |
| RuntimeObserved 统一解释原语 | [ADR-0063 §目标架构 三平面](./0063-run-trace-ssot.md) |
| Kernel/Transport 边界 | [ADR-0115](./0115-kernel-transport-boundary.md) |
| 启动编译化 | [ADR-0111](./0111-startup-compilation-as-subpackage.md) |
| 词表登记流程 | `lca/contracts/models/observability/journal_catalog.py`(注释段) |
| 现有观测基础设施 | `lca/infrastructure/observability/` + `bundles/observability-default.yaml` |