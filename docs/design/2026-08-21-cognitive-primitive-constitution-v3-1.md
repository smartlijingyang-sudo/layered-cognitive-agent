# 认知原语宪法 v3.1

**§3.2 双层分类补丁 + C1 闭集内部细化**

| 字段 | 值 |
|---|---|
| 日期 | 2026-08-21 |
| 作者 | LCA Architecture |
| 状态 | Draft for ADR Review |
| 补丁对象 | [`2026-08-19-cognitive-primitive-constitution-v3.md`](2026-08-19-cognitive-primitive-constitution-v3.md) |
| 接受触发 | [ADR-0074](../adr/0074-plugin-everything-trimmed-implementation.md) 转 Accepted 时同步生效 |

---

## 0. 修订动机

v3 宪法的两处条款在 2026-08-21 提交的四篇 ADR（0066 / 0067 / 0068 / 0069）与 0074 实施计划下出现条款间张力，必须以宪法补丁形式正式对齐，否则会出现"ADRs 已声明 + 宪法文档未承认"的悬空：

1. **§3.2 八群 vs ADR-0069 十三群**——v3 §3.2 把概念群列为 State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition（9 项，按 8 群叙述）；ADR-0069 §一 引入 13 群的扩展分类学。0069 自己虽是 ADR，已满足 C6 的程序性要求，但 0069 §一那句"作为唯一概念坐标"会与 v3 §3.2 的宪法地位冲突。
2. **C1 六步闭集 vs ADR-0068 §三运行时序图**——v3 C1 规定六步闭集（perceive → think → gate → act → reflect → remember → stop）；ADR-0068 §三 把 think 拆为 prepare / decide / govern，把 reflect 拆为 evaluate / ... / commit，把 stop 拆为 decide / ... / journal.commit / checkpoint / safe-boundary。这是闭集内部细化，但 0068 未明确声明这一点。

本补丁解决以上两处张力，**不引入新原语、新阶段、新事件词表或新插件 schema**——符合 C6 的最小变更原则。

---

## 1. 修订 §3.2：双层分类学

v3 §3.2 增加以下分层条款（插入在原文 8 群列表之后）：

> **§3.2.1 双层分类**
>
> v3 8/9 群（State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition）是**宪法原语基础集**——用于宪法引用、Protocol 边界、群内策略归档、ADR 验收与 linter 检查。Code / doc / commit 引用群归属时以此集合为准。
>
> ADR-0069 的 13 群（Constitution / Identity / Spacetime / Facts / Perception / Cognition / Decision / Execution / Collaboration / Interaction / Composition / Creation / Evidence）是**扩展分类学**——用于跨系统推理、PlanTemplate 命名、ADR 与文档的概念坐标，不替代 v3 8/9 群的宪法地位。
>
> 13 群到 8/9 群的映射由 `lca plugin check` 命令维护，缺失映射时输出 warning 而非 error。`lca plugin check` 同时输出 LogicAddress 完整度评分（评分定义见 ADR-0074 V9 约束）。
>
> **新增第十四群（含 0069 13 群之外的扩展）必须证明现有 13 群均不能表达其主问题，并经 ADR 批准。** 此约束由 ADR-0069 §一继承，v3.1 仅做宪法地位确认。

### 1.1 13 群到 8/9 群映射（参考，非强制）

| ADR-0069 群 | v3 等价群 | 备注 |
|---|---|---|
| G0 Constitution & Kernel | (宪法外) | 不在 v3 群列表内 |
| G1 Identity, Intent & Contract | G1 Identity | TaskContract / GoalStack / AgentSpec |
| G2 Spacetime, Environment & Context | G4 Perceive | 时空事实作为 Perceive 输入 |
| G3 Facts, State & Knowledge | G3 Facts / G9 Journal | Facts = State，Knowledge = Journal-as-Truth 投影 |
| G4 Perception & Grounding | G4 Perceive | — |
| G5 Cognition, Models & Planning | G5 Cognition | — |
| G6 Decision, Command & Control | G6 Decision | 含 Gate 角色（v3 把 Gate 单列） |
| G7 Execution, Tools & Operations | G7 Execution | — |
| G8 Collaboration & Organization | G8 Collaboration | — |
| G9 Interaction, Transport & Interop | G9 Transport | — |
| G10 Composition, Configuration & Runtime Governance | G10 Composition | — |
| G11 Creation, Learning & Evolution | G11 Creation | — |
| G12 Evidence, Evaluation & Operations | G12 Evidence | — |

> 注：v3 编号为占位，本表"v3 等价群"列以中文名对齐；具体编号系统以宪法 §3.2 原文为准。

---

## 2. 修订 C1：闭集内部细化

v3 C1 条款（六步闭集：perceive → think → gate → act → reflect → remember → stop）保持不变；增加以下细化条款：

> **C1.1 ADR-0068 §三运行时序图为 C1 闭集的内部细化**
>
> ADR-0068 §三 给出的运行时序图
>
> ```text
> perceive.collect → perceive.admit → perceive.select
> think.prepare → think.decide → think.govern
> command.plan → act.authorize → act.budget → act.constrain → act.execute → act.observe
> reflect.evaluate → remember.admit → remember.commit
> stop.decide → journal.commit → checkpoint → safe-boundary
> ```
>
> 是 C1 六步闭集的**内部细化**，不引入新阶段。具体对应关系如下：
>
> | 0068 子步骤 | C1 阶段 |
> |---|---|
> | perceive.collect / admit / select | perceive |
> | think.prepare / decide / govern | think |
> | command.plan / act.authorize / budget / constrain / execute / observe | act |
> | reflect.evaluate | reflect |
> | remember.admit / commit | remember |
> | stop.decide | stop |
> | journal.commit / checkpoint / safe-boundary | (横切，非阶段) |
>
> 横切项 `journal.commit` / `checkpoint` / `safe-boundary` 由 v3 §6（Journal-as-Truth）与 ADR-0065（Recoverable Evidence Ledger）承接，不进入闭集阶段枚举。子步骤可由 ControlSlot 投稿表达，闭集本身不可由配置改写。

### 2.1 副作用条款

接受 C1.1 后，下列行为被视为 v3 闭集纪律的合法实施而非闭集扩张：

- ADR-0066 §二 9 个 Control Slot 在 C1 各阶段内的投稿
- ADR-0068 §三 子步骤在 C1 各阶段内的细化
- ADR-0068 §四 RunFact / RunDelta / Verdict / Decision / CommandEnvelope / Observation 作为 C1 各阶段间数据载体

下列行为**仍视为闭集扩张**，需 ADR：

- 在 C1 之外引入新阶段（如 self_reflect、meta_plan）
- 把 Control Slot 提升为独立阶段（如把 `stop.decide` 独立于 stop 阶段）
- 把 journal.commit / checkpoint / safe-boundary 提升为独立阶段

---

## 3. 修订 §0.1：现网一句话补录

v3 §0.1 列出"2026-08-19 核实"的现网状态。在 2026-08-21 提交的四篇 ADR 中，下列落地应补录：

| 提交 | 落地状态 | commit |
|---|---|---|
| ADR-0070 Reducer-as-Plugin | ✅ 已落地 | `eca3966b` |
| ADR-0072 Null-Default Discipline | ✅ 已落地 | `26bf0aaf` |
| ADR-0062 Plugin Runtime Cleanup | ✅ 已落地 | `e0eb2484` |
| ADR-0071 Composer-per-Cluster | ⏳ Proposed，与 ADR-0074 PR-5 同步推进 | — |
| ADR-0073 Session Path Convergence | ⏳ Proposed，与 ADR-0074 PR-7 同步推进 | — |
| ADR-0066 / 0068 / 0069 / 0074 | ⏳ Proposed，本补丁与 ADR-0074 同步推进 | — |

---

## 4. 受影响 ADR

| ADR | 关系 | 说明 |
|---|---|---|
| [ADR-0066](../adr/0066-declarative-atomic-control-plugins.md) | Refines（核心接受） | 9 Control Slot 由 ADR-0074 §一接受 |
| [ADR-0067](../adr/0067-spacetime-runtime-and-governed-creation.md) | Supersedes (part) | 8 态 / 5 子空间 / 6 道闸 / 7 Creator 面由 ADR-0074 §三裁剪 |
| [ADR-0068](../adr/0068-compiled-plugin-kernel-and-unified-run-plan.md) | Refines（核心接受） | CompiledRunPlan 三件套由 ADR-0074 §二接受 |
| [ADR-0069](../adr/0069-agent-primitive-system-and-declarative-grammar.md) | Reconcile | 13 群分类学由 v3.1 §1 接受为扩展分类学；0069 §一"唯一概念坐标"声明由 v3.1 §1 收口为"扩展分类学" |
| [ADR-0070](../adr/0070-reducer-as-plugin.md) | Co-evolves | 已落地（`eca3966b`），被 ADR-0074 PR-3 引用 |
| [ADR-0071](../adr/0071-composer-per-cluster.md) | Co-evolves (parallel) | PR-5 前置依赖 |
| [ADR-0072](../adr/0072-null-default-discipline.md) | Co-evolves | 已落地（`26bf0aaf`），被 ADR-0074 PR-2 引用 |
| [ADR-0073](../adr/0073-runsession-sole-session-path.md) | Co-evolves (parallel) | PR-7 前置依赖 |
| [ADR-0074](../adr/0074-plugin-everything-trimmed-implementation.md) | Meta-ADR | 本补丁与 0074 同步生效 |

---

## 5. 验收约束

| 编号 | 约束 | 自动化证据 |
|---|---|---|
| **CV1** | v3 8/9 群仍是宪法原语基础集 | `lca plugin check` 不引用 13 群做 group 检查 |
| **CV2** | 13 群通过 `lca plugin check` warning 输出 | `lca plugin check --functional-group <G0–G12>` 输出映射表 |
| **CV3** | 缺失 8→13 映射时 warning 而非 error | `lca plugin check --strict=false` 通过；`--strict=true` 报错 |
| **CV4** | C1 子步骤不可独立于 C1 阶段被表达 | ADR-0068 §三子步骤枚举的所有方法名存在于 C1 阶段对应插件内，不出现"独立阶段"方法 |
| **CV5** | Control Slot 不被提升为独立阶段 | `lca-ops explain control <slot>` 输出 C1 阶段归属，不出现"独立阶段"标签 |
| **CV6** | ADR-0074 PR-0 / PR-1 接受 v3.1 引用 | ADR-0074 §"与 v3 宪法的兼容性"表增列"v3.1 §1 双层分类 / §2 C1 细化" |

---

## 6. 后续

1. v3.1 与 ADR-0074 同步由 ADR 流程接受；v3.1 进入宪法文档树。
2. v3 原文保留不变（与 ADR 维护规则一致："不改旧文件"）。
3. v3.2+ 仅在出现新的闭集张力时提交；本文档不预先规划 v3.2 内容。