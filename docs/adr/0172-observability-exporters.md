# ADR-0172: Observability Exporters —— metrics/OTel/Langfuse 出口实现层

## 状态

**Proposed — 2026-09-02**

> **被 ADR-0170 引用**: Exporters 在 loop 维度以 `LoopProjectionDefinition` 实现,注册到 `ProjectionHost`,不挂在 cursor(继承 ADR-0169 五缝原则)。
> **隔离**: 本 ADR 只覆盖"出口实现层",与 ADR-0169 五缝架构(控制 / 投影宿主 / 持久化 / 模型可见 / 关闭屏障)严格正交。

## 一句话

metrics / OTel trace / Langfuse 等第三方观测系统的**Exporter 实现**,以 `LoopProjectionDefinition` 实现层注册到 `ProjectionHost`(ADR-0170);Profile YAML 控制选配;与 ADR-0169 五缝完全正交,不污染 cursor 控制面。

## 背景

ADR-0168-final §"不在本 ADR 范围"列第 4 项 "OTel / Langfuse 投影路径",评审山姆 §潜在 #14 处决:"metrics/OTel『也算本 ADR』/ 范围渗透 → 观测厂商集成与状态机 PR 抢车道"。

本 ADR 明确边界: **ADR-0169 / 0170 钉五缝,cursor + ProjectionHost + PersistenceCoordinator + ModelVisibleCapture + CloseBarrier 是项目本身;第三方 Exporter 是本 ADR 单独范围**。ADR-0168-final 把这两层合并,本 ADR 拆分。

正确分解:

| 层 | 组件 | ADR | 验收 |
|---|---|---|---|
| **实现层** | Exporter(每家厂商)LoopProjectionDefinition 实现 | **本 ADR** | metrics / trace / LLM-as-judge 都能 register 到 host |
| **协议层** | `ProjectionHost.register(def)` / `drive` / `flush_all` / `close` | ADR-0170 | 与 Exporter 实现无关 |
| **控制层** | `LoopCursor.advance / record_* / halt / close / fork` | ADR-0169 | 与 Exporter 完全无关 |

**关键不变量**:ADR-0169 五缝 → cursor 完全不知道 Exporter 存在;ADR-0170 ProjectionHost 不知道 Exporter 是"系统内置"还是"第三方";本 ADR 的 Exporter 只是注册到 host 的若干 `LoopProjectionDefinition` 实现,**不依赖** cursor 任何字段,**不依赖** host 的内部 backup。

## 第一性原理

### P1 · Exporter 是 adapter,不属于核心
与 ADR-0044 Code Sandbox Adapters 同源:对接每家厂商的适配层是 adapter,放 `@plugin/runtime/observability/exporters/...`(ADR-0074 命名约定)。

### P2 · 注册走 host,不直接订 spine
Exporter 不订 `EventSpine.subscribe(...)`(那是 ADR-0063 的旧 SSE 模式);走 `ProjectionHost.register(def)` —— 拿到 reducer 视图而非原始事件流(与 dsh consumer group 同构)。

### P3 · 选配 Profile YAML,默认不注册
web-standard 默认不含 Exporter(避免无凭证 SDK 启动报错);`oii-debug` / `genai-traced` / `coding-agent` / `langfuse-eval` 等 profile 按需加载。

### P4 · 频度与背压解耦
metrics 高频(每个 step 写一行)/ OTel 异步 span / Langfuse 异步 batch —— 由 Exporter 自身批写窗口控,与 host flush_all 解耦;ADR-0170 `best_effort` 分档语义与此同构。

## 决策

### D1 · Exporter 实现层模板

```python
# plugins/observability/exporters/metrics/_impl.py
class MetricsProjectionDefinition(LoopProjectionDefinition):
    """metrics 出口:按 step / phase 计数;高频事件流。

    key: "metrics"
    state: 计数 dict;按 (incarnation, phase, kind) index
    apply: 累加 metric tokens_count / tool_call_count / latency
    view: 序列化 prometheus 文本(or OpenMetrics JSON)
    """
    key = "metrics"
    version = 1
    def init(self): return {"counters": {}, "gauges": {}}
    def apply(self, state, snapshot, record): ...
    def view(self, state): ...             # 返回 OpenMetrics 输出 buffer
    def restore(self, state): return state  # 默认 seed


# plugins/observability/exporters/otel_trace/_impl.py
class OtelTraceProjectionDefinition(LoopProjectionDefinition):
    """OTel trace 出口:把 loop 事件映射到 OTel span。"""
    key = "otel_trace"
    version = 1
    def init(self): return OTelState(...)        # 内部 SpanBuilder
    def apply(self, state, snapshot, record): ...
    def view(self, state): return state.export() # span list
    def restore(self, state): return state


# plugins/observability/exporters/langfuse_eval/_impl.py
class LangfuseEvalProjectionDefinition(LoopProjectionDefinition):
    """Langfuse LLM-as-judge / 评分 出口(可选)。"""
    key = "langfuse"
    version = 1
    def init(self): return LangfuseState(...)
    def apply(self, state, snapshot, record): ...
    def view(self, state): return state.export_scores()
```

**关键**:每个 Exporter 是一个普通 Python 包,继承 `LoopProjectionDefinition` 契约(ADR-0170 D1);**不是** spine plugin,**不是** cursor 子类,**不是** ADR-0168-final 的"装配宇宙"成员。

### D2 · Profile YAML 选配入口

```yaml
# profiles/oii-debug.yaml(profil-bundle 段)
projection_host:
  initial:
    - key: step_tree
    - key: narrative
    - key: graph
    - key: cost
    - key: live_tail
    - key: otel_trace           # ← Exporter opt-in
    - key: metrics              # ← Exporter opt-in

exporter_config:
  otel_trace:
    endpoint: "http://localhost:4317"
    compression: gzip
    resource_attributes:
      service.name: lca
      service.version: "0.1"
  metrics:
    output_path: traces/runs/$RUN_ID/metrics.json
    prometheus_mode: false
  langfuse:
    api_base: $LANGFUSE_BASE_URL
    secret_key: $LANGFUSE_SECRET_KEY
    public_key: $LANGFUSE_PUBLIC_KEY
```

**关键**:每次 profile 加载,`ObservabilityRuntime.from_profile` 按 `exporter_config` 段构造 Exporter 实例并 register 到 host。**无凭证不崩溃**(Profile YAML 校验阶段提示,运行时按需禁)。

### D3 · 词汇 / 边界契约

| 边界 | 谁负责 | Exporter 知道 | Exporter 不知道 |
|---|---|---|---|
| 状态机语义 | LoopCursor | ❌ | ✅(只收 apply(state, snapshot, record))|
| EventSpine 流 | ProjectionHost + spine | ❌ | ✅(host.drive 屏蔽原始)|
| Persistence 写入 | PersistenceCoordinator | ❌ | ✅(独立 best-effort 路径)|
| Model-visible 5 件套 | ModelVisibleCapture + 文件 | ✅(可读 model_visible/step_NN/*.json)| ❌ |
| Close 时序 | CloseBarrier | ❌ | ✅(host.flush_all() 跟随 L7-4)|

**为什么不订 spine.subscribe**:每个 Exporter 直接订 spine 等于把"consumer lifecycle"嵌进 Exporter,绕开 host 的 flush_all 协调;违反 ADR-0169 §D8 五缝的"spine 仍持 subscribers,host 是消费方"。

### D4 · 频度 / 背压模型

| Exporter | 单批事件数 | 窗口 | 失败行为 |
|---|---|---|---|
| metrics | 1 | 同步 1:1 | 失败 → projection_host.errors["metrics"] = exc |
| OTel trace | 100 | 500ms(可配)| 失败 → OTel SDK 重试 3 次后 dropped_events |
| Langfuse | 50 | 2s(可配)| 失败 → Langfuse SDK 退避 1s 后 dropped_events |

**背压**:host.flush_all 调 Exporter 的 view(state);Exporter 自己 flush 内部分别(SDK responsibility);不带 flush 状态回压到 host(本 ADR 不实现 backpressure,ADR-0172 留 TODO)。

### D5 · SDK / 凭证隔离

每家 Exporter 自己的 SDK / 凭证加载是 Exporter 实例责任。**严禁** Exporter 直接读 `os.environ` —— 凭证通过 Profile `{from_env: ...}` 注入(AGENTS.md §3 / ADR-0117 K7 BOOTSTRAP_NAMES)。

```python
# plugins/observability/exporters/langfuse/_impl.py
def make_definition(config: dict) -> LangfuseEvalProjectionDefinition:
    api_base = config["api_base"]            # 已在 Profile yaml 解析期注入
    secret  = config["secret_key"]
    return LangfuseEvalProjectionDefinition(
        client=LangfuseClient(api_base=api_base, secret=secret, ...),
        batch_size=config.get("batch_size", 50),
    )
```

**(凭证字段不在 events.jsonl 中泄露)** —— host.drive 只传 (state, snapshot, record);Exporter 凭证在 view(state) 时(去往外部 API)被使用,不在 events.jsonl 落盘。

## 决策边界 vs ADR-0169

| 关注点 | ADR-0169 | 本 ADR |
|---|---|---|
| 五缝之一 | "投影缝"(ProjectionHost)| ❌ 不重提 |
| 投影协议 | `ProjectionHost.register(def)` | Exporter 实例作为 def 注册 |
| 选配入口 | — | Profile YAML `projection_host.initial` + `exporter_config` |
| 凭证 | — | Profile `{from_env: ...}` 注入 |
| 频度 / 背压 | — | Exporter 自身批写窗口 + SDK |
| 与 cursor 耦合 | cursor 不持有 Exporter | 同 |

## 兼容性

- ADR-0063 I6(third-party event plugins)不变;第三方 Exporter 也走 plugin manifest(ADR-0061)。
- ADR-0088 Profile-selected Runtime 扩为包含 Exporter 选配。
- 凭证加载链 AGENTS.md §3 + ADR-0117 K7 BOOTSTRAP_NAMES 不变。
- 旧 `bundles/spine-default.yaml` 含的 OTel / metrics plugin:迁移到本 ADR 的 `projection_host.initial` 选配;**不**作为 cursor 子 plugin。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| `bundles/spine-default.yaml` 中 `otel_trace` / `metrics` plugin 直接挂在 spine | 删除(转 host.initial)| grep = 0 |
| Exporter `client = Langfuse(api_key=os.environ['LANGFUSE_API_KEY'])` 直接读 env | 删除 | grep = 0 in `plugins/observability/exporters/` |
| `_legacy_exporter_state` 字段(若实施期临时)| AST scan = 0 | `red_audit_log.jsonl` 必 0 |

## 验证

```bash
# 默认 web-standard 无 Exporter
uv run pytest tests/profiles/test_web_standard_no_exporter.py -v

# oii-debug 加载 otel_trace + metrics
uv run pytest tests/profiles/test_oii_debug_exporters.py -v

# Langfuse 无凭证不崩溃
uv run pytest tests/exporters/test_langfuse_credential_failure.py -v

# 频度 / 背压
uv run pytest tests/exporters/test_exporter_backpressure.py -v

# 应用不污染 cursor
uv run python scripts/check_loop_cursor_no_deriver_hold.py
# 同时检查 cursor 不含 otel / metrics / langfuse
```

## 后果

### 正面

1. **Exporter 边界清晰**:与五缝架构正交,不污染 cursor。
2. **Profile YAML 选配**:web-standard 默认无,debug / eval profile 按需加载。
3. **凭证走 Profile YAML**:不读 env,不在 events.jsonl 泄露。
4. **背压与频度解耦**:每家 Exporter 自己负责批写窗口。
5. **第三方友好**:任何 Exporter 都只需继承 `LoopProjectionDefinition`,无需改动 cursor / host。

### 负面

1. **第三方 Exporter 需先实现 LoopProjectionDefinition 接口**:但接口有 5 个方法(init/apply/view/restore)+ 6 个属性,门槛低。
2. **Profile YAML 字段扩张**:但都是 `exporter_config` 段,与 `projection_host.initial` 互不污染。
3. **频度 / 背压目前由 Exporter 自我管理**:不实现统一回压(本 ADR 留 TODO)。

## 引用

- ADR-0044 Code Sandbox Adapters(adapter 同源)
- ADR-0061 Plugin Manifest(Exporter 走 plugin manifest)
- ADR-0063 Run Trace SSOT
- ADR-0074 Plugin-Everything 裁剪
- ADR-0088 Profile-selected Runtime Factory
- ADR-0117 Process Lifecycle + Env Whitelist(K7 BOOTSTRAP_NAMES)
- ADR-0169 五缝架构 + Profile YAML 选配
- ADR-0170 ProjectionHost 注册入口
- ADR-0171 fork 共享 Host
- ADR-0169 §D11 阶段化实施第 4 阶段
- 实施计划: `docs/plans/2026-09-02-loop-cursor-control/0172-exporters.md`(由 writing-plans 输出)

---

## §附录 · 评审清单对照(山姆 §潜在 #14)

| 评审点 | 本 ADR 落点 |
|---|---|
| metrics/OTel「也算本 ADR」 | ✅ 独立成 ADR;ADR-0169 五缝不包含 |
| 观测厂商集成与状态机 PR 抢车道 | ✅ Exporter 走 `LoopProjectionDefinition`,与 cursor 完全无关 |
| OTel / Langfuse 投影路径 | ✅ D1 实现层模板 + D2 Profile YAML 选配 |
| profile 选不选 | ✅ web-standard 默认无;oii-debug / genai-traced 按需 |
