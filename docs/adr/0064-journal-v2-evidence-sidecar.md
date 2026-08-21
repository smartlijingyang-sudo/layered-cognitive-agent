# ADR-0064: Journal v2 + Evidence Sidecar + Per-Run 自洽目录

## 状态

**Superseded by [ADR-0065](0065-recoverable-evidence-ledger.md) — 2026-08-21**

Amends: [ADR-0037](0037-journal-as-truth.md)（journal-as-truth 三原则的可执行细化）
Amends: [ADR-0063](0063-run-trace-ssot.md)（追加 journal.v2 schema、evidence sidecar、per-run 目录、EventMeta、coding agent 工具包）
Refines: [ADR-0055](0055-run-fact-store.md)（事件分类与持久化落地）
Refines: [ADR-0061](0061-plugin-manifest-resolve-boot.md)（新增 4 个 seam + bundle plugin；不撤回声明式 manifest）

> **核心决策：journal 不再压缩、不再字符串化结构、不再有全局流。每 run 一个目录；大载荷走 evidence sidecar；4 个 seam 把"如何存 / 如何写 / 如何看 / 如何布局"全部可替换。**

## 背景

[ADR-0063](0063-run-trace-ssot.md) 已经确立：单账本、append-only、projector 扇出。但实现暴露三个**结构性问题**，让"事后回溯"这件事做不好：

### 1. Lossy preview 字段违反 C3

`lca/contracts/models/observability/journal.py` 共 11 个 `*_preview` 字段是**截断字符串**——`LlmCallCompleted.prompt_preview` 仅 603 字符，但实际 prompt 平均 6-15 KB。**模型看到的东西没全写进去**：违反 ADR-0037 / ADR-0063 的"model-visible ⟺ logged"。补救是 `lca/layer1_cognitive/body/tool_ui_state.py:226` 在客户端做 "Merge truncated preview + full plugin_state"——但 plugin_state 也不总在。

### 2. 双层序列化：`result_preview` 是字符串里的 JSON

`lca/layer1_cognitive/body/tool_journal_emit.py` 把 `dict` 序列化为 JSON 字符串塞进 `result_preview: str`。下游 `deploy/lobehub/patches/runtime/lcaJournal.ts` 必须 `JSON.parse(result_preview)` 二次解析。**类型撒谎**：字段语义是 dict，类型是 str。

### 3. Per-run 文件不可读、无 viewer

`traces/runs/<id>.jsonl` 是 per-run 真相，但 `lca-ops logs` 只能读全局 `traces/lca_journal.jsonl`。Agent / 新人想看一次 run：要么自己写 jq 脚本，要么靠 doctor 报告——**没有标准入口**。

### 4. Plugin 交互信息无图

`RuntimeObserved(kind=PLUGIN, operation="...")` 已记录"哪个插件做了什么"，但**没有 caller → callee 边**，没有"传了多少字节"信息。多 agent 调试时，无法可视化插件协作图。

### 5. 没有代码 trace

拿到一条异常事件，**无法直接跳到抛它的源码行**。要靠"猜文件 + grep event_type"——debug 核武器缺失。

### 6. Plugin 边界有 `new` 泄漏

`gateway/runs/execute.py:169` 直接 `JsonlJournalProjector(jsonl_path)`、`LiveTail()`。Plugin 体系的核心约束是"一切经 cordis.Context"，但 run-scoped projector 实例化绕过了 seam。`gateway/runs/process_journal.py:14` 在 `RunRegistry.__init__` 里 `ProcessJournal()` 也是同样问题。

## 决定

### 一、journal.v2 schema（破 v1 不回退）

```json
{
  "schema": "journal.v2",
  "seq": 42,
  "ts": 1787282332.94,
  "scope": {
    "trace_id": "trace_e797e0b279c9",
    "run_id": "run_4a0b43ae707c",
    "parent_run_id": null,
    "parent_trace_id": null,
    "delegation_id": null,
    "agent_role": "agt_aVxY6ag9MbMc",
    "step": 0
  },
  "event_type": "LlmCallCompleted",
  "data": {
    "model": "qwen3.7-plus",
    "ok": true,
    "latency_ms": 2416,
    "prompt_tokens": 7388,
    "completion_tokens": 79,
    "prompt_hash": "sha256:...",
    "prompt_source": "builtin:reasoner@2.3.1"
  },
  "meta": {
    "plugin": "lca-llm-resolver",
    "source": "tools/pre-execute",
    "duration_ms": 2416,
    "outcome": "ok",
    "error_code": "",
    "tags": ["high-cost"],
    "file": "lca/layer1_cognitive/body/safe_executor.py",
    "line": 142,
    "function": "execute",
    "info_in_bytes": 30234,
    "info_out_bytes": 144
  },
  "evidence_ref": {
    "prompt": "evidence/llm-0042-prompt.txt",
    "response": "evidence/llm-0042-response.txt"
  }
}
```

**字段硬约束：**
- `data` 内所有字段 typed & complete（不截断、不字符串化结构）
- 大载荷（> 64 KB）走 `evidence_ref`；journal 字段保留 metadata（hash、size）+ 路径
- `meta` 由 `record()` facade 在入口自动用 `inspect.stack()` 捕获
- 删 v1 的所有 `*_preview` 字段；`output_truncated: bool` 一并删除（不再需要标记）
- v1 reader **立即删除**（不混读）；老 trace 用 `scripts/migrate_journal_v1_to_v2.py` 升级

### 二、Per-run 自洽目录

```
traces/
├── latest → runs/<最新 run>            ← symlink（Linux/macOS）
├── latest.txt                          ← Windows fallback（写入目标路径）
└── runs/
    └── 20260821-111932_<24hash>/
        ├── manifest.json         ← 机器读：id, status, ts, tokens, tools, error
        ├── summary.md            ← 人读：auto-generated 叙事
        ├── phase_summary.json    ← Agent 快速入口：6 phase 耗时/token/决策
        ├── cost_summary.json     ← 成本归因：per-model USD + total
        ├── journal.jsonl         ← 事件流（append-only，schema v2）
        ├── index/                ← 轻量 JSON 索引
        │   ├── by_session.json
        │   ├── by_turn.json
        │   ├── by_error_code.json
        │   ├── by_tool_name.json
        │   ├── by_plugin.json
        │   └── by_tag.json
        ├── turn_<seq>_trajectory.md      ← 时间线 + 决策 + 瓶颈
        ├── turn_<seq>_decision_tree.md   ← 决策路径
        ├── turn_<seq>_causal_chain.json  ← 结构化因果
        └── evidence/                     ← 大载荷 sidecar
            ├── llm-0042-prompt.txt
            ├── llm-0042-response.txt
            └── tool-0007-result.json
```

**目录命名约束：**
- `<本地时间戳>_<24 字符全哈希>`：本地时间（`datetime.now()`，无 tz 后缀、无英文）
- 时间戳格式 `YYYYMMDD-HHmmss`（纯数字 + 连字符）
- 24 字符哈希防生日悖论碰撞
- 不写 `run_` 前缀（`runs/` 下全是 run，加前缀冗余）

**`traces/latest` 双层 fallback：**
- Linux/macOS：symlink（`tmp_symlink + rename` 原子更新）
- Windows：写 `latest.txt` 写目标路径字符串
- 启动探测 OS 自动选择；损坏则重建

### 三、新增 4 个事件类型（仅 4 个，封闭）

| 事件 | 平面 | 何时 |
|---|---|---|
| `RunOpened` | Structural | 第一次 journal event 前 |
| `RunClosed` | Structural | 最后一次 event 后（RunFinalizer 触发） |
| `TurnOpened` / `TurnClosed` | Structural | 用户消息进 / Agent 最终回复出 |
| `StepOpened` | Structural | `_loop.step()` 入口 |

**不发明新事件承担 plugin/code/permission/bottleneck 解释**——全部走 `RuntimeObserved(kind=..., operation="...")` 的稳定 operation 命名（ADR-0063 PR-5 已规范）。

### 四、EventMeta 信封（DSH 风格）

`StampedEvent` 加 `meta: EventMeta` 字段（frozen dataclass）：

```python
@dataclass(frozen=True)
class EventMeta:
    plugin: str = ""           # 产生事件的插件 id
    source: str = ""           # 更细来源
    duration_ms: int | None = None
    outcome: str = "ok"        # "ok" | "error" | "cancelled" | "retry"
    error_code: str = ""       # 封闭 ErrorCode 枚举
    error_message: str = ""
    retryable: bool = False
    tags: tuple[str, ...] = ()
    # 代码 trace（自动捕获）
    file: str = ""
    line: int = 0
    function: str = ""
    call_stack: tuple[str, ...] = ()  # 深度 ≤ 5
    # 信息量
    info_in_bytes: int = 0
    info_out_bytes: int = 0
```

**自动捕获：** `record_runtime` / `record` facade 入口用 `inspect.stack()` 填 `file/line/function`（性能成本 5-15μs/次，可接受）。

**plugin 交互：** `RuntimeObserved` 加 `target_plugin: str = ""` 字段。`TraceInspector.plugin_interaction_graph()` 用 `parent_seq` 走边，输出 Mermaid（节点=plugin_id，边标签=info 类型/字节量）。

### 五、4 个 seam（cordis 扩展点）

| seam 名 | 用途 | 默认实现 |
|---|---|---|
| `evidence_store` | 大载荷 sidecar 存储 | `lca-evidence-store-filesystem` |
| `run_layout` | run 目录布局计算 | `lca-run-layout-filesystem` |
| `run_summary_writer` | run close 时写 manifest + summary.md | `lca-run-summary-writer-markdown` |
| `run_viewer` | per-run 查看器 | `lca-run-viewer-terminal` |

**新增 3 个 seam 配套（factory 化 `new`）：**

| seam 名 | 用途 |
|---|---|
| `journal_projector_factory` | 返回 `JsonlJournalProjector(jsonl_path)` |
| `live_tail_factory` | 返回 `LiveTail()` |
| `process_journal` | 返回 `ProcessJournal()`（全局共享） |

**所有 `new` 在 gateway/runs/ 路径清零**——除 dataclass / pydantic / Exception 外，零直接实例化。

### 六、RunFinalizer + Coding Agent Tools（1 个订阅器 + 1 个 bundle）

**`lca-run-finalizer`（Tier-3）：** 单一订阅器
- 订阅 `TurnClosed` → 写 `turn_<seq>_trajectory.md` + `decision_tree.md` + `causal_chain.json`
- 订阅 `RunClosed` → 写 `manifest.json` + `summary.md` + `phase_summary.json` + `cost_summary.json` + `index/by_*.json`
- `ctx.dispose()` 时 flush pending writes

**`lca-coding-agent-tools`（BUNDLE）：** 1 个 plugin 提供 7 个 Coding Agent 工具
- `trace_inspector`：用 `index/by_*.json` 快速过滤
- `failure_explainer`：失败路径投影 + 因果链 walk
- `optimization_finder`：按延迟/token/重试排序
- `plugin_graph_renderer`：Mermaid 插件交互图
- `minimal_reproduction`：导出最小复现包
- `diff_context`：对比 step 前后 prompt/context
- `run_diff`：对比两次 run 同 step 差异（含 prompt_hash）

**Capability 显式：** bundle 的 `provides` 列 7 个 capability；Coding Agent profile `requires` 申请；ADR-0061 DAG 自动校验（C5 满足）。

### 七、成本归因（Cost Attribution）

```python
# lca/contracts/observability/cost.py
@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_per_1k: float  # USD
    output_per_1k: float

class CostCalculatorProtocol(Protocol):
    def register(self, pricing: ModelPricing) -> None: ...
    def compute(self, model, prompt_tokens, completion_tokens) -> float: ...
```

**新增 plugin：** `lca-cost-calculator`（默认定价表：DeepSeek / OpenAI / Anthropic / Qwen 等）；`lca-cost-projector`（订阅 journal 累加 cost）。**输出：** `cost_summary.json.cost_by_model` + 新 CLI `lca-ops cost <run_id> [--by model|phase|tool]`。

### 八、Prompt 版本追踪

`LlmCallCompleted` 加 `prompt_hash: str`（sha256）+ `prompt_source: str`（如 `builtin:reasoner@2.3.1`）。**核心用途：** A/B 测试时 `lca-ops diff-runs <a> <b> --step N` 直接对比 prompt_hash 是否变了。

### 九、Agent 定位问题四阶段（核心）

写入 `docs/observability/agent-debug-cookbook.md`，成为 Coding Agent 调试标准流程：

```
Stage 1: cat traces/runs/<id>/phase_summary.json        ← 30s 看耗时分布
Stage 2: 读 bottlenecks 字段                            ← top-N 慢在哪
Stage 3: lca-ops trace <id> --format mermaid           ← 决策 + 时间线 + 代码
Stage 4: lca-ops explain <id> / lca-ops graph <id>      ← 失败路径 + 插件交互
```

**错误码字典：** LLM/TOOL/GATE/LOOP/PLUGIN/MEMORY/SANDBOX/NETWORK/AUTH/USER 10 大类 ~30 个稳定码（C6 闭集）。`lca/contracts/observability/error_codes.py` 枚举。**`lca-ops diagnose <alias>` 给出修复建议**（model_not_seen / loop_stuck / memory_poisoned / approval_rejected 起步）。

### 十、文档 + CI

**新增 8 个 doc：** `docs/observability/{README,architecture-overview,journal-v2-schema,evidence-sidecar-spec,run-layout,plugin-interaction-graph,code-trace,agent-debug-cookbook,cli-reference}.md`

**新增 7 个 check 脚本：** `check_no_preview_fields` / `check_no_double_encoding` / `check_plugin_capability` / `check_run_naming` / `check_journal_v2_compat` / `check_evidence_atomic` / `check_plugin_setup_signature`

**新增 11 个测试套：** evidence 原子写 / run 命名 / v2 roundtrip / latest pointer / run_finalizer snapshot / coding_agent_tools / plugin_interaction_graph / code_trace / run_diff / token_breakdown / diagnostics

## 后果

### 正面

1. **完整：** 模型所见即日志所记（journal 不再截断，evidence sidecar 装完整载荷）。
2. **结构：** 字段 typed，evidence sidecar 是 typed 文件，不再字符串化 dict。
3. **自洽：** 每个 run 目录独立可读，跨进程 / 跨 OS 无依赖。
4. **插件化：** 一切经 cordis.Context；4 个 seam + bundle + factory 模式；零 `new` 在 gateway 层泄漏。
5. **Agent 友好：** 4 阶段诊断流程 + 错误码字典 + 轻量索引 + plugin_interaction_graph + code_trace；Coding Agent 不必扫描 10MB JSONL。
6. **可维护：** 23 个新模块每行一句话职责；新人有 `architecture-overview.md` 5 分钟入门。
7. **成本可见：** 每个 run 自动算出 per-model USD，Agent 可直接做优化决策。
8. **A/B 测试：** prompt_hash 让"prompt 变了吗"变成可验证的事实。

### 负面

1. **删 lossy 字段破坏外部消费者：** lobehub UI / Langfuse / OTel exporter 读 preview 字段。**对策：** PR-7 前 `grep -rn "_preview" lca deploy/` 列清单，逐个改；同时迁移 lobehub `lcaJournal.ts` 不再做 `JSON.parse(result_preview)`。
2. **删 v1 reader 立即破坏老 trace：** **对策：** PR-7 配套 `scripts/migrate_journal_v1_to_v2.py`；备份原文件为 `<id>.v1.jsonl`。
3. **`traces/latest` 跨平台 fallback 引入双路径：** **对策：** `LatestRunPointerProtocol` 抽象 OS 探测；`lca-ops logs latest` 用户无感。
4. **新增 7 个 CI check + 11 测试：** **对策：** 增量加，不一次性；每 PR 必跑。
5. **journal.write capability 未做：** 任何 plugin 可 emit。**已知妥协**——v3 引入 `journal.write` capability。

### 中性

- v1 老 trace 仍能解析直到 PR-7；migration 脚本兜底。
- OTel exporter 仍可工作（v2 字段语义不变），但要适配 EventMeta。
- 7 个 L2 工具聚合成 1 个 bundle plugin：装配简单但失去每个工具独立挂载的灵活性（**收益 > 成本**）。
- 文档预算新增条目（`agent-debug-cookbook.md` 5000 字等）；`scripts/doc_budgets.json` 同步更新。

### 未在本 PR 范围（明确承诺）

| 未来章节 | 触发 |
|---|---|
| 评估 / Scorer hooks | 单独 PR；接入 Langfuse scorer 模式 |
| 生产监控 / 健康检查 | 单独 PR；需要 metrics 通道 |
| 告警 / 触发器 | 单独 PR；需要 alertmanager 集成 |
| W3C Trace Context | 单独 PR；多进程/跨服务场景出现时 |
| 高吞吐采样 | 单独 PR；token 流超阈值时 |
| `journal.write` capability | v3 引入；当前任何 plugin 可 emit（已知妥协） |

## PR 序列（每 PR 独立可合）

| PR | 标题 | 内容 |
|---|---|---|
| PR-1 | ADR-0064（本文档） | 仅文档 |
| PR-2 | EvidenceStore + RunLayout + LatestPointer 插件 | 3 个 seam + 3 个 Tier-3 |
| PR-3 | Journal v2 schema + EventMeta + RunOpened/Closed/TurnOpened/Closed/StepOpened + prompt_hash + OTel 映射 | journal.py 改动；v1 兼容读 |
| PR-4 | JsonlProjector 走 plugin + factory seam 清零 new + `lca-llm-call-journal-v2` + `lca-tool-journal-v2` 替换直接写入 | gateway/runs/ 改造 |
| PR-5 | RunFinalizer + RunSummaryWriter + CostCalculator + CostProjector + index writer | 1 个订阅器替代原 4 projector |
| PR-6 | Viewer + Coding Agent Tools bundle + 7 个 CLI 子命令 + diagnose | viewer 移到 layer0；6 CLI 子命令 |
| PR-7 | 清理垃圾 + 删 v1 reader + 删 lossy 字段 + migration 脚本 | 配套 `scripts/migrate_journal_v1_to_v2.py` |
| PR-8 | 验证 + 文档收口 | 全量 pytest / mypy / ruff；AGENTS.md 更新 |

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留 `*_preview` 字段，只加 truncated 标记 | 仍是 lossy；与"信息要全面"原则冲突 |
| Evidence sidecar 用数据库 / 对象存储 | filesystem 是最小依赖；s3/zip 是未来 seam 实现 |
| journal schema v3 一步到位 | 破坏性太大；v2 已满足当前需求，v3 留给未来 |
| 不做 plugin_interaction_graph，靠 OTel exporter | OTel 是外部投影；内部 journal 必须先有一等数据 |
| Coding Agent 工具继续分散 6 个 plugin | 装配复杂；bundle 让 1 个 setup 提供 7 服务更优 |
| 引入 `journal.write` capability 在本次 PR | 改动面过大；v3 单独 PR 引入更安全 |

## 相关 ADR

- Keeps: ADR-0037 (journal-as-truth)、ADR-0063 (run trace ssot)、ADR-0055 (run fact store)、ADR-0061 (plugin manifest)
- Amends: ADR-0037 (原则不变，新增可执行细化)；ADR-0063 (追加 schema v2 + seam)
- Future: ADR-v3 (journal.write capability)；ADR-v3 (W3C Trace Context)
