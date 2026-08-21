# ADR-0074 Plugin-Everything 实施追踪

> **这是 ADR-0074「Plugin-Everything 裁剪版」的中央实施账本。开始动手前先读这一份——本文件自包含。**

## 0. 读取顺序

> **【P0 关键声明：ADR-0066 自带的 PR 表已被 ADR-0074 重排】**
>
> ADR-0066 §"实施序列"自带的 PR-1~PR-9 表（PR-2=扩展 Manifest / PR-3=ControlPlan Resolver / PR-4=Gate/Stop 原子化 / PR-5=Execution Control 原子化 / PR-6=L4 组合根瘦身……）与本 tracker 的 PR-1~PR-12 表指**完全不同的实施步骤**。**Phase 0 PR-B 已对 PR-3↔PR-4 做过一次互换，PR-0.5 / PR-2.5 是新增项**。
>
> **只按本 tracker 的 PR 表执行**，不要去读 ADR-0066 的 PR 表。如果读 ADR-0066 的实施序列章节来对照执行步骤，会指向错误的模块与错误的 commit 路径。
>
> 决策记录：ADR-0066 §"实施序列"是 2026-08-21 初稿时的排期；ADR-0074 PR-B 在同日对该排期做了重排。**不要修改 ADR-0066**（"不改旧文件" 规则），本声明即作为该重排的事实记录。

开始动手前，按下列顺序读完前 6 节：

1. **ADR 监督范围**（了解 0066 / 0067 / 0068 / 0069 / 0074 五 ADR 整体监督状态）
2. §1 状态总览（知道当前 Phase 与 Next Action）
3. §6 tracker 自身的执行（5 ADR 监督 = 看 §6 流程链 + check_adr_supervision.py / route_legacy_patterns.py / lca-ops status-adr-supervision）
4. §2 5 个 Phase 0 决策（不可变更）
5. §3 依赖图（理解 PR ↔ PR ↔ ADR 阻塞）
6. §4 当前 PR 详情 / 已完成 PR 详情 + §7 已知陷阱 + §7.5 历史迁移路线图

读完上述 5 节后，再去读：

- `/home/lichao/layered-cognitive-agent/AGENTS.md`
- `/home/lichao/layered-cognitive-agent/docs/adr/0074-plugin-everything-trimmed-implementation.md`（**只读 §一~§五的设计意图，不读 §"实施序列"**——该章节与本 tracker 一致但 PR 编号不同，是参考而非执行依据）
- `/home/lichao/layered-cognitive-agent/docs/plans/adr-0074-acceptance-criteria.md`（**验收规约**：每条 V/CV 承诺对应一条 `uv run …` 命令；判定"是否真正达到预期架构效果"的唯一标准；本文件 tracker 标 ✅ Done 不代表验收通过）
- 当前 PR 涉及的具体 ADR 章节（仅当该 ADR 提供具体设计而非 PR 排期时）

---

## ADR 监督范围：5 个 ADR × 所有条款

本 tracker 是下列 5 个 ADR 落地的**单一中央账本**。任何 PR 完成时同步更新对应条目；任何 ADR 收到用户接受动作时同步更新状态。

| ADR | 关系 | 整体状态 | 落地入口（PR 序列） |
|---|---|:-:|---|
| **ADR-0066** Control Slot（9 槽 + 单调聚合）| Refined by ADR-0074 §一 | ⛔ 待 PR-1 | PR-1 dataclass → PR-2 Manifest 字段 → PR-3 compile → PR-4 migrate-first |
| **ADR-0067** Spacetime Runtime（5 子空间 / 8 状态 / 7 Creator 面 / 6 闸）| Superseded(部分) by ADR-0074 §三 | ⏳ 部分已裁剪 | 4 状态→PR-8 / 4 Creator 面→PR-9 / 6→3 闸→PR-4 / 子空间→ADR Draft 待 owner |
| **ADR-0068** Compiled Plugin Kernel（3 子 plan + CommandEnvelope + ArtifactController）| Refined by ADR-0074 §二 | ⛔ 待 PR-3 | PR-3 plan+compiler / PR-7 envelope / PR-8 artifact 4 状态 |
| **ADR-0069** Agent Primitive System（13 群 + LogicAddress + 11 关系 + 6 verbs + PlanTemplate + PluginContract）| Refined by ADR-0074 §四 | ⏳ taxonomy (PR-2 ✅ 字段) | PR-2 functional_group + logic_address + contract 字段 / PR-2.5 11 关系 data / PR-12 template / 6 verbs 含 0074 §四 |
| **ADR-0074** Plugin-Everything 本体 | 自身实施计划 | ⏳ 4 / 17 | §1 状态总览追踪 PR-0..PR-12 |

### 实施矩阵（ADR § × clause → 交付 PR）

| ADR § | clause 描述 | 状态 | 交付 PR | 备注 |
|:-:|---|:-:|:-:|---|
| **0066 §二** | 9 个 Control Slot 有限枚举 | ⛔ | PR-1 | 11 槽全表见 §19（含 PR-0 新增 2 个） |
| **0066 §三** | PluginDefinition.control 三件套（identity / authority / effects） | ⛔ | PR-2 | |
| **0066 §四** | 单调聚合（deny-on-any-deny / stop-on-any-stop / scope 收紧） | ⛔ | PR-3 编译期 + PR-7 运行时 | |
| **0066 §五-§六** | Composer + ControlPlan 描述 | ⏳ | ADR-0071 | 外移 |
| **0066 §七** | 决策点三分（策略 / 事实 / 强制） | ⛔ | PR-4 首次迁移 | |
| **0067 §一-§三** | SpacetimeContext 5 子空间 | 暂缓 | ADR Draft | 0074 §三 裁剪到 ExecutionSpace + LifecycleSpace |
| **0067 §四** | 8 状态机 | ⛔ → ✅ | **PR-8** | 0074 §三 裁剪到 4 状态；映射见 §18 |
| **0067 §五** | 6 道闸 | ⛔ | PR-4 | 0074 §三 裁剪到 3 道闸 |
| **0067 §七** | 7 Creator 面 | ⛔ | PR-9 | 0074 §三 裁剪到 4 面；映射见 §18 |
| **0068 §一** | CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan | ⛔ | PR-3 | |
| **0068 §二** | PluginContract 概念 | ⏳ → ✅ (PR-2) | PR-2 可选段 | 详见 §12；0074 §四 不替换 PluginDefinition |
| **0068 §五** | CommandEnvelope = effect 唯一入口 | ⛔ | PR-7 | architecture test 路径见 §14 |
| **0068 §六** | Boot 双轨消除 | ✅ Done | ADR-0062 PR-3/PR-4 (`e0eb2484`) | 已落地，详见 §3.3 |
| **0068 §七** | ArtifactController | ⛔ | PR-8 | 4 状态机 |
| **0069 §一** | 13 原语群分类学 | ⏳ taxonomy 部分 → ✅ (PR-2) | PR-2 functional_group 字段 | 群名见 §15.2 |
| **0069 §二** | LogicAddress 6 维 | ⛔ → ✅ (PR-2) | PR-2 logic_address 字段 | 评分细则见 §15.3 |
| **0069 §三** | 11 关系代数 | ⛔ → ✅ (PR-2.5) | PR-2.5 数据面 + PR-12 可视化 | |
| **0069 §四** | 6 contribution verbs | ⛔ | PR-3 PlanCompiler | verb 集见 §1 实施序列 §四 |
| **0069 §五** | PlanTemplate 实例（RAG / prompt chain / routing …） | ⛔ | PR-12 | 12 个 template 见 §16.2 |
| **0069 §六** | PluginContract 9 段 | ⏳ → ✅ (PR-2) | PR-2 可选段 + PR-12 | 详见 §12 |
| **0074 §一** | 接受 0066 / 0068 / 0069 核心 | ✅ Done | Phase 0 | |
| **0074 §二** | 接受 0068 CompiledRunPlan + §五 CommandEnvelope | ✅ Done | Phase 0 | |
| **0074 §三** | 裁剪 0067（4 状态 / 4 Creator 面 / 3 闸 / 2 子空间） | ✅ Done | Phase 0 | |
| **0074 §四** | 接受 0069 13 群 / LogicAddress / 11 关系 / PlanTemplate / PluginContract | ✅ Done | Phase 0 | |
| **0074 §五** | 整合本地 0070–0073 | ✅ Done | Phase 0 | |
| **0074 实施序列** | PR-0..PR-12 13 项 | ⏳ 4 / 17 | 详见 §1 | |

> **更新规则**：任何 PR 完成 → §1 同步更新；同时核查本表中对应 "交付 PR" 行是否可标 ✅，并清理"备注"列中"详见 §N"指向的章节；任何 ADR 收到 supersedes / Refines 关系变动 → 修改本表头行。

---

## 1. 状态总览

| Phase | PR | 标题 | 状态 | Commit | 完成日 | 阻塞 |
|:-:|:-:|---|:-:|---|:-:|---|
| **0** | A | v3.1 宪法补丁 | ✅ Done | `f980ace0` | 2026-08-21 | — |
| **0** | B | ADR-0074 重排 | ✅ Done | `c8c1b007` | 2026-08-21 | — |
| **0** | D | README 收尾 | ✅ Done | `5e32e704` | 2026-08-21 | — |
| **1** | 0 | audit 测量网 | ✅ Done | `8f8469eb` | 2026-08-21 | — |
| **1** | 0.5 | 清 19 个 pre-existing 失败 | ⏳ Ready（与 PR-0 并行） | — | — | — |
| **1** | 1 | ControlSlot + ControlPlan 数据面 | ✅ Done | `e2043986` | 2026-08-21 | PR-0 |
| **1** | 2 | PluginDefinition.control 可选段 | ✅ Done | `396c89ba` | 2026-08-21 | PR-1 |
| **1** | 2.5 | 11 关系代数扩展 CapabilityPlan | ✅ Done | `23161de1` | 2026-08-21 | PR-2 |
| **2** | 3 | CompiledRunPlan + PlanCompiler | ⛔ Blocked | — | — | PR-2.5 |
| **2** | 4 | think.guard / stop.decide 原子化 | ⛔ Blocked | — | — | PR-3 |
| **2** | 5 | spawn.bind_plan | ⛔ Blocked | — | — | PR-3 + ADR-0071 |
| **3** | 6 | plan_ref × Journal 绑定 | ⛔ Blocked | — | — | PR-5 |
| **3** | 7 | RunFact / CommandEnvelope 收口 | ⛔ Blocked | — | — | PR-6 + ADR-0073 |
| **3** | 8 | ArtifactController（4 状态机） | ⛔ Blocked | — | — | PR-7 |
| **4** | 9 | Creator 4 面化 | ⛔ Blocked | — | — | PR-8 |
| **4** | 10 | Golden profile + 文档收尾 | ⛔ Blocked | — | — | PR-9 |
| **4** | 12 | PlanTemplate + 关系图谱可视化 | ⛔ Blocked | — | — | PR-10 |

**Next Action**：PR-3（CompiledRunPlan + PlanCompiler）。

**累计完成**：7 / 17（PR-0 / PR-1 / PR-2 / PR-2.5 完成；PR-0.5 推迟到大重构结束后）。

---

## 2. 5 个 Phase 0 决策（不可变更）

> 这些决策在 Phase 0 review 中由用户拍板，后续工作**不得重新决定**。如果发现需要修改，必须先与用户确认。

| # | 决策 | 来源 | 不可变更理由 |
|--:|---|---|---|
| **1** | README 已把 0062 / 0070 / 0072 三者都标 Accepted | Phase 0 PR-D | 三者实现都已合并到 main（`e0eb2484` / `eca3966b` / `26bf0aaf`），仅标 0062 不一致 |
| **2** | PR-3 ↔ PR-4 互换：原 PR-3 → 新 PR-4，原 PR-4 → 新 PR-3 | Phase 0 PR-B | think.guard 迁移依赖 ControlPlan 编译产物；先有 PR-3 才能静态表达 |
| **3** | PR-0.5 新增：19 个 pre-existing 失败从外部风险并入主路径（实测 `uv run pytest --no-cov -q` 输出 19 failed，不是初稿估计的 22；user 决策：本计划阶段不深挖，按"大重构，搞完再测试"处理） | Phase 0 PR-B | PR-1 起步即会被这 19 个失败拖累 CI |
| **4** | PR-2.5 拆出：11 关系代数数据面前移到 PR-2 末尾，图谱可视化保留到 PR-12 | Phase 0 PR-B | PR-3 CompiledRunPlan 需要 11 关系才能完整表达 governance |
| **5** | 元 ADR 例外：README header 已声明「元 ADR（如 ADR-0074）是例外」 | Phase 0 PR-D | ADR-0074 同时是接受链记录器，旧规则不适用 |

---

## 3. 依赖图

### 3.1 PR ↔ PR（同一 Phase 0 计划内）

```
PR-0 (audit)
   ↓
PR-0.5 (清失败) ← 可与 PR-0 并行
   ↓
PR-1 (ControlSlot + ControlPlan dataclass)
   ↓
PR-2 (PluginDefinition.control 可选)
   ↓
PR-2.5 (11 关系代数扩展 CapabilityPlan)
   ↓
PR-3 (CompiledRunPlan + PlanCompiler)
   ↓
PR-4 (think.guard / stop.decide 原子化)
   ↓
PR-5 (spawn.bind_plan)
   ↓
PR-6 (plan_ref × Journal)
   ↓
PR-7 (CommandEnvelope 收口)
   ↓
PR-8 (ArtifactController)
   ↓
PR-9 (Creator 4 面化)
   ↓
PR-10 (Golden + 文档收尾)
   ↓
PR-12 (PlanTemplate + 关系图谱)
```

### 3.2 PR ↔ 外部 ADR

| PR | 依赖 ADR | 依赖原因 | 外部 ADR 状态 |
|--:|---|---|---|
| PR-5 | ADR-0071 Composer-per-Cluster | spawn.bind_plan 需要 4 个 sub-composer | Proposed — **必须先落地** |
| PR-7 | ADR-0073 Session Path Convergence | CommandEnvelope 收口需要 SessionService Protocol | Proposed — **必须先落地** |

### 3.3 已落地依赖（无需重做）

| ADR | Commit | 提供什么 |
|---|---|---|
| ADR-0070 Reducer-as-Plugin | `eca3966b` | Reducer Protocol + `_loop` 中间产物收口 |
| ADR-0072 Null-Default Discipline | `26bf0aaf` | NullCritic / NullSynthesizer / NullRetrievalPolicy |
| ADR-0062 Plugin Runtime Cleanup | `e0eb2484` | Cordis Fiber Boot 单轨 + L4 spawn 闭合 |
| ADR-0071 Composer-per-Cluster | TBD | **外部依赖**（见 §3.2、§3.4） |
| ADR-0073 Session Path Convergence | TBD | **外部依赖**（见 §3.2、§3.4） |

### 3.4 外部 ADR deadline 与 contingency buffer（P0 关键决策）

> **这是 §3.2 的硬约束展开：ADR-0071 / 0073 是 PR-5 / PR-7 的强前置；如果 0071 / 0073 推迟，PR-5 / PR-7 自动推迟，timeline 整体后移。**

| 外部 ADR | 必须落地 deadline | 不落地的影响 | contingency 方案 |
|---|---|---|---|
| **ADR-0071 Composer-per-Cluster** | **W8 末**（PR-4 完成后、PR-5 启动前） | PR-5 (spawn.bind_plan) 阻塞；后续 PR-6 / PR-7 顺延 | **方案 A（推荐）**：在 W8 末 deadline 之前若 0071 未落地，PR-5 拆为 PR-5a (BrainComposer + BodyComposer) + PR-5b (PerceiveComposer + TeamComposer)；brain / body 的 sub-composer 可独立落地，perceive / team 等 0071 |
| **ADR-0073 Session Path Convergence** | **W10 末**（PR-6 完成后、PR-7 启动前） | PR-7 (CommandEnvelope 收口) 阻塞；PR-8 / PR-9 / PR-10 / PR-12 顺延 | **方案 B（推荐）**：在 W10 末 deadline 之前若 0073 未落地，PR-7 拆为 PR-7a (CommandEnvelope dataclass + mint 工厂 + pipeline_safe_executor 接入) + PR-7b (SessionService Protocol 集成)；envelope 收口本身不依赖 SessionService 协议统一面，Protocol 集成可等 |

**Worst-case timeline 重排**：若 0071 与 0073 同时延后 W12，PR-5 / PR-7 顺延 W12，则整体 timeline 由 W16 推迟到 **W22**（详见 §13 时间估算）。

**buffer 预算（Week-level）**：

- W8–W10 之间预留 **2 周 buffer** 用于 0071 / 0073 的 slippage
- W12–W14 之间预留 **1 周 buffer** 用于 PR-8 / PR-9 的状态机 property test 调试
- W14–W16 之间预留 **1 周 buffer** 用于 golden profile 的兼容性回归
- 总 buffer：**4 周**，timeline 由"乐观 16 周"调整为"现实 **20 周**"（与 §13 一致）

> **决策记录（2026-08-21）**：当前是大重构周期，外部 ADR 落地与本计划主路径**并行推进**，不阻塞 PR-0 / PR-1 / PR-2 / PR-2.5 的早期工作；但 PR-5 启动前必须确认 0071 状态、PR-7 启动前必须确认 0073 状态。**任何 PR 启动前必须显式校验 §3.4 的两个 deadline 仍然可达**；若不可达，**立刻升级到 user**，不擅自重排。

---

## 4. 已完成 PR 详情：PR-2.5（11 关系代数扩展 CapabilityPlan）

> 当 Next Action 推出新 PR 时，把 §4 重命名为对应 PR 并复制一份此节作为工作底稿；保留原内容作为已完成 PR 的归档。
> PR-0 / PR-1 / PR-2 完成细节见 §5 Phase 1。

### 4.1 目标

落地 11 关系代数（ADR-0069 §三）：5 老关系（provides / requires / contributes_to / reads_fact / emits_fact，由 ResolvedProfile 提供者关系自动派生）+ 6 新关系（governs / executes / delegates / projects / revises / evaluates，由 plugin ``meta.relations:`` 段显式声明）。CapabilityPlan 数据面新增 ``relations`` 字段；Resolve 期验证引用合法性。**图谱可视化保留到 PR-12**，本 PR 只交付数据面 + 解析。

### 4.2 新增文件

| 文件 | 作用 |
|---|---|
| `lca/contracts/atoms/relation.py` | `Relation` 枚举（11 项 = 5 老 + 6 新）+ `NEW_RELATIONS` 集合 + `RELATION_GROUP_HINT`（PR-12 图谱颜色用）+ `parse_relation` / `validate_relations` |
| `lca/contracts/protocols/relation.py` | `TypedRelation` dataclass（source / target / kind / evidence / scope / weight）+ `typed_relation_to_dict` + `typed_relations_from_iter` factory |
| `lca/contracts/protocols/capability_plan.py` | `CapabilityPlan` dataclass（profile_path + provider_bindings + relations + revision）+ `ProviderBinding`（capability / owner_plugin / effect_class / revision）+ module-level accessors（`capability_plan_hash` / `capability_plan_to_dict` / `relations_of_kind` / `relations_from_plugin` / `relations_to_plugin`） |
| `lca/harness/profile/capability_plan_resolver.py` | `project_capability_plan()` 从 `ResolvedProfile` 投影 CapabilityPlan；`validate_targets` 校验 source / target 引用 |
| `tests/plan/test_11_relations.py` | 11 关系枚举 / TypedRelation / ProviderBinding / CapabilityPlan / hash 稳定 / order invariance / resolver 全覆盖（58 测试） |

修改文件：

- `lca/contracts/atoms/__init__.py` — re-export `Relation` 系列
- `lca/contracts/protocols/__init__.py` — re-export `CapabilityPlan` / `ProviderBinding` / `TypedRelation` 系列

### 4.3 实现要点

- **11 关系代数闭集**：5 老 + 6 新；新增第 12 关系需 ADR（C6 改闭集必 ADR）
- **`Relation` enum** 是 `str Enum`，字符串值稳定（序列化 / plan_ref 引用）；与 `lca.contracts.atoms.functional_group.FunctionalGroup` 等其它 atoms 同源
- **`TypedRelation` dataclass** 命名刻意区别于 `Relation` enum（避免 `lca.contracts.relation.Relation` 双重定义歧义）
- **`ProviderBinding`** 把 ADR-0061 capabilities DAG（``provides`` → owner）与 ADR-0062 effect class 合流到 typed 表达
- **`CapabilityPlan` 不放方法**（ADR-0015 contracts 纯类型契约）；访问器全部 module-level 函数
- **`capability_plan_hash`** 先按稳定 key 排序 bindings / relations 再 SHA-256 → 跨运行稳定
- **PR-2.5 阶段运行时不解** `CapabilityPlan`（PR-3 PlanCompiler 才消费）；本 resolver 是纯数据面
- **target 校验**：source 必填（默认 = plugin.id）；target 可指 plugin / capability / `descriptor:` / `fact:` / `journal.` 前缀引用；reads_fact / emits_fact 的 target 必须是 fact descriptor 风格

### 4.4 不变量

- **不改 ADR 文件**（0066/0067/0068/0069/0071/0073/0070/0072/0062 任何文件一字不改）
- **不动 layer 分层**：contracts/ 不能 import 实现层
- **不修 19 个 pre-existing 失败**（PR-0.5 范围；PR-2.5 新增 58 测试全过，**无新增失败**）
- **不扩张到 PR-3 范围**（不在 PR-2.5 内顺手做 CompiledRunPlan / PlanCompiler）
- **不放方法在 contracts/@dataclass**（ADR-0015；访问器为 module-level 函数）
- **不引入第 12 关系**（新增关系需 ADR）
- **不删除 5 老关系**（ADR-0061 capabilities DAG 已支持；PR-2.5 是扩展而非替换）
- **不改 `Relation` enum 字符串值**（序列化 / plan_ref 引用稳定；break wire 触发 PR-6 ExecutionEnvelope）

### 4.5 验证流程

```sh
# 1. ruff check + format
uv run ruff check --fix lca/contracts/atoms/relation.py lca/contracts/protocols/relation.py lca/contracts/protocols/capability_plan.py lca/harness/profile/capability_plan_resolver.py tests/plan/test_11_relations.py
uv run ruff format ...

# 2. PR-2.5 L1 sign-off 命令（acceptance-criteria §4.5 V11）
uv run python -c "from lca.contracts.atoms.relation import Relation, all_relation_values; print(len(all_relation_values()))"
# 预期: 11

# 3. CapabilityPlan hash 稳定 + order invariance
uv run pytest --no-cov tests/plan/test_11_relations.py -v -k "Hash"

# 4. 不破坏既有测试（除 §11 已登记的 pre-existing 19 失败）
uv run pytest --no-cov tests/harness/ tests/test_contracts.py tests/plan/ -q
```

### 4.6 完成判据

- 1 个新测试文件全过（58 测试，0 失败）
- harness/ + contracts/ + plan/ 测试无新增失败
- ruff 无新增警告
- mypy 无新增错误
- 11 关系枚举闭合（5 老 + 6 新）
- `web-standard.yaml` profile 投影出 ≥ 30 ProviderBinding（42 plugins）+ 0 explicit relations
- CapabilityPlan hash 稳定（cross-run determinism）

### 4.7 提交规范

```text
feat(contracts+harness): PR-2.5 11 relations algebra + CapabilityPlan data layer

- 新增 lca/contracts/atoms/relation.py (11 关系枚举 + NEW_RELATIONS + group hint)
- 新增 lca/contracts/protocols/relation.py (TypedRelation dataclass + accessors)
- 新增 lca/contracts/protocols/capability_plan.py (CapabilityPlan + ProviderBinding + accessors)
- 新增 lca/harness/profile/capability_plan_resolver.py (project_capability_plan + validate_targets)
- 新增 tests/plan/test_11_relations.py (58 测试)
- ADR-0074 PR-2.5 落地

Refs: ADR-0074 phase 1 / PR-2.5 / ADR-0069 §三 + ADR-0068 §一 +
tracker §15.3 + acceptance-criteria §4.5 V11
```

### 4.8 完成后如何更新本追踪

1. 在 `git commit` 后 commit hash（见 §1 状态总览对应行）
2. 更新 §1 状态总览：对应 PR 行 → ✅ Done
3. 更新「ADR 监督范围」实施矩阵：把对应 ADR § 行状态从 ⛔ 改为 ⏳/✅
4. 把 §4 标题从 "当前 PR 详情" 重命名为 "已完成 PR 详情：<N>"
5. **跑 `python scripts/check_adr_supervision.py` 验证 tracker 与 git 一致**
6. **跑 `python scripts/route_legacy_patterns.py` 看 owner_pr == PR-N 桶是否下降**
7. **同步更新 §7.5 历史迁移路线图**: `python scripts/route_legacy_patterns.py --md` 取最新值替换
8. 如果发现新陷阱，追加到 §7
9. 如果发现 PR 详情需调整（实现中发现 spec 偏差），更新 §4 但**保留变更说明**
10. 把追踪文件 commit 与代码 commit 分开（避免一个 commit 含两类变更）

### 4.9 已知陷阱（PR-2.5 新增）

- **`Relation` enum 与 `TypedRelation` dataclass 同名冲突**：enum 在 `lca.contracts.atoms.relation`，dataclass 在 `lca.contracts.protocols.relation`（命名刻意区分 `TypedRelation` 而非 `Relation`，避免 `lca.contracts.relation.Relation` 双重定义）。PR-3 PlanCompiler 引用时按需 `from lca.contracts.atoms.relation import Relation` 或 `from lca.contracts.protocols.relation import TypedRelation`。
- **`CapabilityPlan.relations` 在 PR-2.5 阶段为 opt-in**：plugin 作者未在 ``meta.relations:`` 段声明 → plan 只有 provider_bindings（来自 `provides`），无 typed relations；这是 PR-2 / PR-2.5 迁移期的合法状态。PR-3 PlanCompiler 落地后，PlanCompiler 会基于 ControlPlan + provider_bindings 推断部分关系（governs / executes / delegates），补足到 CapabilityPlan.relations。
- **`TypedRelation.source` 默认 = plugin.id**：用户在 ``meta.relations:`` 不指定 source 时，resolver 默认填 plugin.id。**这意味着 self-relation（source == plugin.id）合法**（用于描述 plugin 自己的 governance / evaluation 行为）。如果用户显式指定 source 为不存在的 plugin id → `CapabilityPlanResolveError`（PR-2.5 阶段 fail-fast）。
- **`TypedRelation.target` 校验可关闭**：`CapabilityPlanOptions(validate_targets=False)` 时，target 不校验（用于 PR-3 PlanCompiler 推断阶段）；默认 `validate_targets=True`。
- **`capability_plan_hash` 不包含 resolver options**：options 改变（如 `include_disabled=True`）→ hash 变化（因 bindings 数量变化）。跨运行同 options → 同 hash。

---

---|
| `audit-control-surface` | 0 | V1 基线：尚未硬编码 slot 字符串 |
| `audit-state-writers` | 40 | V3 / C4 基线：40 处直接 state 写入待 PR-7 收口 |
| `audit-direct-commands` | 2 | V4 基线：2 处 Body 直接 import transport |
| `audit-hook-attach` | 0 | V5 / PR-7 基线：起点已干净 |

**详见**：§4 PR-0 完成判据；§10 V/CV 验收闭环。

---

## 5. 已完成 Phase 详情

### Phase 0：宪法对齐与顺序重排（2026-08-21）

**Goal**：在不破坏 v3 宪法的前提下，让 ADR-0074 的 PR 序列在宪法层面对齐、可被下游 agent 无歧义执行。

**Commits**：

| Commit | 内容 | 文件 |
|---|---|---|
| `f980ace0` | v3.1 宪法补丁（§1 双层分类 + §2 C1 闭集细化 + CV1-CV6 验收） | `docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md`（+156） |
| `c8c1b007` | ADR-0074 重排（PR 顺序 + V9 评分 + Boot 失实修正 + 兼容性表） | `docs/adr/0074-plugin-everything-trimmed-implementation.md`（+371） |
| `5e32e704` | README 收尾（0062/0070/0072 Accepted + 元 ADR 例外） | `docs/adr/README.md`（±32） |

**Phase 0 总评审**：8/10 架构优雅度。

**Phase 0 留下的关键约束**（详见 §2 决策表）。

### Phase 1 PR-0：audit 测量网（2026-08-21）

## 6. tracker 自身的执行（ADR 监督 = 5 ADR 监督）

**核心命题**：实施了本 tracker 即实施了 ADR-0066 / 0067 / 0068 / 0069 / 0074 五份 ADR。

**工程化执行链**（CI / pre-commit / operator 都可以撞这条链验证 ADR 落地）：

```
tracker.md (declarative source of truth)
    ↓ parsed by
scripts/check_adr_supervision.py        — 验证 §1 / 实施矩阵 / Next Action 一致性
scripts/route_legacy_patterns.py        — 把 PR-0 baseline 路由到 owner PR
    ↓ invoked by
pre-commit hooks                        — 防止 tracker 漂移
pytest tests/test_check_adr_supervision — 单元测试
lca-ops status-adr-supervision          — 人类 / agent 现场查问
```

### 6.1 scripts/check_adr_supervision.py

验证 tracker.md 内部一致性 + 与 git/代码外部一致性：

| 校验 | 规则 |
|---|---|
| §1 status Done | ✅ Done 行必须引用真实 git commit hash（`git cat-file -e` 验证） |
| 实施矩阵 | ✅ 行必须含具体交付者（PR-N 或已知 commit） |
| Next Action | 必须指向首个未完成的 PR，不能指向 Done 行 |
| 全 tracker | 任意 `\`<hex>\`` 形式的 commit 引用必须存在于 git |

退出码：0 一致 / 1 一致性破坏 / 2 tracker 缺失。

### 6.2 scripts/route_legacy_patterns.py

跑 4 个 audit_*.py 脚本，输出 PR-N owner 路由表。**这是"历史迁移路线图"段的机械化产出**：

```
uv run python scripts/route_legacy_patterns.py       # human
uv run python scripts/route_legacy_patterns.py --md  # 直接粘贴到本文件的迁移路线图段
uv run python scripts/route_legacy_patterns.py --json
```

### 6.3 lca-ops status-adr-supervision

聚合 view：

```sh
./scripts/lca-ops status-adr-supervision
# ADR supervision tracker: consistent ✅
#
# Historical migration baseline (PR-0 → ownership):
# ... (route_legacy_patterns 输出)
```

### 6.4 pre-commit + pytest

- `scripts/check_adr_supervision.py` 作为 local pre-commit hook 接入（详见 §8 .pre-commit-config.yaml 引用）
- `tests/test_check_adr_supervision.py` 4 个测试守护脚本自身正确性
- CI 跑 `pytest tests/test_check_adr_supervision.py` + `python scripts/check_adr_supervision.py`

**任何 ADR 落地证据 = tracker + 一致性脚本同时通过 + 历史迁移基线下降 + lca-ops status-adr-supervision 全绿**。

---

## 7. 已知陷阱（living document）

> 任何后续工作遇到的新陷阱、ADR 漂移、测试 flaky、依赖变更，都追加到这里。下一个动手者必读。

### 7.1 已记录

- **`docs/adr/README.md` 字数预算 900**：每加一行 ADR 表要重算；em-dash (`——`) 与单 em-dash (`—`) 等价（都算 1 word）；markdown 表格里多行描述挤预算。**经验**：所有 ADR 描述保持短，主标题句即可，详细描述去 ADR 文件。
- **`docs/adr/README.md` 测试强制**：`tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 要求 README 列出所有 `docs/adr/*.md` 文件。**不能删除 ADR 文件来减字数**——会破测试。
- **ADR 状态变更路径**：ADR 文件本身**不能改**（"不改旧文件" 规则），状态变更通过：
  - README 索引更新（可）
  - 新 ADR 的 `Refines` / `Supersedes` 关系（可）
  - 用户单独接受动作（用户决定）
- **ADR-0070 与 Boot 双轨无关**：ADR-0070（`eca3966b`）只收口 `_loop` 中间产物；Boot 双轨由 ADR-0062 PR-3/PR-4（`e0eb2484`）处理。**新 agent 不要再混淆**。
- **19 个 pre-existing 测试失败**（实测，2026-08-21 `uv run pytest --no-cov -q` 输出）：来源主要是 journal v2 envelope 错配 / OpenAI compat gateway 的 plugin context boot / DSH 删除遗留 / glossary 词条覆盖四大类。**不在 PR-0 范围内修复**；PR-0.5 处理（详见 §11 测试失败分类清单）。**user 决策（2026-08-21）：当前是大重构周期，测试修复排在所有 PR 落地之后；PR-0.5 范围相应调整为"为后续 PR 清理阻塞"，非"全部清零"**。
- **`lca-ops` 子命令注册机制**：参考 `scripts/lca-ops` 现有 audit/diagnose 子命令。新增 audit 子命令时复用相同模式。
- **`/home/lichao/.cache/uv` docker overlay 只读**：本会话遇到 `uv: error: Could not acquire lock ... Read-only file system (os error: 30) at path /home/lichao/.cache/uv/.tmpXXXXX`。**绕过**：`UV_CACHE_DIR=/tmp/uv-cache-test uv run ...`。前提：现有 lock 释放后；CI 环境正常
- **`lca-ops` cli.py GUIDE 段含 `─` (U+2500) box-drawing**：`edit` 工具的 old_string 必须字节级匹配才能替换，否则 `Error: old_string was not found`。复杂字符场景用 `python3 -c "content.replace(old, new)"` 更稳

### 7.2 待识别

[新发现时追加]

---

## 7.5 历史迁移路线图（PR-0 baseline → owner PR）

> 本节由 `scripts/route_legacy_patterns.py --md` 自动产出；每次 audit baseline 下降时同步更新。**（手动维护 = 漂移源头，优先 re-run 脚本）**

### 7.5.1 当前 snapshot（2026-08-21，PR-0 落地时）

PR-0 audit 测量网对全仓库扫一次得到 42 条违规基线，路由如下：

| Owner PR | 数量 | 违规类型分布 | 路由理由 |
|---|:-:|---|---|
| **PR-3** CompiledRunPlan + PlanCompiler | 1 | state_writers=1 | MemoryPolicy / CapabilityPlan 中读写 |
| **PR-4** think.guard / stop.decide 原子化 | 12 | state_writers=12 | ModularBrain / Reasoner 写入 |
| **PR-7** RunFact / CommandEnvelope 收口 | 29 | direct_commands=2, state_writers=27 | CommandEnvelope 收口 + Body.execute 5 闸 |
| **PR-99** 测试修复专期 | 19 | （外加 19 个 pre-existing test failures，详见 §11） | 大重构后统一清零 |

合计 42 + 19 = 61 条历史迁移基线，由 PR-3 / PR-4 / PR-7 / PR-99 承担。

### 7.5.2 更新规则

- PR-N 完成 + merge 后，跑 `python scripts/check_adr_supervision.py` 确认 tracker 同步；再跑 `python scripts/route_legacy_patterns.py` 看到 owner_pr == PR-N 的桶从 N1 下降到 N2
- 当某个 owner 桶从 0 触发：把 §1 状态总览对应 PR 行标 ✅ Done，并修改本节"当前 snapshot"日期
- 任何手动编辑本节：先 `python scripts/route_legacy_patterns.py --md` 取最新值（防止手写漂移）

---

## 8. 文件索引

| 文件 | 用途 |
|---|---|
| `/home/lichao/layered-cognitive-agent/AGENTS.md` | 工作区纪律（最严格） |
| `/home/lichao/layered-cognitive-agent/docs/adr/0074-plugin-everything-trimmed-implementation.md` | **必读** PR 表 + 兼容性 + 风险 |
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md` | v3.1 补丁 |
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-21-code-aligned-architecture-audit.md` | 审计原文（理解为什么） |
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` | v3 宪法（非变动基线） |
| `/home/lichao/layered-cognitive-agent/docs/adr/0066-declarative-atomic-control-plugins.md` | Control Slot 9 槽位来源 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0068-compiled-plugin-kernel-and-unified-run-plan.md` | CompiledRunPlan 三件套来源 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0069-agent-primitive-system-and-declarative-grammar.md` | 13 群分类学 + 11 关系来源 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0071-composer-per-cluster.md` | PR-5 外部依赖 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0073-runsession-sole-session-path.md` | PR-7 外部依赖 |

---

## 9. V1-V12 ↔ PR 完成判据映射（节流引用）

完整的 V / CV 验收表见 [§10 V/CV 验收闭环](#10-v1-v12--pr-完成判据映射--v31-cv1-cv6-验收闭环)。本节只放该表 TL;DR，§10 是权威版本。

| V 约束 | 在哪一 PR 首次生效 | 该 PR 完成时新增的强制证据 |
|:-:|:-:|---|
| V1 控制面单一入口 | PR-3 | `lca-ops explain control <slot>` 列表 |
| V2 plan_hash 确定性 | PR-3 | property test 100 次随机 |
| V3 Reducer 唯一写 | PR-0 → PR-7 | `lca-ops audit state-writers` 缩窄到 reducer |
| V4 CommandEnvelope | PR-7 | architecture test |
| V5 plan_ref 全覆盖 | PR-6 | replay test |
| V6 4 状态封闭 | PR-8 | state migration property test |
| V7 Creator 4 面 | PR-9 | `lca-ops creator --help` 4 sub |
| V8 capability 单调 | PR-3 + PR-8 | property test 子代理 ⊆ 父代理 |
| V9 LogicAddress 6 维 | PR-2 | `lca plugin check` 评分 |
| V10 13 群分类 | PR-2 | functional_group 字段 |
| V11 11 关系 | PR-2.5 + PR-12 | relations 字段 + 图谱 |
| V12 PlanTemplate 可发现 | PR-12 | `lca-ops plan list-templates` |

---

## 10. V1-V12 ↔ PR 完成判据映射 + v3.1 CV1-CV6 验收闭环

> **这是 review 中识别的最大缺口：ADR-0074 定义了 V1-V12 验证约束，v3.1 补丁定义了 CV1-CV6 验收约束，但每个 PR 的完成判据没有显式声明"本 PR 完成 → 哪些 V/CV 约束的自动化证据被建立"。本节是验收闭环。**

### 10.1 V1-V12 ↔ PR 完成判据映射表

| V 约束 | 自动化证据 | 在哪个 PR 完成时首次生效 | PR 完成判据的强制性条款 |
|:-:|---|---|---|
| **V1** 控制面单一入口 | `lca-ops explain control <slot>` 列出该 slot 的所有 entry、来源 bundle/patch、order、activation 表达式 | **PR-3**（ControlPlan Resolver 编译产出后）| PR-3 完成时必须新增 `tests/harness/test_explain_control.py` 覆盖 9 个 slot 至少各 1 个 entry |
| **V2** CompiledRunPlan 确定性 | 同 profile × TaskContract × Environment → 同 plan_hash | **PR-3**（PlanCompiler 落地）| PR-3 完成时必须新增 property test：固定输入 → 固定 hash，跨 100 次随机运行 |
| **V3** Reducer 唯一写 State | `lca-ops audit state-writers` 输出空集（除 reducer） | **PR-0**（audit 测量网建立基线） + **PR-7**（RunFact 收口 effect 后最终成立） | PR-0 完成判据："audit state-writers 输出非空且可读"；PR-7 完成判据："audit state-writers 缩窄到只剩 reducer" |
| **V4** CommandEnvelope 必经 5 闸 | architecture test 拒绝无 envelope 的 tool call；Body.execute stack trace 必含 `command_envelope.mint` | **PR-7**（CommandEnvelope 收口） | PR-7 完成时必须新增 `tests/architecture/test_command_envelope_required.py`：AST 扫描所有 Body.execute 调用，确保 mint_envelope 在 stack trace |
| **V5** plan_ref 全覆盖 | replay test 取任意 run，重放其 journal 即可重建 plan | **PR-6**（plan_ref × Journal 绑定） | PR-6 完成时必须新增 `tests/journal/test_plan_ref_replay.py`：跑 1 个完整 agent run，断言每条 journal fact 携带 plan_ref |
| **V6** 4 状态机封闭 | state migration property test：合法迁移覆盖；非法迁移抛 InvalidStateTransition | **PR-8**（ArtifactController 4 状态） | PR-8 完成时必须新增 `tests/artifact/test_state_machine_property.py`：覆盖 DRAFT→VERIFIED→ACTIVE→RETIRED 4 条迁移 + 至少 4 条非法迁移断言 InvalidStateTransition |
| **V7** Creator 4 面化 | `lca-ops creator --help` 输出 4 个 subcommand | **PR-9**（Creator 4 面化） | PR-9 完成时必须新增 `tests/creator/test_4_faces.py`：断言 `lca-ops creator {inspect,author,validate,promote}` 4 个 subcommand 都可调用，且 stage/retire/publish 通过 promote flags 实现 |
| **V8** capability 单调 | 子代理 / 子 scope / 子 artifact grant ⊆ 父 | **PR-3** + **PR-8**（CapabilityPlan 编译 + Artifact 状态收敛）| PR-3 完成时新增 `tests/test_capability_monotonicity.py`：property test 覆盖子代理 grant ⊆ 父代理；PR-8 完成时扩展到 artifact grant |
| **V9** LogicAddress 完整度 | `lca plugin check` 输出 LogicAddress 6 维完整度评分 | **PR-2**（PluginDefinition.control 可选段 + LogicAddress 元数据） | PR-2 完成时必须新增 `tests/plugin/test_logic_address_scoring.py`：覆盖 4 档评分边界（≥75 / 50–74 / <50 / --strict） |
| **V10** 13 原语群覆盖 | `lca plugin check` 输出每个 plugin 的 functional_group 归属 | **PR-2**（functional_group 字段新增）| PR-2 完成时必须新增 `tests/plugin/test_functional_group.py`：覆盖 v3 8/9 群 ↔ ADR-0069 13 群映射表（详见 §15） |
| **V11** 11 关系代数 | CapabilityPlan.relations 解析通过；6 种新关系覆盖 | **PR-2.5**（11 关系数据面） + **PR-12**（关系图谱可视化）| PR-2.5 完成时必须新增 `tests/plan/test_11_relations.py`：覆盖 11 种关系枚举 + Resolve 解析；PR-12 完成时新增图谱可视化测试 |
| **V12** PlanTemplate 可发现性 | `lca-ops plan list-templates` 输出 12 个标准 PlanTemplate | **PR-12**（PlanTemplate 列表工具） | PR-12 完成时必须新增 `tests/golden/plan_templates/*.yaml`：12 个 PlanTemplate 各 1 个 golden + golden test |

### 10.2 v3.1 CV1-CV6 ↔ PR 完成判据映射表

| CV 约束 | 自动化证据 | 在哪个 PR 完成时首次生效 |
|:-:|---|---|
| **CV1** v3 8/9 群仍是宪法原语基础集 | `lca plugin check` 不引用 13 群做 group 检查 | **PR-2**（functional_group 字段新增，但不影响 v3 8/9 群检查） |
| **CV2** 13 群通过 `lca plugin check` warning 输出 | `lca plugin check --functional-group <G0–G12>` 输出映射表 | **PR-2** |
| **CV3** 缺失 8→13 映射时 warning 而非 error | `lca plugin check --strict=false` 通过；`--strict=true` 报错 | **PR-2** |
| **CV4** C1 子步骤不可独立于 C1 阶段被表达 | ADR-0068 §三子步骤枚举的所有方法名存在于 C1 阶段对应插件内 | **PR-4**（think.guard / stop.decide 原子化首次迁移）|
| **CV5** Control Slot 不被提升为独立阶段 | `lca-ops explain control <slot>` 输出 C1 阶段归属 | **PR-3** |
| **CV6** ADR-0074 PR-0 / PR-1 接受 v3.1 引用 | ADR-0074 §"与 v3 宪法的兼容性"表增列"v3.1 §1 双层分类 / §2 C1 细化" | **本 tracker 已完成（§"与 v3.1 兼容性" 显式列出）** |

### 10.3 完成判据黄金法则

> **任何 PR 完成（commit 合并到 main）必须满足**：
> 1. PR 描述明确引用本节 10.1 / 10.2 中对应的 V/CV 约束
> 2. PR 引入的测试覆盖该 V/CV 约束的自动化证据
> 3. `uv run pytest --no-cov -q` 不引入新失败（pre-existing 19 个按 user 决策推迟）
> 4. `uv run ruff check --fix <改动路径>` 与 `uv run ruff format <改动路径>` 通过
> 5. tracker §1 状态总览对应行更新为 ✅ Done

---

## 11. 19 个 pre-existing failure 分类与 PR-0.5 推迟决策

> **user 决策（2026-08-21）**：当前是大重构周期，测试修复推迟到大重构结束后。本节是事实记录与推迟决策的依据。

### 11.1 19 个 failure 的来源分类（实测，2026-08-21 `uv run pytest --no-cov -q`）

| 类别 | 数量 | 测试列表 | 性质 |
|---|:-:|---|---|
| **A. OpenAI compat gateway plugin context boot** | 6 | `test_openai_compat_gateway.py::TestOpenAiCompatGateway::test_chat_completions_housekeeper_passthrough` 等 6 个 | `RuntimeError: default plugin context is not booted; await ensure_default_ctx()` |
| **B. Gateway team factory Observability attribute** | 2 | `test_gateway_team_factory.py::TestGatewaySoloFactory::test_solo_excludes_search_skill_from_g2a_tools`、`test_team_builds_team_from_role_library` | `'InMemoryObservability' object has no attribute 'store'` |
| **C. Architecture / protocols / conventions** | 6 | `test_architecture_conformance.py::test_check_protocol_impl_script_passes`、`test_contracts_purity.py::test_no_behavior_classes_in_contracts`、`test_code_conventions.py::TestNoBannedClassNames` / `TestFileLineCountLimit` / `TestGlossaryTermCoverage` / `TestGlossaryReverseCoverage` | 协议继承检查 / 文件行数 / glossary 词条覆盖 |
| **D. Journal / Trace / scenario coherence** | 4 | `test_journal_preview_boundary.py::test_result_preview_has_no_new_production_readers`、`test_run_http.py::test_post_runs_202_then_live_is_journal`、`test_scenario_standard.py::test_standard_plugins_are_closed_set`、`test_trace_coherence.py::test_phase_spans_carry_actor_identity` | journal v2 envelope / run http / scenario closed set / trace 阶段 span |
| **E. Refactor guards** | 1 | `test_refactor_guards.py::TestLeadWallClockPropagation::test_lead_wall_clock_preserved` | `ImportError: cannot import name 'create_observability'` |

### 11.2 PR-0.5 推迟决策

| 维度 | 原计划（PR-B 拍板）| **当前决策（2026-08-21 user）** |
|---|---|---|
| 范围 | 清零 22 个 pre-existing failure（后实测为 19 个） | **推迟到大重构结束后** |
| 时间 | W2（与 PR-0 并行）| **不占用 PR-0 ~ PR-12 任一周次** |
| PR-1 起步是否阻塞 | 19 个 failure 会拖累 CI | **接受拖累**：PR-1 起就接受 19 个红；新 PR 不引入新失败即可（10.3 黄金法则）|
| 修复窗口 | 大重构结束后 | 大重构结束后（预计 W20 之后），单独立 PR-99 "测试修复专期" |

**§11.3 PR-99 占位**：在大重构周期所有 PR（PR-0 ~ PR-12）完成后，开 PR-99 集中清 19 个 pre-existing failure。优先级低于任何 V 约束实现。

---

## 12. PluginContract 决策与 plugin 作者迁移路径

> **review 中识别的概念漂移**：ADR-0074 §一第 10 条写 "PluginContract 概念完整接受"，§四又写 "不替换 PluginDefinition，作为可选 typed section 并存"。Plan/Tracker 沿用后者。本节是决策收敛。

### 12.1 决策（2026-08-21 user 拍板）

| 选项 | 描述 | 取舍 | **决策** |
|---|---|---|---|
| **A. 完整接受** | PluginContract 立即替代 PluginDefinition；PluginDefinition deprecated | break wire；blast radius 涉及所有 profile / bundle / patch | ❌ 不采纳 |
| **B. 可选并存** | PluginDefinition 保留；PluginContract 作为可选 typed section | 不 break wire；plugin 作者渐进迁移 | **✅ 采纳** |
| **C. 并行 + 6 个月迁移** | PluginDefinition 与 PluginContract 并行 6 个月，之后 PluginDefinition deprecated | 给 plugin 作者明确窗口 | ❌ 不采纳（C 与 B 等价但要求 6 个月 deadline，无人 enforce）|

### 12.2 下游影响：plugin 作者迁移路径

```
Phase 1（PR-2）：PluginDefinition 增加可选 `contract: PluginContract | None` 字段
                    ↓
Phase 2（本计划 PR 期间）：核心插件（repeat_tool_call / stop_rule / decision_gate / perception 等）填写 contract 字段，作为示范
                    ↓
Phase 3（PR-12 + PlanTemplate）：所有 PlanTemplate 实例（RAG / prompt_chain / routing 等）填写 contract 字段
                    ↓
Phase 4（PR-12 后）：lca plugin check 对未填 contract 字段的 plugin 输出 warning
                    ↓
Phase 5（不在本计划范围）：新 ADR 决定是否将 PluginDefinition 全面 deprecated
```

**plugin 作者的最小动作**（PR-2 之后即可选执行）：
```python
from lca.contracts.harness.plugin_api import PluginDefinition, PluginContract

# 之前
PluginDefinition(id=..., provides=[...], requires=[...], setup=...)

# PR-2 之后（可选）
PluginDefinition(
    id=...,
    provides=[...],
    requires=[...],
    setup=...,
    contract=PluginContract(  # ← 新字段，可选
        identity=PluginIdentity(...),
        architecture=ArchitectureContract(slot="think.guard", group="G5"),
        # ...
    ),
)
```

### 12.3 ADR-0074 §一第 10 条补丁说明

> **本节为 ADR-0074 §一第 10 条的概念补丁，由本 tracker 持有；不修改 ADR-0074 原文**。
>
> ADR-0074 §一第 10 条原文 "PluginContract 概念（0069 §六）：9 段...作为可选 typed section 并存" 与 §四的 "不替换 PluginDefinition" 一致——**两处都指向"可选并存"路径**。review 中识别的"完整接受 vs 可选并存"漂移实际不存在；§一第 10 条 "完整接受" 是指**PluginContract 的概念语法被接受**，而非"PluginDefinition 被替换"。
>
> 本补丁消除歧义：**PluginContract 是可选 typed section；PluginDefinition 保留为 PluginManifest 的稳定输入**。

---

## 13. 时间估算（16 → 20 周 + buffer）

> **review 中识别的乐观估算问题**：原 timeline 16 周是 1 人 + 1 reviewer 的 optimistic estimate；考虑 PR-3 / PR-5 / PR-7 / PR-8 的大型改动 + 19 个 pre-existing failure 拖累 + 外部 ADR slippage buffer，实际应为 **20 周**。

### 13.1 调整后的 timeline（20 周 + PR-99 占位）

```
W1       PR-0 测量网
W2       PR-0.5（推迟：见 §11，实际 W2 不占周次）
W3-4     PR-1 ControlSlot + ControlPlan 数据面
W5       PR-2 PluginDefinition.control 可选段
W5.5     PR-2.5 11 关系代数扩展 CapabilityPlan
W6-7     PR-3 CompiledRunPlan + PlanCompiler（前置：PR-2.5 已完成）
W8       PR-4 think.guard / stop.decide 原子化（前置：PR-3 已完成）
W9-10    PR-5 spawn.bind_plan（前置：ADR-0071 已落地；W9-W10 = 2 周而非 1 周）
W11      PR-6 plan_ref × Journal 绑定
W12      PR-7 RunFact / CommandEnvelope 收口（前置：ADR-0073 已落地）
W13      PR-8 ArtifactController（4 状态）
W14      PR-9 Creator 4 面化
W15      PR-10 Golden + 文档 + ADR 状态更新
W16-17   PR-12 PlanTemplate 列表工具 + 关系图谱可视化（2 周而非 1 周）
W18-20   Buffer：预留给 §3.4 外部 ADR slippage + 状态机 property test 调试
W21+     PR-99 占位：清 19 个 pre-existing failure（见 §11）
```

### 13.2 Buffer 分配详解

| Buffer 来源 | 占用周次 | 触发条件 |
|---|---|---|
| ADR-0071 slippage | W8 末 / W9 初 | §3.4 deadline 未达 |
| ADR-0073 slippage | W10 末 / W11 初 | §3.4 deadline 未达 |
| PR-3 PlanCompiler 调试 | W7 末 | plan_hash property test 失败 |
| PR-5 spawn 重写 | W9-W10（2 周而非 1 周）| spawn.py 635 → ~200 行涉及 4 个 sub-composer 接入 |
| PR-8 状态机 property test | W13 末 | 合法/非法迁移覆盖不足 |
| PR-12 关系图谱实现 | W16-W17（2 周而非 1 周）| graph 渲染与 11 关系映射 |

### 13.3 总周次对比

| 维度 | 原计划 | 调整后 |
|---|:-:|:-:|
| 乐观估计 | 16 周 | 20 周 |
| 含 buffer | （未声明）| 20 周（buffer 内嵌）|
| 含 PR-99 | （未声明）| 21+ 周 |

---

## 14. PR-7 architecture test 实现路径决策

> **review 中识别的缺口**：PR-7 "Architecture test 拒绝无 envelope 的 tool call" 的实现路径没明文。本节提前决策。

### 14.1 三种实现路径对比

| 路径 | 实现机制 | 优点 | 缺点 | **决策** |
|---|---|---|---|---|
| **A. AST 静态扫描** | `ast` 模块扫描所有 `Body.execute` 调用点，断言每个调用栈必含 `command_envelope.mint` | 静态、零运行时开销、覆盖广 | 维护成本高；动态 import / 字符串调用漏检 | **✅ 采纳为首选** |
| **B. Mock sandbox runtime hook** | mock sandbox.transport，断言每次调用前 stack 含 mint_envelope | 准确捕捉运行时调用 | 易漏检（mock 不到的代码路径）；维护复杂 | ❌ 不采纳 |
| **C. 装饰器 wrapper + type check** | 在 `act.execute` slot 投稿前强制要求 `CommandEnvelope` 类型注解 | 类型系统保护；mypy 可检查 | 仅在类型层；runtime 不强制 | **✅ 采纳为辅助**（双轨：A 主 + C 辅）|

### 14.2 PR-7 完成判据（architecture test 部分）

| 文件 | 作用 |
|---|---|
| `scripts/check_command_envelope_required.py` | AST 扫描 `lca/layer1_cognitive/body/` 所有 `.py` 文件，断言 `pipeline_safe_executor.py::execute` 调用栈必含 `mint_envelope` 引用；违规时 exit 1 |
| `tests/architecture/test_command_envelope_required.py` | 跑 check 脚本，断言 exit 0 |
| `lca/layer1_cognitive/body/command_envelope.py` | `mint_envelope` 函数，类型注解 `-> CommandEnvelope` |

### 14.3 限制与边界

- AST 扫描**仅扫描 `lca/layer1_cognitive/body/` 与 `lca/plugins/body/`**；其他模块的 tool call 入口（gateway / agent）不在 PR-7 范围
- 动态 `importlib.import_module()` 调用漏检——接受此限制；不在本计划范围
- 字符串 `getattr(obj, "execute")` 调用漏检——同上

---

## 15. V9 LogicAddress 两个集合明文（v3 8/9 群 + ADR-0069 13 群）

> **review 中识别的边界集合缺失**：ADR-0074 V9 LogicAddress 评分依赖两个集合（v3 8/9 群 + 0069 13 群），但**两个集合未明文列在同一处**。本节集中列出。

### 15.1 v3 宪法原语基础集（8/9 群）

来源：[`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`](../design/2026-08-19-cognitive-primitive-constitution-v3.md) §3.2

| 群 | 名称 |
|---|---|
| State | AgentState 的 owner；Reducer 单写 |
| Perceive | 外部事实成为可信 context |
| Think | 候选理解、计划与决策 |
| Gate | 决策的确定性治理 |
| Act | 安全改变外部世界 |
| Memory | 候选 WriteSet、保留策略 |
| Collaboration | 委派、协作、合成 |
| Journal | 事实保真运行账本 |
| Composition | 已有能力如何解析、编译、启动 |

> **8 群 vs 9 群**：v3 宪法 §3.2 实际列出 9 个名词（State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition），ADR-0074 V9 引用 "v3 8/9 群" 即指此 9 项。本节以 9 项为准。

### 15.2 ADR-0069 扩展分类学（13 群）

来源：[`docs/adr/0069-agent-primitive-system-and-declarative-grammar.md`](../adr/0069-agent-primitive-system-and-declarative-grammar.md) §一

| 群 | 名称 | v3.1 §1.1 映射 |
|---|---|---|
| G0 | Constitution & Kernel | (宪法外) |
| G1 | Identity, Intent & Contract | G1 Identity |
| G2 | Spacetime, Environment & Context | G4 Perceive |
| G3 | Facts, State & Knowledge | G3 Facts / G9 Journal |
| G4 | Perception & Grounding | G4 Perceive |
| G5 | Cognition, Models & Planning | G5 Cognition |
| G6 | Decision, Command & Control | G6 Decision |
| G7 | Execution, Tools & Operations | G7 Execution |
| G8 | Collaboration & Organization | G8 Collaboration |
| G9 | Interaction, Transport & Interop | G9 Transport |
| G10 | Composition, Configuration & Runtime Governance | G10 Composition |
| G11 | Creation, Learning & Evolution | G11 Creation |
| G12 | Evidence, Evaluation & Operations | G12 Evidence |

### 15.3 V9 评分的两个对照集合

| 评分维度 | 对照集合 |
|---|---|
| FunctionalGroup 命中已知群 | **§15.1 v3 9 群 ∪ §15.2 ADR-0069 13 群**（去重共 22 个唯一项）|
| ControlSlot 命中已知槽 | ADR-0066 §二 9 槽位（perceive.context / think.guard / act.authorize / act.budget / act.constrain / act.execute / remember.admit / stop.decide / observe.*）|
| Scope 在合法 ScopeGraph | 7 项 scope：release / profile / agent / run / turn / invocation / experiment / device（注：v3.1 §1.1 列表 7 项，ADR-0074 V9 写 8 项含 "invocation"——本节以 7 项为准，详见 §15.4）|
| Evidence descriptor 已登记 | Journal catalog 已登记的 EventDescriptor |

### 15.4 Scope 集合分歧说明

ADR-0074 V9 写 "Scope ∈ {release, profile, agent, run, turn, invocation, experiment, device}（8 个合法 scope）"；v3.1 §1.1 ADR-0069 13 群映射表未列 scope。本节以 ADR-0074 V9 8 项为准（含 invocation），但**在 PR-2 启动时与 user 确认是否合并 invocation → turn**（ADR-0067 §三裁剪已含此合并动议，但 V9 未同步）。

---

## 16. PR-10 Golden Profile 覆盖矩阵

> **review 中识别的覆盖缺失**：PR-10 仅说"标准 agent / team / coding agent 各 1 个"。本节明文覆盖矩阵。

### 16.1 必须覆盖的 Profile 类型

| Profile | 用途 | 验证的 V/CV 约束 | golden 文件位置 |
|---|---|---|---|
| **standard-solo** | 单 agent 标准配置；最简 Configured Agent | V1（控制面）/ V2（plan_hash）/ V3（reducer 单写）/ V8（capability 单调） | `tests/golden/profiles/standard-solo.yaml` |
| **standard-team** | 团队协作（lead + 2 members） | V1（lead 路由 control）/ V11（collaboration 关系）/ V12（team PlanTemplate）| `tests/golden/profiles/standard-team.yaml` |
| **coding-agent** | 编程场景；含 tool heavy | V4（CommandEnvelope 必经 5 闸）/ V7（Creator 4 面）/ V11（execution / delegates / projects 关系）| `tests/golden/profiles/coding-agent.yaml` |
| **control-slot-coverage** | 每个 Control Slot 至少 1 个 entry | V1（全部 9 slot 覆盖） | `tests/golden/profiles/control-slot-coverage.yaml` |
| **11-relations-coverage** | 11 种关系代数每种至少 1 个实例 | V11（11 关系全覆盖） | `tests/golden/profiles/11-relations-coverage.yaml` |
| **patch-priority** | Bundle + Patch 优先级冲突解决 | V2（plan 确定性） | `tests/golden/profiles/patch-priority.yaml` |
| **4-state-artifact** | ArtifactController 4 状态完整迁移 | V6（4 状态封闭）/ V8（artifact grant 单调） | `tests/golden/profiles/4-state-artifact.yaml` |
| **hitl-loop** | Human-in-the-Loop approval | V1（act.authorize + ask_human）/ V12（hitl PlanTemplate） | `tests/golden/profiles/hitl-loop.yaml` |

### 16.2 Golden file 配套

| 类型 | 位置 | 说明 |
|---|---|---|
| Profile YAML | `tests/golden/profiles/*.yaml` | 8 个 profile 各 1 个 |
| ControlPlan JSON | `tests/golden/control_plans/*.json` | 与 profile 一一对应 |
| CompiledRunPlan JSON | `tests/golden/plans/*.json` | 与 profile 一一对应 |
| PlanTemplate YAML | `tests/golden/plan_templates/*.yaml` | 12 个 PlanTemplate 各 1 个 |
| Boot Report | `tests/golden/boot_reports/*.md` | Profile boot 后的诊断报告（人类可读）|

### 16.3 Golden Test 维护约定

- golden 文件以 hash 守护：`hash(golden) == expected_hash`；hash drift 视为 PR break
- 修改 golden 必须 PR 描述里明文声明 "为什么这次 hash 必须变"
- CI 跑 `tests/test_golden_profiles.py` 全集覆盖

---

## 17. PR-5 spawn 重写回滚路径

> **review 中识别的回滚缺失**：PR-5 (spawn.bind_plan) 是 L4 大改（spawn.py 635 → ~200 行），没有回滚路径。本节明文。

### 17.1 三级回滚机制

| 级别 | 触发条件 | 回滚动作 | RTO（恢复时间） |
|:-:|---|---|:-:|
| **L1：本地 revert** | PR-5 自身无法合并（CI 红 / architecture test 不通过） | `git revert <PR-5 commit>` | < 1 小时 |
| **L2：feature flag** | PR-5 合并后发现 runtime regression | `LCA_LEGACY_SPAWN=1` 环境变量启用旧 spawn 路径 | < 1 分钟 |
| **L3：compat adapter** | PR-5 + PR-6 整体需要回滚 | 启用 `LCA_PLAN_COMPAT=1`（PR-3 引入，PR-6 之后扩展到 spawn）| < 5 分钟 |

### 17.2 L1 回滚前置条件

- PR-5 的所有改动必须可被 `git revert` 干净撤销（无 schema migration）
- `_legacy_spawn_objects()` 函数作为 compat 入口保留 ≥ 6 个月（PR-5 落地后）
- 任何对 `RuntimeDeps` 字段的删除必须先标记 deprecated ≥ 1 个 PR

### 17.3 L2 Feature Flag 设计

```python
# lca/layer4_app/spawn.py
async def spawn_agent(spec, *, scope=None):
    if os.environ.get("LCA_LEGACY_SPAWN") == "1":
        return await _legacy_spawn_objects(spec, scope=scope)  # 旧路径
    # 新路径
    return await _bind_plan(...)
```

**flag 启用条件**（user 决策）：
- PR-5 merge 后 7 天内未发现 P0 / P0 / P1 regression → flag 默认 off
- 发现 P0 regression → flag 默认 on，spawn 走旧路径；新路径逐步调试
- 6 个月后 flag 默认删除；旧 `_legacy_spawn_objects()` 删除

### 17.4 L3 Compat 集成

PR-3 引入 `LCA_PLAN_COMPAT=1` 保留 3 个 PR；PR-5 扩展此 flag 到 spawn 路径。删除时间：**W12（PR-8 完成后）**。

---

## 18. 0067 旧 artifact 6 个月迁移映射图

> **review 中识别的迁移缺失**：ADR-0074 裁剪 0067 8 状态机到 4 状态，6 个月兼容期内的旧 artifact 迁移路径没明文。本节补全。

### 18.1 旧 8 状态 → 新 4 状态映射

| 0067 旧状态 | 0074 新状态 | 迁移判定 |
|---|---|---|
| **DRAFT** | **DRAFT** | 直接迁移 |
| **PARSED** | **DRAFT**（子步骤）| PARSED 是 VERIFIED 的子步骤，合并 |
| **DECLARED** | **DRAFT**（子步骤）| DECLARED 是 VERIFIED 的子步骤，合并 |
| **VERIFIED** | **VERIFIED** | 直接迁移 |
| **STAGED** | **ACTIVE**（scope=experiment） | STAGED 等价于 promote(target_scope=experiment)，迁移为 ACTIVE + scope flag |
| **ACTIVE** | **ACTIVE** | 直接迁移 |
| **QUIESCING** | **ACTIVE**（退出协议）| QUIESCING 是 ACTIVE 的退出协议，不是独立状态；迁移时记录为 ACTIVE + retiring_at timestamp |
| **RETIRED** | **RETIRED** | 直接迁移 |
| **ROLLED_BACK** | **RETIRED**（rollback=True） | ROLLED_BACK 是 RETIRED 的子分支，合并 |

### 18.2 迁移执行

- **6 个月兼容期内**：`ArtifactController.migrate_legacy_state(legacy_artifact)` 提供一次性迁移；旧 state 字段保留在 `CapabilityArtifact.legacy_state: str | None`，新 state 字段在 `CapabilityArtifact.state: ArtifactState`
- **6 个月后**：`legacy_state` 字段删除；任何仍在使用旧 state 字段的 artifact 视为已退役

### 18.3 旧 Creator 7 面 → 新 4 面映射

| 0067 旧 Creator 面 | 0074 新 Creator 面 | 迁移判定 |
|---|---|---|
| **inspect** | **inspect** | 直接迁移 |
| **author** | **author** | 直接迁移 |
| **validate** | **validate** | 直接迁移 |
| **stage** | **promote(target_scope=experiment)** | stage = promote(experiment)，软链接 6 个月 |
| **promote** | **promote** | 直接迁移（接受 release scope）|
| **retire** | **promote(rollback=True)** | retire = promote(rollback)，软链接 6 个月 |
| **publish** | **promote(target_scope=release)** | publish = promote(release)，软链接 6 个月 |

### 18.4 Creator 软链接实现

```python
# lca/plugins/creator/faces/_legacy_aliases.py (PR-9)
async def stage(artifact, scope):  # 旧 API
    return await promote(artifact, target_scope="experiment")

async def retire(artifact):  # 旧 API
    return await promote(artifact, rollback=True)

async def publish(artifact):  # 旧 API
    return await promote(artifact, target_scope="release")
```

**6 个月后删除**：`_legacy_aliases.py` 与 `lca-ops creator {stage,retire,publish}` 子命令同步删除。

---

## 19. ADR-0068 横切项 Control Slot 归属

> **review 中识别的归属缺失**：ADR-0068 §三 运行时序图有 3 个横切项（`journal.commit` / `checkpoint` / `safe-boundary`），v3.1 §2 标"为"（横切，非阶段）"，但这些横切项是否每个都需要新增 Control Slot 没明文。本节决策。

### 19.1 三个横切项的归属决策

| 横切项 | 归属决策 | 理由 |
|---|---|---|
| **`journal.commit`** | **不新增 Slot；由 v3 §6 Journal-as-Truth + ADR-0065 承接** | commit 是 Journal 内部协议；不属于任何认知阶段的 Control Slot |
| **`checkpoint`** | **新增 Control Slot：`observe.checkpoint`**（观察口）| checkpoint 是可观察事件，不改写控制结果；挂在 observe.* 下 |
| **`safe-boundary`** | **新增 Control Slot：`act.safe-boundary`**（act.execute 后置闸）| safe-boundary 是 effect dispatch 的最后一道闸；属于 act.constrain 的"物理隔离"层 |

### 19.2 Control Slot 总集（PR-3 完成后）

ADR-0066 §二 9 槽位 + ADR-0074 §三新增 = **11 槽位**：

| # | Slot | 来源 | 阶段归属 |
|--:|---|---|---|
| 1 | `perceive.context` | ADR-0066 §二 | perceive |
| 2 | `think.guard` | ADR-0066 §二 | think |
| 3 | `act.authorize` | ADR-0066 §二 | act |
| 4 | `act.budget` | ADR-0066 §二 | act |
| 5 | `act.constrain` | ADR-0066 §二 | act |
| 6 | `act.execute` | ADR-0066 §二 | act |
| 7 | `remember.admit` | ADR-0066 §二 | memory |
| 8 | `stop.decide` | ADR-0066 §二 | stop |
| 9 | `observe.*` | ADR-0066 §二 | （横切）|
| 10 | **`observe.checkpoint`** | ADR-0074 §三（本节 19.1） | （横切，观察口）|
| 11 | **`act.safe-boundary`** | ADR-0074 §三（本节 19.1） | act.execute 后置闸 |

### 19.3 ADR-0074 补丁说明

> **本节为 ADR-0068 §三 横切项归属的 tracker-side 补丁；不修改 ADR-0068 原文**。
>
> ADR-0068 §三 给出运行时序图含 `journal.commit` / `checkpoint` / `safe-boundary` 三个横切项；v3.1 §2 已声明"为"（横切，非阶段）"。本节进一步明确：`journal.commit` 不增 Slot（v3 §6 承接）；`checkpoint` 挂 `observe.checkpoint`；`safe-boundary` 挂 `act.safe-boundary`。
>
> 实施落地：PR-3 (CompiledRunPlan) 必须把 11 槽位（含本节新增 2 个）都纳入 ControlPlan 编译产物；PR-7 (CommandEnvelope 收口) 必须在 `act.execute` 与 `act.safe-boundary` 之间建立类型化接口。

---

## 20. 文件索引（更新）

> §8 文件索引 + 本节新增引用：

| 文件 | 用途 |
|---|---|
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` | v3 宪法 8/9 群来源（§15.1）|
| `/home/lichao/layered-cognitive-agent/docs/adr/0069-agent-primitive-system-and-declarative-grammar.md` | ADR-0069 13 群来源（§15.2）|
| `/home/lichao/layered-cognitive-agent/docs/adr/0066-declarative-atomic-control-plugins.md` | Control Slot 9 槽位来源（仅 §二设计意图，不读 §"实施序列"——见 §0 P0 声明）|
| `/home/lichao/layered-cognitive-agent/docs/adr/0067-spacetime-runtime-and-governed-creation.md` | 旧 8 状态机 / 7 Creator 面来源（§18 迁移映射）|
| `/home/lichao/layered-cognitive-agent/docs/adr/0068-compiled-plugin-kernel-and-unified-run-plan.md` | 运行时序图横切项来源（§19）|

---

## 21. 修订记录

| 日期 | 关键内容修订 |
|---|---|
| 2026-08-21 | 初版：状态总览 + 5 决策 + PR-0 详情 + Phase 0 完成 |
| 2026-08-21 | §0 P0 声明（ADR-0066 PR 表冲突）+ §3.4 外部 ADR deadline + §10 V/CV 映射 + §11 19 个 failure 分类 + §12 PluginContract 决策 + §13 20 周 timeline + §14 PR-7 arch test + §15 V9 集合明文 + §16 golden 覆盖 + §17 PR-5 回滚 + §18 0067 迁移 + §19 0068 横切项 + 22→19 数字修正 |
| 2026-08-21 | PR-0 完成（`8f8469eb`，4 个 audit + 4 个测试 + lca-ops 4 子命令；47 测试全过；harness 无回归）|
| 2026-08-21 | 切到只在 main 工作：移除 §6 Session 日志 + §9 副本 + 分支列 + agent attribution；新增「ADR 监督范围」段（5 ADR × 30+ 条款实施矩阵）|