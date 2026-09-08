# Agent Lab 群体智能架构评审 — 回应与暂缓登记

> **状态**：plans（对话材料 + 暂缓登记，非 note lifecycle）
> **对话日期**：2026-09-09
> **评审方案来源**：用户提交的外部文档《Agent Lab 群体智能架构评审与基建完善方案》（smartlijingyang-sudo/layered-cognitive-agent 的 agent_lab 图 B 评审）
> **评审对象**：图 B（agent_lab InfoEdge）vs 图 A（生产 LCA 架构）

## Problem

用户在 2026-09-09 的对话中提交了一份针对本仓库的群体智能架构评审方案，要求回应。本文件保存两件事：

1. 对评审方案的真实判断（已给出的回应正文）
2. 评审落地建议的"暂缓登记"（用户指示"现在不实施"）

后续若要继续该方向，按本文件末尾"暂缓登记"的恢复条件启动。

## How to use this file（下次打开该做什么）

1. **先读 §"Re-entry signals"**：看当下是否已出现重启信号
2. **若信号触发**：跳到 §"Per-PR concrete template"，按对应 PR 的"文件改动 / 验收命令"执行
3. **开 PR 前**：跑 §"Pre-flight checklist"的 5 条命令，全部绿再开始
4. **避免重复犯评审方案的方法缺陷**：参考 §"Pitfalls when revisiting the review"
5. **文件本身需要重新评估时**：跳到 §"Re-evaluation triggers"

## 评审方案的方向

评审方案提出的总方向：

> 把 Agent 从 Agent Loop Framework 升级为 Colony Runtime：单体 Loop 负责认知，图内核负责组合，Colony Control Plane 负责组织，Pheromone Field 负责间接通信，Session Fact Plane 负责真相，Effect Gateway 负责现实世界副作用。

具体提议见评审方案原文（未落档仓库，按需回看对话）。本回应就"是否采纳、采纳哪些"做出判断。

## 回应正文（核心判断）

### 一、对评审方案的总体判断

**评审方向是对的，但其"未吸收"判断与图 B 的真实位置存在偏差。** 这份评审有一个核心危险：把已存在或已 Proposed 的 LCA 机制当成"缺口"，并据此开出了大量重叠或平行的提案。若按评审文字直接落地，会同时违反 AGENTS.md 的两条红线：

- 禁止新增平行 ADR/Note/Proposal
- 改变闭集/层边界/SSOT/能力模型 → 必须先有 ADR/Note 草案

### 二、按"已落 / 已 Proposed / 真正缺口"三栏对照

#### 已落（事实/机制已实施）

| 评审缺口 | 仓库实情 | 文件锚点 |
|---|---|---|
| "可观测机制已吸收，缺群体指标" | Observability Exporters + Compile Graph 已落 | [ADR-0172](../adr/0172-observability-exporters.md) Proposed / [ADR-0198](../adr/0198-observability-compile-graph.md) Accepted |
| "事实单轨方向" | Session/FactGateway/spine/deriver 已 Implemented | [ADR-0186](../adr/0186-session-as-event-ssot.md) Implemented / [ADR-0191](../adr/0191-runtime-loop-dsh-convergence-and-control-plane.md) Implemented / [ADR-0194](../adr/0194-cognitive-loop-architecture-convergence.md) Implemented |
| "执行窄门 + 决策/观测分离" | CompiledRunPlan + Effect Gateway + Decision/Observation 分离 | [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md) Accepted / [ADR-0050](../adr/0050-run-bound-sandbox-runtime.md) / [ADR-0051](../adr/0051-run-workspace-plane.md) |
| "图作为执行事实" | 图作为 CompiledRunPlan region（0075 phase_graph） | [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md) |
| Effect idempotency / durable receipt | SqliteIdempotencyStore capability 已落地 | [ADR-0093](../adr/0093-continuous-control-plane.md) §实施状态 |

#### 已 Proposed（决策已立但未 Accepted）

| 评审缺口 | 仓库实情 | 文件锚点 |
|---|---|---|
| "没有持续群体控制面" | ADR-0093 正是 Continuous Control Plane（Proposed 2026-08-27）：Trigger / WorkItem / WorkQueue / Lease / SessionWorkActivator | [ADR-0093](../adr/0093-continuous-control-plane.md) |
| "没有群体级任务市场" | ADR-0093 §决策已规定 WorkQueue 持久去重、原子 claim、过期 lease 恢复、dead-letter | [ADR-0093](../adr/0093-continuous-control-plane.md) |
| "图 B 已吸收但仍依赖适配器" | agent_lab 双挂桥接 + delete-when 已立契约 | [docs/notes/proposed/seam/2026-09-08-agent-lab-absorb-end-state.md](../proposed/seam/2026-09-08-agent-lab-absorb-end-state.md) |
| "图内核扩展" | InfoEdgeSpec 嵌套子图 + CompiledGraphBundle | [ADR-0206](../adr/0206-information-graph-kernel.md) Proposed |

#### 与现有 ADR 冲突（不应采纳）

| 评审建议 | 冲突点 | 处理 |
|---|---|---|
| 新增 Pheromone 平面 / PheromoneSignal 词根 | [ADR-0206](../adr/0206-information-graph-kernel.md) §8 Reject 已显式表态"信息素 ≠ 可审计边；隐喻止于 Grant / Borrow；无衰减黑板垃圾场" | 驳回 |
| 建 `lca/colony/` 目录 | 违反 [ADR-0001](../adr/0001-five-layer-separation.md) 五层单向依赖分层；与 [ADR-0195](../adr/0195-platform-architecture-convergence.md) SSOT 矩阵冲突；重叠 [ADR-0093](../adr/0093-continuous-control-plane.md) 已实现组件 | 驳回 |
| 六类角色（Scout/Builder/Verifier/Router/Guardian/Forager）作为 Worker 类型 | [ADR-0075](../adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md) §二 + [ADR-0093](../adr/0093-continuous-control-plane.md) §验收 §6 "不得扩大 capability grant"；违反 AGENTS.md C1 认知闭集 | 须先 ADR/Note 草案，能力配置化而非新 Agent 类 |
| `ActionValue` / `expected_information_gain` / 三层 utility 函数 | 涉及新决策原语，违反 AGENTS.md C1 / C6 | 须先 ADR/Note 草案 |
| 五源四系拼接（蚂蚁/工蜂/COIN/Distributed/信息论） | 评审未做"已存在 ADR 索引"，直接拼接违反 AGENTS.md §1 "禁止新增平行 ADR/Note/Proposal" | 驳回作为落地方案；保留为对照材料 |

### 三、真正的缺口与建议路径

按 AGENTS.md §1 表"改变闭集/层边界/SSOT/能力模型 → 必须先有 ADR/Note 草案"，列出真正需要提案的项：

| # | 缺口 | 提案形式 | 范围 |
|---|---|---|---|
| 1 | ADR-0093 已 Proposed 但未 Accepted | 推进 ADR-0093 → Accepted（不重开 colony 层） | ADR 治理 |
| 2 | ADR-0093 Goal /优先级字段空白 | ADR-0093.1 Goal Graph 与 typed Goal/Priority 契约 | ADR 治理 |
| 3 | ADR-0093 §后果列出"分布式 worker 与 durable effect reconciliation"未落地 | ADR-0093.2 fence token / 跨进程 lease / 对账 | ADR 治理 |
| 4 | 群体可观测指标空白（评审 §8 P2 末尾 10 项） | ADR-0172.1 Group 指标族，列为 ADR-0172 扩展 | ADR 治理 |
| 5 | 角色分化（评审 §4.2 六类） | 若要做，先 ADR/Note 草案，明确"能力配置 + Policy 而非新 Agent 类"，对应 AGENTS.md C1 + ADR-0093 §验收 §6 "不得扩大 capability grant" | 须先 ADR |
| 6 | `ActionValue` / `expected_information_gain` / 三层 utility | 先 ADR/Note 草案（涉及新决策原语，须走 C6 原语默认 no-op + C1 闭集审查） | 须先 ADR |
| 7 | agent_lab 双挂吸收 | 已有 Note `2026-09-08-agent-lab-absorb-end-state.md`（proposed）驱动；按 delete-when 推进 | 已立契约 |
| 8 | 评审 §5.3 四类对象再切分 | 与 ADR-0186 / 0191 / 0194 / 0195 重复；以 ADR-0186 §3 + 0194 §1 为 SSOT，不开新平面 | 驳回新提案 |
| 9 | ADR-0206 P7 阶段闭集迁移 | 已立契约——ADR-0206 §10 P7 显式承担；不得在本主题下平行新开 | 已立契约 |

### 四、对评审 §1.2 "7 条尚未真正吸收" 的逐条再评估

| # | 评审判断 | 真实状态 |
|---|---|---|
| 1 | "没有一等的共享信息环境" | 错误。Session + FactGateway + ProjectionHost + ModelVisibleUnit（0193 / 0201）已是事实共享面；任何"群体共享"应经它们，不应另立 Pheromone 平面 |
| 2 | "没有群体级任务市场" | 部分成立，但 ADR-0093 已经声明 WorkQueue 为其承载；只需推进 ADR-0093 + ADR-0093.1 |
| 3 | "没有角色分化机制" | 成立，但 ADR-0075 §二 + ADR-0093 §验收 §6 已经划下边界：阶段由 PhaseExecutor 插件实现，角色不能扩大 capability grant。先 ADR 再实现 |
| 4 | "没有探索—利用控制" | 成立。先 ADR/Note |
| 5 | "没有群体收敛协议" | 成立（属于 #5 / #6），先 ADR |
| 6 | "没有信用与归因" | 成立。先 ADR |
| 7 | "没有持续群体控制面" | 错误。ADR-0093（Proposed 2026-08-27）正是这一面；配套 provider 与 bundle 已落地（`bundles/continuous-control-plane.yaml` + `lca-continuous-control-plane-factory` plugin）。下一步是补 ADR-0093.1 / .2 与推进 Accepted |

**结论：7 条中 2 条错误（#1、#7），3 条已有覆盖（#2、#3 部分、#5 部分），2 条新机制须先 ADR（#4、#6）。**

### 五、建议的下一步动作（PR-A~F）

按 AGENTS.md §1 表"改变闭集/层边界/SSOT/能力模型 → 先提交 ADR/Note 草案"：

| 提案 | 内容 |
|---|---|
| PR-A | 审计型 Note：把"建 lca/colony/ + Pheromone 平面"作为拒绝提案落档，写明已被 ADR-0093 / 0187 / 0206 覆盖，引用评审本文作对比 |
| PR-B | 推进 ADR-0093 → Accepted：补充 fence token 章节（§5.2）、引用 ADR-0187 routines 作为上层示例、显式拒绝"第七认知阶段" |
| PR-C | ADR-0093.1 Goal Graph 与 typed 契约：覆盖评审 §5.1 durable Work Graph 部分；声明 Goal / WorkItem / EvidenceBundle 的 frozen Pydantic 契约 |
| PR-D | ADR-0093.2 跨进程 lease / fence token / 对账：覆盖评审 §5.2 剩余部分 |
| PR-E | ADR-0172.1 Group 指标族：评审 §8 P2 末尾 10 项指标的归属 ADR，明确"指标由 Fact/Projection 派生，不由 worker 自报" |
| PR-F | 若团队确认要做角色分化 / 信息增益决策，先写 Agent Note (proposed)：明确新原语 vs AGENTS.md C1 / C6 的兼容性，给出 alternatives considered |
| 不动作 | lca/colony/、Pheromone Gateway、PheromoneSignal 词根、ActionValue 原语——这些都先等 PR-A~F 落定再决定 |

**前置动作**：把评审本文作为评论材料，本文件即为该动作的产物；运行 `./scripts/lca-ops notes-check` 与 `notes-audit`，确认新 Note 不与现有 ADR/Note 冲突。

## Alternatives considered

### Why 落档 plans/ 而非 docs/adr/？

ADR 走编号体系 + 元决策边界；本材料是"对话记录 + 暂缓登记"，不符合 ADR 元决策粒度。强行塞入会触发 ADR index 测试与编号漂移。

### Why 落档 plans/ 而非 docs/notes/proposed|implemented|rejected|archived/？

这些走 note lifecycle；本材料未实施、未到单点契约/原语/Seam/Profile/运行手册/复盘的任一类。`plans/` 目录专收过程材料，不参与 lifecycle。

### Why 落档 plans/ 而非 docs/specs/？

specs 是现行系统如何工作（权威规格）；本材料是暂缓登记，不是现行规格。

### Why 落档 plans/ 而非 docs/design/？

design 是宪法级长期设计；本材料尚未达到这个分量。

### Why 不创建 lca/colony/、PheromoneGateway、ActionValue 原语？

违反 ADR-0001 / 0195 五层单向依赖 + AGENTS.md C1 闭集 + ADR-0093 §验收 §6 capability grant 不扩大。

### Why 不在仓库落档评审方案原文？

仓库卫生：外部评审材料不进入 docs/；对话本身已有可追溯的提交记录，需要时回看对话即可。

## 暂缓登记（用户 2026-09-09 指示"现在不实施"）

| 提案 | 状态 | 恢复条件 |
|---|---|---|
| PR-A 拒绝 colony 层 Note | 暂缓 | 用户明确"开始实施" + 团队评审通过 ADR-0093 推进方案 |
| PR-B 推进 ADR-0093 → Accepted | 暂缓 | 同上 |
| PR-C ADR-0093.1 Goal Graph 契约 | 暂缓 | ADR-0093 升 Accepted 后启动 |
| PR-D ADR-0093.2 跨进程 lease / fence token | 暂缓 | 同 PR-C |
| PR-E ADR-0172.1 Group 指标族 | 暂缓 | 用户明确"开始实施" |
| PR-F 角色分化 / 信息增益 Note | 暂缓 | 用户明确"开始实施" |
| `lca/colony/` 目录 | **不创建** | 用户明确"开始实施" + 通过 ADR-0093 推进 + ADR-0093.1/2 提案 |
| PheromoneGateway / PheromoneSignal 词根 | **不创建** | 用户明确"开始实施" + 与 ADR-0206 §8 Reject 解锁 |
| ActionValue 原语 | **不创建** | 用户明确"开始实施" + 通过 AGENTS.md C1/C6 审查 |

**对评审方案本身的判断仍然有效**——只是执行时机延后，不会因为"暂缓"而漂移。

## 恢复条件总结

启动任何暂缓项之前，必须满足：

1. 用户明确"开始实施"
2. 对应 ADR/Note 草案已经评审通过（不与现有 ADR-0001 / 0093 / 0195 / 0206 / AGENTS.md C1-C13 冲突）
3. 若涉及新词根（`Pheromone*`、`ActionValue`、六类角色），先 ADR/Note 草案
4. 若涉及目录新增（`lca/colony/`），先 ADR 评估层边界与 ADR-0001 / 0195 五层单向依赖的兼容性
5. 若涉及 capability grant 扩大，先与 ADR-0093 §验收 §6 + AGENTS.md C5 三维单调对齐

## Re-entry signals（什么时候**应该**重启，不能再延）

下列任一信号出现时，"暂缓"应当被激活，**不应**继续沉睡：

| 信号 | 检测方式 | 指向哪条 PR |
|---|---|---|
| ADR-0093 仍未 Accepted，但 `lca/plugins/collaboration/continuous/` 有 ≥3 个 caller | `rg 'continuous_control_plane_factory' lca/` 计数 | PR-B |
| AssistantAgent routines 上线但调度失败 / dead-letter 误归零 | `journalctl` / run 记录 | PR-C + PR-D |
| agent_lab 双挂 `agent-lab-infoedge` 出现删除条件之一 | 对照 [Note delete-when](../proposed/seam/2026-09-08-agent-lab-absorb-end-state.md) §delete-when | 优先图 B 吸收，再回到本文件 |
| 出现"群体共享信号"需求（如多 worker 同源协调 / 跨 Worker 信息互引用） | RFC / 用户对话 / Issue 标题含 colony / swarm / multi-agent coordination | 先 PR-A 落档拒绝理由，**不直接做** colony 层 |
| 用户明确"开始实施" | 直接信号 | 启动对应 PR |
| AGENTS.md / 根 ADR 索引发生与群体运行时有关的大改 | `./scripts/lca-ops notes-audit` 红 | 重审 §"Re-evaluation triggers" |

**反向规则**：半年内（2026-03-09 前）若上述信号一个未出现，主动关闭本文件（迁 `docs/notes/archived/` 或删除均可，避免 plans/ 列表漂移）。

## Pre-flight checklist（开任意 PR 之前必过）

按 AGENTS.md §6 验证矩阵 + §7 最小命令入口：

```bash
# 1. ADR 索引健康
./scripts/lca-ops notes-audit

# 2. ADR-0093 当前状态（必须是 Proposed 或 Accepted 才能开始 PR-B/C/D）
grep -A1 '## 状态' docs/adr/0093-continuous-control-plane.md

# 3. agent_lab 删除条件扫描
rg 'agent_lab.runtime.runner' lca/ lca_kernel/ profiles/ bundles/

# 4. 层依赖扫描
# 任何准备在 lca/colony/、新增信息素、ActionValue 词根前必须确认：
./scripts/lca-ops lint-imports

# 5. 已知冲突段位（评审材料的反向核对，本文件 §"Pitfalls when revisiting the review"）
grep -nE 'PheromoneSignal|ActionValue|colony|fence_token' docs/adr/*.md
```

**不通过任意一项 = 不开 PR。** 任一项红 = 走 `notes-audit` 路径。

## Per-PR concrete template（PR-A~F 具体怎么做）

### PR-A — 拒绝 colony 层 Note（最先做，禁防止重复提案）

**文件改动**：

- 新建：`docs/notes/rejected/2026-09-09-colony-runtime-as-separate-layer.md`
- 三行头：`# Agent Note: colony 层作为运行时层已被 ADR-0093/0187/0206 覆盖` + `Status: rejected — 已被 ADR-0093 / 0187 / 0206 覆盖，新提案重复`

**正文骨架**（必含）：

- `## Problem`：记录评审方案提出过"lca/colony/"目录与 Pheromone 平面的诱惑点
- `## Proposal`：说明被否决
- `## Alternatives considered`：列出至少三个替代方案（沿用 ADR-0093、扩展 ADR-0206 § Borrow、扩展 ADR-0187 routines），每个一段
- `## Acceptance criteria`：`grep -rn 'lca/colony/' lca/ = 0` + `grep -rn 'PheromoneSignal' lca/ = 0` + `grep -rn 'ActionValue' lca/ = 0`

**验收命令**：

```bash
./scripts/lca-ops notes-check
grep -rn 'lca/colony/' lca/   # 必须空
grep -rn 'PheromoneSignal' lca/ # 必须空
```

### PR-B — 推进 ADR-0093 → Accepted

**文件改动**：

- 编辑 `docs/adr/0093-continuous-control-plane.md`：
  - `## 状态` 从 `Proposed — 2026-08-27` 改为 `Accepted — <today>`
  - §决策补一节 **"明确拒绝"第七认知阶段""**：引用 AGENTS.md C1 + ADR-0075 §二"图不得以添加未声明的'第七阶段'规避六个语义契约"
  - §决策补一节 **"fence token 留待 ADR-0093.2"**：明示 fence token / 跨进程 lease / 对账不在本 ADR 范围
- 新建 `docs/notes/implemented/seam/<today>-0093-accepted.md`：落档"0093 接受"+"未完成项归 ADR-0093.1/.2"

**验收命令**：

```bash
# ADR 状态必须为 Accepted
./scripts/lca-ops notes-audit | grep -A2 '0093'
# capability 仍可注入
./scripts/lca-ops why-plugin lca-continuous-control-plane-factory -p profiles/web-standard-continuous.yaml
# bundled 不变
./scripts/lca-ops inspect-tree profiles/web-standard-continuous.yaml | grep continuous-control-plane
```

### PR-C — ADR-0093.1 Goal Graph 与 typed 契约

**文件改动**：

- 新建 `docs/adr/0093.1-goal-graph-and-typed-contract.md`
- 三行头：`Status: Proposed — <today>`
- §Decision 包含：
  - `Goal`、`WorkItem`、`EvidenceBundle`、`Priority` 均为 `pydantic frozen, extra="forbid"`
  - 字段：`goal_id`、`committed_at`、`acceptance_criteria`、`evidence_refs`、`priority`、`cancellation_policy`
  - 与现有 ADR-0093 WorkItem 的差异：`Goal` 是用户/团队输入面，`WorkItem` 是调度面（已存在）
- §Relation：`Builds on ADR-0093; Refines ADR-0187 §routines`
- §Delete-when：`grep -rn 'Goal(' lca/plugins/assistant/ = 0` 且 routines 全走 typed 契约

**前置**：必须 PR-B 先 Accepted。

### PR-D — ADR-0093.2 fence token / 跨进程 lease / 对账

**文件改动**：

- 新建 `docs/adr/0093.2-fence-token-and-cross-process-reconcile.md`
- §Decision：
  - `Lease` 增加 `fence_token: ULID`，worker 提交 receipt 时强制 token 匹配
  - 跨进程：lease 由持久 backend（SqliteContinuousControlPlaneFactory）持有，worker 仅持 token
  - `uncertain` 状态显式三态（`pending | leased | dispatched` + `uncertain(reconciling)`）；不静默转 `failed` 或 `completed`
- §Delete-when：`fence_token` 字段全量 + `uncertain` 状态被 reducer 显式处理

**前置**：必须 PR-B 先 Accepted。

### PR-E — ADR-0172.1 Group 指标族

**文件改动**：

- 新建 `docs/adr/0172.1-group-metrics.md`
- §Decision：
  - 10 项指标（评审 §8 P2 末尾）：`signal_half_life / exploration_ratio / duplication_rate / verification_yield / consensus_latency / reversal_rate / colony_throughput / coordination_overhead / orphan_lease_rate / information_debt`
  - **派生面**：所有指标必须从 Fact/Projection 计算，不由 worker 自报
  - 写入：`lca_kernel/events/` 下的 `colony_metrics.yaml` 与对应 exporter
- §Delete-when：10 项指标全量在 metrics exporter 注册

**前置**：必须 PR-B 先 Accepted（共享 fact 单轨）。

### PR-F — 角色分化 / 信息增益 Agent Note

**文件改动**：

- 新建 `docs/notes/proposed/primitive/<today>-colony-role-differentiation.md`
- 必须满足 AGENTS.md C1 / C6 + ADR-0093 §验收 §6：
  - `## Problem`：描述"是否需要角色分化"的诱惑点
  - `## Proposal`：能力配置（`CapabilityProfile + ResponsePolicy`），**不是新 Agent 类**
  - `## Alternatives considered`：复用 ADR-0075 PhaseExecutor + 扩展 ADR-0187 routines vs 新增 Scout/Builder Worker
- §Acceptance criteria：`grep -rn 'class ScoutAnt\|class BuilderAnt' lca/ = 0`（即不引入以生物外形命名的 Python 类）

**前置**：先评审通过"是否需要角色分化"——若团队决定不必做，落 `rejected/` 而非 `proposed/`，避免概念漂移。

## Pitfalls when revisiting the review（评审材料的已知冲突，下次评估别再踩）

1. **Pheromone 平面与 ADR-0206 §8 Reject 冲突**——ADR-0206 已显式表态"信息素 ≠ 可审计边；隐喻止于 Grant / Borrow"。下次有人重提 Pheromone 黑板，直接指 ADR-0206。
2. **`lca/colony/` 与 ADR-0001 / 0195 五层单向依赖冲突**——五层不允许 colony 这种"跨层组织"层。下次有人重提，建 ADR 走元决策流程，**不**直接建目录。
3. **六类角色（Scout/Builder 等）与 ADR-0075 §二 + ADR-0093 §验收 §6 冲突**——阶段闭集 + capability grant 不扩大。下次重提，先 ADR/Note 草案，能力配置化而非新类。
4. **评审"未吸收"清单的时点漂移**——`7 条未吸收`是 2026-09-09 时点判断；ADR-0206 P7、ADR-0093 推进后结论可能变化。重读前先 `./scripts/lca-ops notes-audit` 看现状。
5. **五源四系拼接方法风险**——评审用了蚂蚁/工蜂/COIN/Distributed/信息论四源拼接，但未先做"已存在 ADR 索引"。下次类似评审直接按 AGENTS.md §1 表的"必须先答 7 问"拒绝方法缺陷。
6. **PlanCompiler、Region、phase_graph 等现有缝可能被复用**——任何"群体层"诉求先查 ADR-0068（CompiledRunPlan）/ 0075（phase_graph）/ 0093（continuous control）/ 0187（routines）/ 0206（InfoEdge region）能否扩展，能扩展就扩展。

## Re-evaluation triggers（什么时候重审本文件本身）

- ADR-0093 状态变化（Proposed → Accepted / Superseded）
- ADR-0206 P7 阶段闭集迁移完成
- agent_lab 双挂被吸收（删除条件全部满足）
- AGENTS.md / ADR-0195 分层变更
- 用户/团队对群体运行时方向有新决策

重审动作：

```bash
# 1. 拉 ADR 现状
./scripts/lca-ops notes-audit

# 2. 查 agent_lab 状态
rg 'agent_lab.runtime.runner' lca/ lca_kernel/ profiles/ bundles/

# 3. 查 colony 相关新增
rg -l 'colony|Pheromone|ActionValue' lca/ lca_kernel/

# 4. 读本文件 + ADR-0093 + ADR-0206 §11 决策记录
# 5. 决定：续暂缓 / 启动 PR / 迁 archived
```

## Acceptance criteria（本文件本身的验收）

- [x] 文件落位 `docs/notes/plans/`，与 `plans/` 目录约定一致（不参与 note lifecycle）
- [x] 评审方案的回应保留：方向判断 + 真正缺口 + PR-A~F 暂缓表
- [x] 不改动任何 ADR / Note / 运行配置 / 代码
- [x] 暂缓项恢复条件明确
- [x] 评审方案原文未落档仓库（按 AGENTS.md §8 卫生）
- [x] 文件头三段：状态、对话日期、来源——符合 plans/README §2 段位规范
- [x] 未来操作手册完整：How to use / Re-entry signals / Pre-flight / Per-PR template / Pitfalls / Re-evaluation triggers
- [x] 每个 PR 都有"文件改动 + 验收命令"四件套
- [x] 反向触发条件（半年内无信号则主动关闭）已落档

## Commands

### 文件落位体检（本文件刚写入时）

```bash
ls docs/notes/plans/
git status
git diff --check docs/notes/plans/2026-09-09-colony-runtime-architecture-review-response.md
wc -l docs/notes/plans/2026-09-09-colony-runtime-architecture-review-response.md
```

### 当前 ADR / Note 健康（每次重启前必跑）

```bash
./scripts/lca-ops notes-check
./scripts/lca-ops notes-audit
```

### 群体运行时方向的反向体检（确认尚未漂移）

```bash
# colony / pheromone / 信息素：必须为空
rg -l 'lca/colony/|PheromoneSignal|pheromone_gateway' lca/ lca_kernel/

# agent_lab 双挂吸收进度
rg 'agent_lab.runtime.runner' lca/ lca_kernel/ profiles/ bundles/

# ADR-0093 现状
grep -A1 '## 状态' docs/adr/0093-continuous-control-plane.md

# ADR-0206 现状
grep -A1 '## 状态' docs/adr/0206-information-graph-kernel.md
```

## Risks

- plans/ 目录是"非 Note 顶层目录"，`check_notes_tree.py` 当前不校验（notes/README §6 步骤一未启用）。若未来启用 note lifecycle 自动校验，本文件需要明示其 plans/ 身份。
- 若 ADR-0093 后续被 supersede 或大改，本文件的 PR-B/PR-C/PR-D 路径需要相应修订。
- 评审方案的"7 条未吸收"清单是 2026-09-09 时点的判断；若 ADR-0206 P7 阶段闭集迁移或 ADR-0093 推进后落地，结论可能漂移。

---

*plans/ 落档 — 2026-09-09（对话记录 + 暂缓登记，非 note lifecycle）*