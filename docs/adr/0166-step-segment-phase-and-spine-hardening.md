# ADR-0166: Step / Segment / Phase 三层计数与 Spine 硬化

- 状态: Accepted
- 日期: 2026-09-02
- 作者: coding-agent
- 修订: ADR-0164（纠正 step 边界的实现漂移；保留 step-tree 主存储）
- 相关: ADR-0164, ADR-0165.1, ADR-0159, ADR-0065；对照 deepseek-harness `docs/architecture.zh.md`（一步 = 一次模型请求 + 其工具）
- 触发样本: `run_bb1b9570ef94`（当前错误计为 8 phase-steps；正确应为 steps=3 / segments=5 / phases=8）

## 一句话

**step** 对齐 deepseek-harness（一次 LLM 请求 + 它触发的工具）；**segment** 计数 think|act（含思考）；**phase** 落盘闭集相位（含 perceive）。流式 `reasoning_delta` / `step_text_delta` 必须 coalesce 后落盘，禁止把每个 delta 当成独立 span 污染 narrative。同步硬化上次 spine 复盘暴露的观测缺陷。

## 背景

### 业界与 DSH 怎么定义 step

| 来源 | 单位 | 含义 |
|---|---|---|
| **deepseek-harness** | **step** | 「一次模型请求加上它调用的工具」；**turn** = 领取输入到不再欠工作 |
| OpenAI Assistants | run_step | `message_creation` / `tool_calls` 分型，粒度更细 |
| OpenAI Agents SDK | turn | 一次模型调用的结果分支（final / tools / handoff） |
| LangGraph | node / superstep | 图节点执行；与「故事步」不对齐 |
| AutoGen | message turn | 对话轮次 |

对 `run_bb1b9570ef94`（3 次 LLM + 2 次 `executeCode` + 3 次 perceive）：

| 计数 | 值 | 规则 |
|---|---:|---|
| **steps** | **3** | DSH：每次 LLM + 同一步内工具 |
| **segments** | **5** | 仅 `think` \| `act`（perceive 不计） |
| **phases** | **8** | 闭集相位含 perceive：P→T→A→P→T→A→P→T |

用户要求 **3 与 5 同时可见且命名可区分**；后续补充 **phase 也要显式落盘**（不只派生数字）。

### ADR-0164 的漂移

ADR-0164 一句话写的是：

> 一个 step = 一个认知闭环（上下文 → 思考 → 工具 → 结果 → 反思）

这与 DSH 一致。但实现（`step_emitter.bridge_perceive_*` / `bridge_think_*` / `bridge_act_*`）把 **每个相位** 开成独立 `JournalStep`，导致：

1. `total_steps=8`，叙事表被 perceive 噪音拉长；
2. `thinking.tool_call` 与独立 `act` step 双轨，违背「一步内 5 原语」；
3. `bridge_llm_reasoning_delta` 每个 token 一片 `SpanRecord(kind=reasoning_delta)`，narrative「诊断」展开成几十～上百行。

### 同次 spine 复盘暴露的问题（一并纳入）

来自 `traces/runs/run_bb1b9570ef94/events.jsonl` + CLI：

1. **CLI 读错路径**：`explain` / `trace` / `cost` 仍找 `journal.jsonl`，对 v3 `journal.json` 直接失败。
2. **`body.tool.execute` 双层 start/end**：decision 包装（`dec_*`）与真实 invocation（`toolu_*`）各一对，易被读成「执行了两次」。
3. **`phase_graph.node.end` 无对应 `.start`**：无法做 start/end 配对健康检查。
4. **sequence 重复 / transport 交织**：`transport.route.*` 与 run 内 seq 冲突，route.enter 时间甚至晚于 `kernel.run.start`。
5. **`exception.finally`（diagnostic）**：`boundary=terminal_driver` 在成功 stop 前出现，像异常。
6. **全局 `.lca/spine/events.jsonl` 为空**：live 事件只在 `traces/runs/<id>/events.jsonl`，全局 sink 误导排障。

## 决策

### D1. 三层词汇（强制）

| 词 | 定义 | 计入 | 本次样本 |
|---|---|---|---:|
| **step** | 一次成功进入的模型请求 + 该请求直接触发的工具调用/结果（可 0..N 工具；并行工具同属一步） | `JournalDocument.steps[]` / `totals.steps` | 3 |
| **segment** | step 内（或跨叙事视图）的 `think` 或 `act` 段落；**包含思考**，故不叫 action | `step.segments[]` / `totals.segments` | 5 |
| **phase** | 认知闭集相位实例：`perceive` \| `think` \| `act` \| `reflect` \| `remember` \| `stop`（与 runtime 闭集对齐） | `JournalDocument.phases[]` / `totals.phases` | 8 |

不变量：

- `totals.steps == len(steps)`
- `totals.segments == sum(len(s.segments) for s in steps) == len([p for p in phases if p.kind in ("think","act")])`
- `totals.phases == len(phases)`
- **perceive 不创建 step，不创建 segment**；写入当前（或下一个即将打开的）step 的 `context_before`，并追加一条 `phases[]` 记录。
- 默认对外叙事与 `journal steps` 表以 **step** 为主列；`--segments` / `--phases` 开关展开细层。

### D2. 存储形状（`lca.journal/3.1`）

在 ADR-0164 的 `JournalDocument` / `JournalStep` 上增量（向后兼容读旧文档：缺字段视为「phase-as-step 旧语义」，migrator 可升级）：

```text
JournalDocument
  schema: "lca.journal/3.1"
  steps: JournalStep[]          # DSH 步
  phases: PhaseRecord[]         # 显式落盘
  totals: { steps, segments, phases }
  ...

JournalStep
  step_id / step_index          # 1..N，仅 step 层
  segments: SegmentRecord[]     # think | act，有序
  context_before / thinking / tool_calls[] / tool_results[] / reflect
  spans: SpanRecord[]           # 仅非流式诊断；见 D3
  ...

SegmentRecord
  segment_id / kind: "think" | "act"
  phase_ref?: phase_id          # 指回 phases[]
  started_at / ended_at / outcome

PhaseRecord
  phase_id / kind: StepPhase
  step_id?: str | null          # perceive 可在 step 打开前暂 null，close 时回填
  segment_id?: str | null
  entered_at / exited_at / summary? / outcome
```

`tool_call` 单数字段升级为 **`tool_calls` / `tool_results` 列表**（一步多工具）；单工具 run 长度为 1。旧单字段读路径保留一个版本。

### D3. 流式 delta 合并（强制）

- **运行时**：`bridge_llm_reasoning_delta` / `bridge_llm_step_text_delta` 写入 **coalescer**（按 step + channel 追加 buffer），**禁止**每 delta `record_span`。
- **落盘**：`close` think segment / step 时把 buffer flush 进 `thinking.reasoning`（及 answer/decision 文本字段）；可选一条汇总 span：

```text
SpanRecord(kind="stream_stats", summary={
  reasoning_chars, reasoning_chunks,
  text_channels: { decision: {chars, chunks}, answer: {...} }
})
```

- **SSE live**：仍可发细粒度 progress 事件（ADR-0157）；那是投影面，不是 journal 真值。
- **narrative**：默认不展开 `reasoning_delta`；`stream_stats` 一行摘要；`--verbose-spans` 才展开非 delta spans。

### D4. Emitter 切步规则（取代 per-phase open_step）

| 钩子 | 新行为 |
|---|---|
| `bridge_perceive_opened/closed` | **不** `open_step`；写 `phases[]` + 填充/暂存 `context_before` |
| `bridge_think_opened` | 若无 open step → `open_step`；追加 `segment(kind=think)` + `phase(think)` |
| LLM completed | `record_thinking`；flush delta coalescer |
| `bridge_act_opened` | **同一** open step 上追加 `segment(kind=act)` + `phase(act)` + `tool_call`；禁止新 step |
| tool invoked | `tool_result`；不关 step |
| 无工具的最终 respond | think segment 结束后 `close_step` |
| 有工具且模型还需下一轮 | `close_step` 发生在 **本步工具全部收口之后**、下一 `think_opened` 之前（与 DSH `step/end` 对齐） |

子 agent：保持 `subagent_role` 前缀 step_id；子 run 自己的 steps/segments/phases 计数，不与父混加。

### D5. Doctor / CLI / Narrative

- Doctor H2/H3/H8：主断言改为 **step 树闭合**；新增 H-seg / H-phase：`totals` 与数组长度一致；segment/phase 时间不倒挂。
- `lca-ops journal steps`：默认 step 表；`--segments`、`--phases`；JSON 带 `totals`。
- `lca-ops explain|trace|cost|evidence`：**优先** `traces/runs/<id>/journal.json`，其次 raw `journal.jsonl` / `journal.raw.jsonl`。
- Narrative 标题：`steps=3 segments=5 phases=8`；因果链按 step；segment 缩进在 step 下。

### D6. Spine 硬化（与本 ADR 同批）

| ID | 问题 | 决策 |
|---|---|---|
| S1 | CLI journal 路径 | 见 D5；单测覆盖 `journal.json` 命中 |
| S2 | 双层 `body.tool.execute` | 对外 spine 只保留 **invocation** 层（`toolu_*` / 真实 sandbox 进出）；decision 包装改为 `body.tool.decision.{start,end}` 或降为 payload 字段 `wrapper=decision`，默认 LiveTail/trace 表隐藏 wrapper |
| S3 | `phase_graph.node` 缺 start | 补齐 `phase_graph.node.start`（与 end 成对）；或若图节点成本过高，则改名 `phase_graph.node.visit` 并文档声明非配对点——**优先补 start** |
| S4 | seq 与 transport 交织 | run 内 spine 事件使用 **run-local monotonic sequence**；`transport.route.*` 使用独立 `carrier_seq` 或不写入 run `events.jsonl`（只写 boot/carrier 日志）。禁止跨 carrier 重用 run seq |
| S5 | `exception.finally` 误导 | 成功路径改 `execution_point=lifecycle.finally`（或 `outcome=success` 且 `reason=normal_exit`）；仅真实异常保留 `exception.*` |
| S6 | 全局 `.lca/spine/events.jsonl` 空 | FileSink 默认路径与 run 绑定：`traces/runs/<run_id>/events.jsonl`；全局文件若保留则写 boot-only，并在文件头/README 注明「非 run 事件」 |

### D7. 不做的事

- 不把 segment 命名为 action / total_actions（思考不是 action）。
- 不删除 SSE 细粒度 delta（只禁止写入 journal spans）。
- 不在本 ADR 改变认知闭集步骤集合（perceive→…→stop 仍是运行时相位）。
- 不强制历史 7017 run 自动迁移；提供 `journal migrate --to 3.1`，旧 3.0 phase-as-step 可读。

## 后果

### 正面

- 与 DSH / ADR-0164 原文对齐：`steps=3` 可读。
- 同时保留用户要的 `segments=5` 与可审计 `phases=8`。
- narrative 体积下降（delta 合并）。
- 复盘 CLI 重新可用；spine 配对与 seq 可信度上升。

### 负面 / 风险

- `step_emitter` 与所有 `bridge_*` 调用点要改；测试需重写「一步一相」假设。
- UI 若硬编码 `steps.length === phase count` 会破 —— 需读 `totals`。
- 双层工具事件改名可能影响外部 spine 消费者 —— 记入 changelog。

### 兼容

- 读路径：无 `totals` / `segments` / `phases` 的 3.0 文档 → CLI 显示 warning，按「每条 JournalStep 即旧 phase-step」降级。
- 写路径：新 run 一律 3.1。

## 验收（以 `run_bb1b9570ef94` 同类拓扑为准）

1. 新跑同等拓扑：`totals.steps=3`、`totals.segments=5`、`totals.phases=8`。
2. `journal.narrative.md` 无逐条 `reasoning_delta` 列表；有合并后的思考文本或 `stream_stats`。
3. `lca-ops explain|cost <run_id>` 在仅有 `journal.json` 时成功。
4. spine：同一次工具调用不再出现两对无区分的 `body.tool.execute.*`；`phase_graph.node.start/end` 可配对；run `events.jsonl` seq 严格单调无碰撞。
5. 成功收尾不再出现像失败的 `exception.finally`（或带明确 success 语义）。

## 实施分期（计划阶段展开）

| PR | 内容 |
|---|---|
| PR-1 | 合约：`JournalDocument` 3.1、`SegmentRecord`/`PhaseRecord`/`totals`、读兼容 |
| PR-2 | coalescer + emitter 切步规则 + 单测（3/5/8） |
| PR-3 | narrative / doctor / CLI 路径修复 |
| PR-4 | spine S2–S6 |
| PR-5 | migrator 3.0 → 3.1 启发式（phase-as-step 折叠为 DSH step） |

## 参考

- deepseek-harness: `docs/architecture.zh.md` §轮次流程；`docs/agent-lifecycle.zh.md`
- LCA: `docs/adr/0164-journal-step-tree.md`；`lca/runtime/step_emitter.py`；`lca/runtime/step_lifecycle.py`
- 样本: `traces/runs/run_bb1b9570ef94/`
