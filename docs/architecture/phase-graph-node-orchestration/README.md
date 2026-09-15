> 仓内路径：`docs/architecture/phase-graph-node-orchestration/`  
> 审表正名：`03-six-column-0206.md`（C/I/P = ADR-0206）。架构室冻结：M1 立刻开，Add 暂缓。

# LCA Phase-Graph 编排规划 — 给李超的简报

> 作者视角：我是对照仓库里**真实 YAML**（`gh api` 读 `bundles/outer/phase_main.yaml` 及其子图，以及 agent/concept/primitive、guard-stack、recovery、spine）整理的规划，不是凭空画图。  
> 目录：`00-inventory.md` 现状清单 · `01-industry-matrix.md` 业界能力落点 · `02-proposed-graph.md` 目标图与迁移。

---

## 一句话

**外环六阶段已经立得住；真正的债是「三条图血缘并存」和「业界 agent loop 的关键能力还没进图缝」。目标不是堆节点，而是收敛成一张外环 + 概念复用，把 HITL / 预算压缩 / 并行工具 / 恢复边放进该放的缝里。**

---

## 现状我摸到了什么

生产 profile（`web-standard`）跑的是：

`perceive → think → act → reflect → remember → terminal.commit`

- **Think** 最完整：shortcut → 路由 → reason（fork 工具面 / plan / render）→ history → LLM → parse → **Gate⊂Think**。
- **Act** 纪律正确：validate → authorize → envelope → **effect gateway → Body → SafeExecutor → Sandbox** → observe；副作用没有第二入口。
- **Reflect / Remember** 偏薄，但职责清楚；恢复边今天主要挂在 `declarative-recovery` 插件上，**不在外环 YAML 里**。
- 同时还有 ADR-0220 的 **agent → concept → primitive** 三层图，以及旧的 **declarative-phase-graph** 边表——和生产外环**语义重叠、控制形状不完全一样**。这是清晰度最大的敌人。

Guard / 租约 / Spine 作为 **插件平面**（不是第七 phase）是对的：和 Hermes/DSH 的分层收敛方向一致，我不建议把它们硬塞进 phase 节点。

---

## 业界我们吸收什么（不抄名字进 node id）

| 能力本质 | 落 LCA 的位置 |
|---|---|
| ReAct 想–做–看 | 外环 think ↔ act + reflect |
| 危险审批 / HITL / 可恢复暂停 | `intervene` 子图 + `Command` 端口（ADR-0228 已指向），在 **envelope 之前**打断 |
| 预算 / 压缩 / 坏 JSON 修复 | Think 瀑布前置/后置节点，不进新 phase |
| 并行工具 + join | Act 的 fanout/join；执行仍在 SafeExecutor |
| 子代理 / handoff | `delegate` 子图，不是第七 phase |
| Plan–Execute | `plan.compose/revise`，TaskList 走 reducer |
| 循环刹车 / 无进展 | 继续用 Gate + `loop.policy`，不要每个计数器一个节点 |
| Checkpoint / 时间旅行 | Journal/Spine 做 SSOT，不另起一套 checkpointer 产品 |

详细对照表见 `01-industry-matrix.md`。

---

## 我建议怎么改（优雅优先）

1. **冻结一张外环**：`phase.main.outer` 作为唯一生产控制脊；恢复边、循环预算写回这张 YAML。  
2. **合并重复栈**：两套 perceive、两套 act 词汇、两套 observation fold、两套 decision parse → 各留一条概念路径。  
3. **少而准地加节点**：budget / compact / repair / fanout+join / intervene / plan / delegate——按 P0→P2 分批，见 `02-proposed-graph.md`。  
4. **清理**：declarative 边 SSOT、文档里的 `stop.main` 旧名、外品名节点、第二 Runtime、per-node max_visits（已由 ADR-0225 否决）。

验收口诀：闭集不变、副作用单轨、Gate 唯一改写 Decision、外环边自洽、无双 SSOT。

---

## 我不做的承诺

- 没有声称这些 ADD 节点已经在主干落地——规划如此，实现按 M1–M5。  
- 没有把 DeepSeek/Hermes/LangGraph 的产品名写进节点 id。  
- 没有建议「每个业界 checkbox 一个节点」——那会毁掉现在 Act/Think 的干净度。

---

## 建议你怎么用这份材料

1. 先扫本 README 对齐方向。  
2. 用 `00-inventory.md` 做评审事实底稿（和代码争论时以 YAML 为准）。  
3. 用 `01` 看「缺的能力放哪层」。  
4. 用 `02` 拍板 M1（外环边 SSOT）是否立刻开 PR；其余按依赖插入排期。

有问题直接拿 inventory 表里的节点 id / 边谓词对线即可。

- M1 fault-domain obligations attachment: [`04-m1-fault-domain-obligations.md`](./04-m1-fault-domain-obligations.md)
