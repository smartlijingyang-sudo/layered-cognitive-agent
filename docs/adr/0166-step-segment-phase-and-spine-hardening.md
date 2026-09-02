# ADR-0166: Step / Segment / Phase 三层计数与 Spine 硬化

- 状态: Accepted
- 日期: 2026-09-02
- 作者: coding-agent
- 修订: ADR-0164（纠正 step 边界的实现漂移；保留 step-tree 形状）
- **所有权 / SSOT / Model-visible 文件组织: 见 [ADR-0167](0167-spine-ssot-and-step-materialization.md)**（本 ADR 的「Store 唯一写者」改为「Accumulator 由 Coordinator 驱动；耐久真值是 spine」）
- 相关: ADR-0164, ADR-0165-execution-point-enforcement, ADR-0159, ADR-0065, ADR-0167；对照 deepseek-harness `docs/architecture.zh.md`（一步 = 一次模型请求 + 其工具）
- 触发样本: `run_bb1b9570ef94`（当前错误计为 8 phase-steps；正确应为 steps=3 / segments=5 / phases=8）

## 一句话

**step** 对齐 deepseek-harness（一次 LLM 请求 + 它触发的工具）；**segment** 计数 think|act（含思考）；**phase** 落盘闭集相位（含 perceive）。**废除 `step_emitter` bridge**：`StepCoordinator` 驱动累加器 + spine；**只有 agent loop / phase driver 可以 open/close step**；Brain/Body 只 `record_*`。流式 delta 在累加器内 coalesce。同步硬化 spine 观测缺陷。轨迹清晰与 prompt/skill 落盘见 ADR-0167 D3/D4。

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

### D3. 废除 bridge（第一性原理 / 大道至简）

**删除** `lca/runtime/step_emitter.py` 及其 `bridge_*` 调用点（PerceiveHub / TelemetryLLMAdapter / safe_executor 等）。

现状问题（存在性否定，不只是改职责）：

1. bridge 把「写事实」和「切步」混在同一旁路里；
2. 步边界由遥测适配器/执行器各自 `open_step`，循环真正的主人（loop）反而不是写者；
3. 双写（stream `record` + step_lifecycle）增加静默失败面（firewall skip）。

目标态只有一条写路径：

```text
Agent loop / phase driver
  ├── open_step / close_step / open_segment / close_segment / append_phase
  └── 把 StepWriter（或 store ContextVar）注入 Brain / Body / Perceive

Brain / Body / Perceive
  └── 只调 record_thinking / record_tool_* / record_reflect / append_delta
      （禁止 open_step / close_step）

StepCoordinator      ← 唯一写入 API（ADR-0167）
  ├── EventSpine.append     → events.jsonl（耐久 SSOT）
  └── StepTreeAccumulator   → 内存物化；finalize → journal.json
        └── coalesce deltas
```

可选极薄 `StepWriter` Protocol（方法 = accumulator 的 `record_*` / `append_delta` / `record_request_header`），**不是**第二套 bridge 模块；**facade 不得提供 `step_open` 给 Brain/Body**——`open`/`close` 仅 loop 包可见（`runtime/loop_step_control.py`）。

旧 stream `facade.record(JournalEvent)`：**不再经 bridge 双写**。若 SSE/raw 仍需要事件流，由 **deriver / progress 通道（ADR-0157）** 从 spine/step-tree 派生；不在业务 emit 点维护第二本账。Model-visible 正文进 `model_visible/step_N/`（ADR-0167 D3）。

### D4. 切步规则（仅 loop）

| 时刻（loop 拥有） | 行为 |
|---|---|
| 即将发起模型请求 | `open_step`；`append_phase(think)`；`open_segment(think)` |
| 模型流式输出 | Brain → `append_delta`（store 内 buffer） |
| 模型请求结束 | `record_thinking`（flush buffer）；`close_segment(think)` |
| 若有工具 | 对每个工具：`append_phase(act)`；`open_segment(act)`；Body → `record_tool_*`；`close_segment(act)` |
| 本步工具全部收口（或无工具） | `close_step`（对齐 DSH `step/end`） |
| perceive 相位 | **不**开 step；`append_phase(perceive)` + 写入下一 step 的 `context_before`（若 step 尚未 open，则写入 pending context，在下一次 `open_step` 时带入） |

子 agent：子 loop 自有 store 或带 `subagent_role` 的同一 store 规则；计数不与父混加。

### D4b. 流式 delta 合并（强制，在 store 内）

- `append_delta(channel, text)` 只追加 buffer；**禁止**每 delta `record_span`。
- `close_segment(think)` / `record_thinking` 时 flush → `thinking.reasoning`（及 decision/answer 字段）；可选一条 `stream_stats` span。
- SSE live 仍可走 progress 投影；narrative 默认不展开 delta。

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
- 不保留 `step_emitter`「改职责后继续活着」——**文件删除**，不是瘦身。
- 不新造平行 bridge 包换皮（`StepWriter` Protocol 若需要，放 `contracts/`，实现即 store）。
- 不删除 SSE 细粒度 progress（只禁止写入 journal spans）。
- 不在本 ADR 改变认知闭集步骤集合（perceive→…→stop 仍是运行时相位）。
- 不强制历史 7017 run 自动迁移；提供 `journal migrate --to 3.1`，旧 3.0 phase-as-step 可读。

## 后果

### 正面

- 与 DSH / ADR-0164 原文对齐：`steps=3` 可读。
- 同时保留用户要的 `segments=5` 与可审计 `phases=8`。
- narrative 体积下降（delta 合并）。
- 复盘 CLI 重新可用；spine 配对与 seq 可信度上升。

### 负面 / 风险

- 删除 `step_emitter` 是破坏性清理：所有 `bridge_*` 调用点与「一步一相」测试要改；短期 diff 大于「只改 bridge 职责」。
- UI 若硬编码 `steps.length === phase count` 会破 —— 需读 `totals`。
- 双层工具事件改名可能影响外部 spine 消费者 —— 记入 changelog。
- 过渡期若仍有代码走旧 `record(JournalEvent)` 且假定会进 step-tree，会漏步 —— 应用测试/`vulture`/契约测试挡住。

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
| PR-1 | 合约：`JournalDocument` 3.1、`SegmentRecord`/`PhaseRecord`/`totals`、store 内 coalescer API、读兼容 |
| PR-2 | **删除 `step_emitter`**；loop 单点 open/close；Brain/Body 只 `record_*`；单测锁定 3/5/8 |
| PR-3 | narrative / doctor / CLI `journal.json` 路径修复 |
| PR-4 | spine S2–S6 |
| PR-5 | migrator 3.0 → 3.1 启发式（phase-as-step 折叠为 DSH step） |

## 参考

- deepseek-harness: `docs/architecture.zh.md` §轮次流程；`docs/agent-lifecycle.zh.md`（driver 写 `step/start|end`，非 adapter 旁路）
- LCA: `docs/adr/0164-journal-step-tree.md`；`lca/runtime/step_lifecycle.py`（保留）；`lca/runtime/step_emitter.py`（**删除**）
- 样本: `traces/runs/run_bb1b9570ef94/`

## 修订记录

- 2026-09-02：初版 Accepted（仍描述「收窄 bridge」）。
- 2026-09-02：按第一性原理修订 —— **废除 bridge 存在性**；唯一写者 store；loop 切步（D3/D4/D4b）。
