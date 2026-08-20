# ADR-0063: Run-scoped 详细交互轨迹 — 单一文件 SSOT + 分层分受众

## 状态

Proposed

Amends: [ADR-0037](0037-journal-single-source.md)（journal 是事实流；trace 是 journal 的 DEBUG 副本，不引入并行事实源）、[ADR-0055](0055-run-fact-store.md)（journal 事件词表定义复用）、[ADR-0061](0061-plugin-manifest-resolve-boot.md)（plugin Manifest 是 trace 的 emit 入口之一）、[ADR-0062](0062-plugin-runtime-cleanup.md)（驱动边界；trace 自动捕获 inject 路径）

## 背景

LCA 的可观测栈目前有两类输出：

| 类别 | 文件 / 流 | 用途 | 缺点 |
|---|---|---|---|
| **Journal** | `traces/runs/<run>.journal` | load-bearing 事实流（ADR-0037），消费者：replay / reducer / SSE / OTel | 词表受宪法约束（C6：改闭集必 ADR）；不收录 DEBUG 级 plugin 交互 |
| **structlog stderr** | `_log.debug("hook_triggered", ...)` | 开发者本地 debug | **不进文件**；**不分 run**；**没语义结构** |

结果：开发期想问"插件 X 在 run Y 里调用了什么、传了什么、模型为什么这么想"，只能 grep stderr（不可靠）或拼 journal（粒度不够）。这是一个真实的诊断盲区——例如今天用户问"我怎么知道一条 run 的完整插件链路"，工具链没有正面答案。

**DSH 的精华**（`session.jsonl` + `logger-console` Exporter + 事件折叠原则）值得借鉴：

- `~/deepseek-harness/.agents/notes/implemented/simplification/2026-06-20-collapse-trace-only-session-events.md` 明确：**trace-only 事件要折叠进 load-bearing 事件**——不是把 trace 复制一份塞进 conversation log。
- `~/deepseek-harness/vendor/cordis/src/logger.ts` 把 logger 作为 cordis Context 的**内置服务**，`Message {sn, ts, name, type, level, args, fiber}` 携带 fiber 引用（哪个插件触发的）。
- `~/deepseek-harness/vendor/logger-console/src/shared.ts` 实现一个 Exporter，可插拔。

但 LCA 已经选择了**结构化 journal jsonl**作为单一事实源（比 cordis Logger 的 ring buffer 更适合 replay）。问题是：**journal 不收 DEBUG 级 plugin 交互**——这不是 journal 的缺陷，是设计意图。TRACE 需要一个新出口，但**不能成为新事实源**——它必须是 journal 的投影 + plugin 作者显式 emit 的补充。

## 第一性原理

| # | 不变量 | 含义 |
|---|---|---|
| **T1** | **trace ≠ journal** | trace 是 DEBUG 副本 + plugin 主动 emit 的扩展；journal 继续是单一事实源。trace-only 数据不得进入 journal（C6）。 |
| **T2** | **每 run 一份文件** | `traces/runs/<run>.trace.jsonl` 是 run-scoped 的；append-only；由 cordis `run_scope` 边界驱动创建 / 关闭。 |
| **T3** | **三类正交标签** | `layer`（认知相位：`perceive`/`think`/`gate`/`act`/`reflect`/`remember`/`plugin`/`infra`）× `domain`（对象类型：`llm`/`tool`/`memory`/`skill`/`hook`/`capability`/`team`/`transport`）× `audience`（`internal`/`end_user`/`restricted`）。三轴独立，每行都标。 |
| **T4** | **`traces/last.log` 是最新 run 的入口** | 软链到当前活跃 run 的 `.trace.jsonl`；`finalize` 时重链。开发期 `tail -f traces/last.log` 永远是"正在跑的那个 run"。 |
| **T5** | **自动捕获 + 显式 emit 两路并存** | 自动捕获：`ctx.inject` / `setup()` / hook trigger / LLM call（plugin 不动也看得到）。显式 emit：plugin 作者用 `trace_event()` 上下文管理器写 WHY/INPUT/OUTPUT。**默认自动捕获全开；显式 emit 增量信息**。 |
| **T6** | **trace-only 数据不重投 journal** | 自动捕获产生的 trace 行**只入 trace 文件**；如需进 journal，必须显式 `record(JournalEvent)`（journal 词表闭集）。 |
| **T7** | **plugin 主动 emit 是首选 UX** | `trace_event()` context manager / 装饰器是惯用法；自动捕获是兜底。自动捕获可配置关闭（生产环境关掉以省 I/O）。 |

## 决定

### 1. 新增 plugin `lca-observability-trace`

**位置**：`lca/plugins/observability/trace_logger/`（observability 是 L0 seam；trace 是观测扩展，不污染 L1）。

**Manifest**：
```python
@plugin(
    id="lca-observability-trace",
    provides=["trace_logger"],
    requires=["observability"],
    layer="L0",
    effects="writes traces/runs/{run_id}.trace.jsonl + traces/last.log symlink",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config):
    exporter = TraceJsonlExporter(
        path_template=config.get("path", "traces/runs/{run_id}.trace.jsonl"),
        level=config.get("level", "debug"),
        audiences=set(config.get("audiences", ["internal", "end_user", "restricted"])),
        write_last_log=config.get("write_last_log", True),
    )
    observability = ctx.inject("observability")
    observability.add_trace_exporter(exporter)
    ctx.provide("trace_logger", exporter)
```

**Bundle**：`bundles/observability-dev.yaml`（opt-in；`web-app.yaml` 不带——保持生产日志清爽）。

### 2. Schema（每行 trace）

```json
{
  "ts": "2026-08-20T12:00:00.123Z",
  "mono": 42,
  "run_id": "run_xxx",
  "trace_id": "trace_xxx",
  "step": 2,
  "layer": "think",
  "domain": "llm",
  "level": "debug",
  "audience": "internal",
  "plugin": "lca-loop-cognitive",
  "actor": "助手",
  "title": "ask LLM to decide next action",
  "what": "complete()",
  "why": "step=2 status=running need=action_decision",
  "input": {"prompt_preview": "你好吗...", "model": "qwen3.7-plus"},
  "output": {"text_preview": "好", "tokens_in": 127, "tokens_out": 34, "duration_ms": 1500},
  "parents": [41],
  "tags": ["slow"],
  "error": null
}
```

字段定义：
- `ts` — ISO8601 UTC；`mono` — monotonic seq within trace（与 journal 的 `seq` 解耦）
- `step` — 来自 `state.step`（认知循环计数）；无 `state` 时为 `null`
- `layer` — `lca/contracts/atoms/enums.py` 新增 `TraceLayer` 枚举（见 §4）
- `domain` — `lca/contracts/atoms/enums.py` 新增 `TraceDomain` 枚举
- `audience` — 复用 journal 的 `JournalSchemaMeta.audience` 字符串域（`internal`/`end_user`/`restricted`）
- `plugin` — emit 者的 plugin id；hook 触发时 = 触发 hook 的 plugin
- `actor` — agent role（来自 state.agent_role）或 `system` / `user`
- `title` — 人类一句话摘要（自动从 `what` + `input` 派生，或 plugin 显式提供）
- `what` — 方法名 / 动作名
- `why` — 决策依据（plugin 显式提供或自动从 kwargs 提取）
- `input` / `output` — KV map；敏感字段由 `policy=redact` 自动 mask（沿用 `AttributePolicy`）
- `parents` — `mono` 数组，构成因果链（≠ span tree；只是逆查索引）
- `tags` — 自由字符串（`slow` / `retry` / `cached` 等）
- `error` — 异常时填 `{type, message, stack_head}`；否则 `null`

### 3. Plugin 作者 UX

**一行 helper（最常用）**：
```python
from lca.plugins.observability.trace_logger import trace_log

trace_log(ctx, layer="plugin", domain="capability",
          title=f"resolve {capability}", what="inject",
          input_preview={"requested_by": plugin_id},
          output_preview={"provider": providing_plugin})
```

**上下文管理器（带输入输出 + 自动计时 + 异常捕获）**：
```python
from lca.plugins.observability.trace_logger import trace_event

async def complete(prompt, model, ctx):
    with trace_event(
        ctx, layer="think", domain="llm",
        title=f"call {model}", what="complete",
        actor=role,
        input={"prompt": prompt, "model": model},
        why=f"step={state.step} need LLM response",
    ) as t:
        result = await _do_complete(prompt, model)
        t.set_output(text=result.text, tokens_in=result.tokens_in,
                     tokens_out=result.tokens_out, duration_ms=elapsed)
        return result
# ↑ 自动捕获：异常 → level=error, output.error={type,message,stack_head}
# ↑ 自动计时：duration_ms 由上下文管理器在 exit 时填
```

**装饰器（hook / 工具调用零侵入）**：
```python
@traced(layer="act", domain="tool",
        title_fn=lambda args, kwargs: f"exec {args.get('tool_name')}")
async def execute_tool(ctx, *args, **kwargs):
    return await ...
```

### 4. 三轴分类（taxonomy）

**Layer**（认知相位 + 基建）：

| 值 | 含义 | 触发者 |
|---|---|---|
| `perceive` | 感知阶段 | `HookEvent.PRE_PERCEIVE` / `POST_PERCEIVE` |
| `think` | 思考阶段 | `HookEvent.PRE_THINK` / `POST_THINK` |
| `gate` | 决策门 | `HookEvent.PRE_GATE` / `POST_GATE` |
| `act` | 行动阶段 | `HookEvent.PRE_ACT` / `POST_ACT` |
| `reflect` | 反思阶段 | `HookEvent.PRE_REFLECT` / `POST_REFLECT` |
| `remember` | 记忆阶段 | memory write/read 边界 |
| `plugin` | plugin 生命周期 | `setup()` / `dispose()` / `inject()` |
| `infra` | 基建（IO/transport/observability） | transport / file_store / observability seam 边界 |

**Domain**（对象类型）：

| 值 | 含义 | 典型 plugin |
|---|---|---|
| `llm` | LLM 调用 | `lca-loop-cognitive` / `llm_resolver` |
| `tool` | 工具执行 | `body.safe_executor` |
| `memory` | 记忆读写 | `memory.simple` |
| `skill` | 技能调用 | `skills.disk` |
| `hook` | lifecycle hook | `hook_registry.simple` |
| `capability` | capability 注入 | `AuditedPluginContext.inject` |
| `team` | 委派 / 协作 | `strategies.*` |
| `transport` | transport 边界 | `a2a` / `mcp` / `internal` |

**Audience**（沿用 journal 现有字符串域，无新枚举）：

| 值 | 进 trace 文件 | 进 SSE live | UI 可见 |
|---|---|---|---|
| `internal` | ✅ | ❌ | ❌ |
| `end_user` | ✅ | ✅ | ✅ |
| `restricted` | ✅（redact） | ❌ | ❌ |

### 5. 自动捕获（plugin 作者不动也看得到）

四个边界自动 emit `trace_event`：

1. **`AuditedPluginContext.inject`** — 每次 `ctx.inject("xxx")` → `layer=plugin domain=capability what=inject`；记录 `requested_by`（`definition.id`）和 `provider`（resolved plugin）
2. **Plugin `setup()`** — boot 期；`layer=plugin what=setup input={provides,requires,config_keys}`；boot 完成后**不进 trace**（避免 boot 噪音；走 boot_report 即可）
3. **Hook trigger** — `layer=<phase> domain=hook what=trigger`；复用现有 `default_logging_hook`，**不替代而是并联**（两者都收到同 hook 事件；hook 本身仍走 journal 路径，trace 是副本）
4. **LLM call** — `lca/layer0_infra/llm/openai_compat/complete()` 包 trace_event（Phase 3 实现）

→ 即便 plugin 作者零改造，trace 文件也已包含完整的 inject 链 + hook 流 + LLM 细节。

### 6. `traces/last.log` 机制

- 每个 run `finalize` 时（`gateway/runs/execute.py:finalize`）：用 `os.replace()` 重链 `traces/last.log` → `traces/runs/<run_id>.trace.jsonl`；同时 `traces/last.journal` → `traces/runs/<run_id>.journal`
- 开发期 `tail -f traces/last.log` 永远是当前活跃 run
- 多 run 并发时（理论上有），`last.log` 指向 `mtime` 最新的；这是约定，不是合同

### 7. 命令：`lca-ops debug trace`

```bash
./scripts/lca-ops debug trace <run_id>                # jsonl → 着色时间线
./scripts/lca-ops debug trace <run_id> --filter llm   # 只看 llm 域
./scripts/lca-ops debug trace <run_id> --layer think  # 只看 think 相位
./scripts/lca-ops debug trace <run_id> --audience end_user  # 只看会推到 UI 的
./scripts/lca-ops debug trace <run_id> --plugin lca-loop-cognitive  # 按 plugin 过滤
./scripts/lca-ops debug trace <run_id> --since 12:00:00  # 时间过滤
./scripts/lca-ops debug trace <run_id> --follow  # 等同 tail -f（运行中实时跟）
```

**输出格式**（仿 DSH `logger-console`）：
```
12:00:00.123 [DEBUG] think  llm    lca-loop-cognitive  助手  ask LLM to decide next action
   why: step=2 status=running need=action_decision
   ── input  ── prompt_preview="你好吗..." model=qwen3.7-plus
   ── output ── text_preview="好" tokens_in=127 tokens_out=34 duration_ms=1500ms
12:00:01.456 [DEBUG] think  llm    lca-loop-cognitive  助手  ask LLM to write response
   why: step=2 decision=respond conf=0.95
   ── input  ── prompt_preview="你现在感觉如何..." tokens_in=89
   ── output ── text_preview="作为 AI..." tokens_out=156 duration_ms=2100ms
```

### 8. 自动生成的 `traces/runs/<run>.summary.md`

每个 run finalize 时，从 `.trace.jsonl` 生成一份 markdown 时间线（人类阅读版）：
```markdown
# Run run_xxx — 12:00:00 ~ 12:00:45 (45s)

## Steps
- step 0 [12:00:00] 助手 think.llm  ask LLM to decide → respond (1500ms)
- step 1 [12:00:02] 助手 think.llm  ask LLM to write → text (2100ms)
- step 2 [12:00:30] 助手 act.tool   exec sandbox_execute (12000ms) ⚠ slow

## Plugins touched (alphabetical)
- body.safe_executor (×3)  llm.openai_compat (×4)  memory.simple (×2)

## Errors / warnings
- (none)
```

实现：`lca/plugins/observability/trace_logger/formatter.py::to_markdown(events: list[TraceEvent]) -> str`。

### 9. 性能预算

| 操作 | 开销 |
|---|---|
| 一次 `trace_event()` exit | ~50µs（json.dumps + 文件 append） |
| 自动捕获 hook trigger | ~30µs × 每次 hook（每次循环 8-10 个 hook） |
| 自动捕获 `ctx.inject` | ~30µs × 每次 inject（每次 plugin 启动 5-10 次） |
| 单 run 总开销（典型：50 步循环） | ~10ms（占 run 耗时的 <0.1%） |

生产环境建议 `level: info`（关掉 DEBUG），开销降至 ~1ms/run。**生产默认关闭 DEBUG**（`observability-dev.yaml` 才打开）。

## 影响

### Plugin 作者

- 必须**用** `trace_event()` / `trace_log()`（推荐但非强制）；自动捕获兜底
- 必须**不**用 `print()` / 裸 `structlog` 写 plugin 业务事件；改用 `trace_event()` 或 `record(JournalEvent)`
- 文档更新：`docs/AGENTS.md` 加一条"trace 是 plugin 主动 emit 的扩展，journal 是事实流"；`roles/` 加 helper 模板

### L0 / L1 边界

- `lca/contracts/atoms/enums.py` 新增 `TraceLayer` / `TraceDomain` 枚举（与 `HookEvent` / `JournalSchemaMeta` 解耦）
- `lca/layer0_infra/observability/seam.py`（假设存在）新增 `add_trace_exporter()` API
- 不动 `JournalSchemaMeta`（沿用 audience 字符串）

### Gateway / Run 生命周期

- `gateway/runs/execute.py:finalize` 加一段：trace exporter 关闭 + 软链重指向
- `gateway/runs/live.py` 不变（trace 不进 SSE；journal 进 SSE）

### 命令行

- `lca-ops debug trace <sub>` 命令新增（仿 `debug run`）

## 替代方案

### A. 不做新 plugin，复用 `default_logging_hook` 写文件

- 优点：改动小，1 文件
- 缺点：缺乏 schema；没有 `domain`/`audience` 分层；自动捕获覆盖不全（只 hook，没有 inject/LLM）；无 `last.log` 机制；违反 T1/T3/T4 — **否决**

### B. 改 cordis Logger（vendored）加 trace Exporter

- 优点：复用 cordis 的 ring buffer + fiber tracking
- 缺点：cordis Logger 是 stderr 输出模型，不分 run 不分文件；要重写大段 — **否决**

### C. 用 OpenTelemetry SDK 全套

- 优点：工业标准；Jaeger/Tempo 可视化
- 缺点：OTel 是 span tree 模型，不是一行一事件的 jsonl；LCA 已选 journal jsonl 作为 SSOT（ADR-0037），OTel 是**投影**而非**事实源**；为 trace 引入 OTel 是新事实源 — **否决**（可作为 trace → OTel 的**导出器**，但不是 trace 的存储格式）

### D. 让 plugin 作者**手动**写 trace（不开自动捕获）

- 优点：trace 行只来自显式 emit，零噪音
- 缺点：违反 T7；user-facing UX 太重（每个 LLM call 都要手动包）— **否决**

## 实施分阶段

| 阶段 | 范围 | 状态 |
|---|---|---|
| **Phase 1 — MVP** | `lca/plugins/observability/trace_logger/` 骨架 + `trace_event` helper + journal 镜像 + `last.log` 软链 + `lca-ops debug trace` 命令 + `bundles/observability-dev.yaml` opt-in | Proposed |
| **Phase 2 — 自动捕获** | `AuditedPluginContext.inject` 改写 + `CordisHookRegistry.trigger` 改写（并联现有 `default_logging_hook`）+ plugin `setup()` 自动 emit | Proposed |
| **Phase 3 — LLM 细节** | `lca/layer0_infra/llm/openai_compat/complete()` 包 `trace_event`，自动捕获 prompt/response/tokens/model/latency | Proposed |
| **Phase 4 — 人类可读** | `formatter.py` + `lca-ops debug trace --filter/--layer/--audience/--follow` 全选项 + `summary.md` 自动生成 | Proposed |

每个 Phase 都是独立 PR，独立可回滚。

## 验证标准

1. **自动化测试**：
   - `tests/test_trace_logger.py`：schema、序列化、自动捕获、redaction、helper
   - `tests/test_trace_integration.py`：每个 hook 事件都产生一行 trace
   - `tests/test_lca_ops_debug_trace.py`：CLI 输出格式、过滤选项
2. **手动验证**：
   - 一个 run 完整 trace 文件可读：`cat traces/runs/<run>.trace.jsonl | jq -c '{plugin,layer,domain,what,why}'`
   - `last.log` 软链正确：`ls -la traces/last.log`
   - `lca-ops debug trace <run_id>` 输出着色清晰
3. **回归测试**：现有 `tests/test_run_http.py` 等不受影响（trace 是新增，不改 journal 路径）

## 参考

- DSH session 模型：`~/deepseek-harness/.agents/notes/implemented/simplification/2026-06-20-collapse-trace-only-session-events.md`
- DSH logger：`~/deepseek-harness/vendor/cordis/src/logger.ts`
- DSH console exporter：`~/deepseek-harness/vendor/logger-console/src/shared.ts`
- OpenTelemetry span model：`https://opentelemetry.io/docs/concepts/signals/traces/`
- Langfuse trace schema：`https://langfuse.com/docs/observability/data-model`
- LCA journal 词表：`lca/contracts/models/observability/journal_catalog.py`
- LCA hooks：`lca/layer1_cognitive/hook_registry.py`
- LCA plugin API：`lca/harness/plugin_api.py`

## 关联 ADR

- [ADR-0037](0037-journal-single-source.md) — journal 是事实流；trace 是 DEBUG 副本
- [ADR-0055](0055-run-fact-store.md) — journal 事件词表定义
- [ADR-0061](0061-plugin-manifest-resolve-boot.md) — plugin Manifest 是 trace emit 入口
- [ADR-0062](0062-plugin-runtime-cleanup.md) — driver 边界；inject 路径在此被自动捕获