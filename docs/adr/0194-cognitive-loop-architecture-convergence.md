# ADR-0194 — 认知 Loop 架构收敛：图内核 · 事实单轨 · 极端插件化

## 状态

**Implemented (P0–P5 core)**（2026-09-06）。P0–P5 按 [0194-0195-implementation-plan](../specs/0194-0195-implementation-plan.md) 落地;验收见 `tests/architecture/test_0194_0195_acceptance.py`。

**Completion note（2026-09-06）**：

| 已完成 | 待办 / 已知债务 |
|---|---|
| FactGateway 生产单轨；`LCA_FACT_GATEWAY` 回退开关已删 | P4 插件物理重组（`plugins/` 顶层 legacy 目录，P5-10） |
| 六语义 phase + bundle 指向 `plugins/loop/phase/*` | package-org 全绿或 ADR 豁免登记（P5-11） |
| cognition 零 spine_reflector import；emit single entry (P-L7) | P4 插件物理重组（`plugins/` 顶层 legacy 目录，P5-10） |
| ADR-0169 gate-as-phase 文档 Superseded 注脚（P5-05） | package-org 全绿或 ADR 豁免登记（P5-11） |
| observability 四段链文档（P5-04 / P-L8） | Wave C COMPAT shim 清理（P5-03；delete-when grep 归零） |
| loop/graph/nodes + loop/state SSOT；**`plugins/phase_graph/` 已删除** | EventBus compat 退役（G6） |
| acceptance **15/15** 通过 | `plugins/session/` 整目录删除（阻塞于 runtime 基础设施 lift） |

**延伸**：ADR-0075（声明式阶段图 / MTK）、ADR-0190（极端插件化组织）、ADR-0191（四态分离 / DSH 收敛）、ADR-0192（Fact Plane）、ADR-0183/0186（Session SSOT）、认知原语宪法 v3（六步闭集 + Gate 概念群）。

**部分收敛（本 ADR 落地后已标记 Superseded / 修订的决策面）**：

| 被收敛面 | 原 ADR / 现状 | 本 ADR 处置 |
|---|---|---|
| 观测「第 7 阶段 gate」 | ADR-0169 `PhaseName` 含 `gate`；`phase.gate.fold` 白名单无生产 emit | **退役** gate 为独立 phase；改为 `think.gate.*` 子事件；**0169 已加注脚（P5-05）** |
| Journal 执行平面 | ADR-0063/0096 与 Session 并行 | **退役** cognition 路径上的 `journal.write`；Session catalog 唯一 durable 事实 |
| 20+ `spine_reflector_*` 插件 | ADR-0181 → 0183 迁移态 | **收敛** 为 `FactGateway` + yaml 鉴权矩阵；reflector 降为薄 adapter |
| Phase 逻辑四散 | harness + phase_graph + control_contributions | **共址** 于 `lca/loop/` 人读层 + MTK 留在 harness |
| `AGENTS.md` 七步闭集表述 | gate 与 think 并列 | **修正** 为「六语义 phase；Gate 为 Think 原语子链」 |

---

## 0. 决策摘要

LCA 已具备正确的**骨架**（声明式 phase graph、Session 事实 SSOT 方向、Reducer C4、Effect Gateway C10），但实现仍呈**迁移叠层**：执行 6 步 vs 观测 7 步、Gate 四套入口、emit 134+ 入口、journal 与 Session 双轨、phase 逻辑横切四处、`plugins/` 上帝包膨胀。

本 ADR 锁定**终态拓扑**与**目录宪法**，原则：

1. **图是执行 SSOT** — 一切 iteration、重入、控制槽顺序由 `CompiledRunPlan` 表达；Runtime 只解释图，不认识业务 plugin id。
2. **事实是 Session SSOT** — 唯一 durable append 面；模型可见与控制态均为 fold 投影，禁止反向写事实。
3. **认知原语零 emit** — `cognition/` 只产出 Decision/Observation/Manifest；事实经 Loop 机制层 `FactGateway` 写入。
4. **可替换皆插件、机制不可插件** — 对齐 ADR-0190 Keep/Reject；MTK + FactGateway 语义属 G0。
5. **人读入口单一** — `lca/loop/README.md` 为 Loop 权威导读；新人不再在 transport / harness / plugins 间拼图。

```text
                    ┌─────────────────────────────────────┐
                    │  Profile / Bundle / CompiledRunPlan │  ← 配置 SSOT
                    └──────────────────┬──────────────────┘
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  G0 Graph Kernel (MTK) — harness/graph                           │
│  compile · validate · interpret · govern · effect-dispatch       │
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  G0 Loop Mechanism — lca/loop/                                   │
│  driver · transaction · fact_gateway · phase_registry (读模型)   │
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  lca/cognition/          lca/session/            lca/plugins/
  (纯原语, 零 I/O)         (append/fold/repair)     (按 seam 一包)
        │                       │
        └─────────── FactGateway.append(fact) ──────┘
                                ▼
                    *.spine.jsonl + fold projections
```

---

## 1. 第一性原理：四类状态 × 三层环

### 1.1 四类状态（不可混写，继承 ADR-0191）

| 类别 | 问题 | 拥有者 | 插件可替换？ |
|---|---|---|---|
| **Facts** | 发生了什么？ | `Session.append` | 否（append 语义 G0）；**内容**由插件经 FactGateway 生产 |
| **Model-visible** | LLM 下一轮看到什么？ | `ModelContextAssembler` fold | Deriver 可插拔 |
| **Control** | 能否继续？预算？审批？ | `RunCommitter` fold | Reducer 策略可插拔（ADR-0070） |
| **Ephemeral** | stream/abort 活着吗？ | Loop runtime 进程内 | 不持久化 |

**核心不变量**：任何对象不能同时承担事实源与投影职责（C11/C4 延伸）。

### 1.2 三层环（机制 vs 原语 vs 载体）

| 环 | 职责 | 目录 | 禁止 |
|---|---|---|---|
| **R0 Graph Kernel** | 计划编译、图验证、通用解释、控制槽调度、Effect 窄门 | `lca/harness/graph/`（自 `declarative/` 抽出 MTK 子集） | 业务 plugin id、工具名、LLM 品牌 |
| **R1 Loop Mechanism** | Turn 驱动、phase visit 事务、FactGateway、人读文档 | `lca/loop/` | 具体 Reasoner/Gate/Body 实现 |
| **R2 Cognitive Primitives** | Brain/Body/Memory/Perceive/Gate **算法** | `lca/cognition/<group>/` | Session/Journal/Spine import |
| **R3 Plugins** | Manifest 声明的可替换贡献 | `lca/plugins/<seam>/<id>/` 一 manifest 一包 | 多 seam 上帝包、plugin→plugin import |
| **R4 Carriers** | HTTP/MCP/CLI 触发 run | `lca/plugins/transport/` 等 | 认知编排、Reducer、直接 append |

### 1.3 六步闭集与 Gate 正名（终结文档/代码分裂）

| 层面 | 表述 | 权威 |
|---|---|---|
| **语义 phase（图节点）** | perceive, think, act, reflect, remember, stop | `SemanticPhase` + `bundles/declarative-phase-graph.yaml` |
| **认知原语群（v3 八群之一）** | Gate ⊂ Think | 宪法 v3；`DecisionGate` 链在 `StandardCognitiveThinkPipeline` 内 |
| **声明式控制槽** | `control.think.guard` 等 | ADR-0074 contributions；**读** Gate 事实，非第二套 Gate 实现 |
| **观测** | `think.gate.enforced.v1` 等 catalog 事实；**禁止** `phase.gate.fold` / `PhaseName.gate` | 本 ADR Wave B |

**AGENTS.md 闭集修正**：由 `perceive→think→gate→act…` 改为 **「六语义 phase；Gate 为 Think 原语子链（非 graph node）」**。

---

## 2. 目标目录结构（人读 + 8/10/15）

> 对齐 [package-organization-discipline](../specs/package-organization-discipline.md) 与 ADR-0190。**搬迁是 Phase B；Phase A 先立门禁与 FactGateway，禁止新债。**

### 2.1 顶层业务包（7 → 8，+loop）

```text
lca/
  contracts/          # 仅类型与 Protocol（不变）
  harness/
    graph/              # R0 MTK：compiler, validator, interpreter, governance
    composition/        # Profile resolve, boot 装配（自 declarative/compile 收敛）
  loop/                 # R1 人读入口 + 机制（NEW）
    README.md           # 唯一 Loop 导读：10 行链路 + 各 phase 链接
    driver.py           # DeclarativeRuntimeDriver（自 runtime/ 迁入）
    transaction.py      # PhaseExecutionTransaction
    fact_gateway.py     # 唯一事实生产门面（G0）
    phases/             # PhaseExecutor **注册表与读模型**（非业务实现）
    control/            # 控制 contribution **契约**（非具体 plugin）
  session/              # 自 plugins/session/runtime 提升（R1 事实层）
    append.py, fold.py, repair.py, checkpoint.py, catalog.py
  cognition/            # R2 纯原语（剥离所有 emit import）
    perceive/, think/, gate/, act/, memory/, reflect/
  runtime/              # 窄入口：CognitiveRuntime, bindings, finalizer
  agent/, application/  # 不变
  infrastructure/       # 适配器；观测 **读** session，不 **写** 第二事实源
  plugins/              # R3 仅 **可替换贡献**，按 seam 竖切
    phase/
      perceive/standard/
      think/standard/
      act/standard/
      ...
    gate/
      repeat-tool-call/
      tool-loop-breaker/
    control/
      think-guard/
      act-chain/        # 五 act contribution 合并为一包多 slot
    transport/
      webserver/
    ...
```

### 2.2 插件包命名（一 manifest = 一目录）

```text
lca/plugins/<seam>/<plugin-id>/
  plugin.py             # 唯一 @plugin 入口（AGENTS §5）
  config.py             # Pydantic Config（可选）
  tests/                # 或 tests/plugins/<seam>/test_<id>.py
```

**禁止**：`lca/plugins/phase_graph/` 18 文件平铺、`lca/plugins/observability/` 30 文件、`lca/plugins/events/publishers/spine_reflector_*` 20 域分包。

**spine reflector 收敛**：删除独立 reflector plugin；改为 `FactGateway.publish(category, payload)` + `lca_kernel/events/config/observability/spine.yaml` 鉴权矩阵。Publisher 身份 = yaml 行，非 Python 包树。

### 2.3 `harness/declarative/` 处置

| 现路径 | 目标 | 理由 |
|---|---|---|
| `graph/*`, `execute/interpreter.py`, `lifecycle/phase_transaction.py` | `harness/graph/` + `lca/loop/` | MTK 与机制分离 |
| `compile/*` | `harness/composition/` | 组合根编译，非 loop 热路径 |
| `controls/*` | 机制留 harness；实现迁 `plugins/control/` | 控制 **规则** 可插拔；**调度** 不可 |
| `plugins/phase_graph/*.py` | `plugins/phase/<phase>/<variant>/` | 一 phase executor 一包 |

---

## 3. 核心设计模式

### 3.1 FactGateway（G0 — 替代 134 个 emit 入口）

```python
# lca/loop/fact_gateway.py — Protocol 在 contracts

class FactGateway(Protocol):
    """Loop 机制层唯一事实生产门面。 cognition 不得 import。"""

    def append_catalog(self, event: SessionCatalogEvent, *, actor: str) -> AppendReceipt: ...
    def publish_ep(self, ep: SpineExecutionPoint, payload: Mapping[str, Any], *, actor: str) -> AppendReceipt: ...
    def append_diagnostic(self, diag: DiagnosticFact) -> AppendReceipt | None: ...  # 允许 no-op
```

**规则**：

- 所有 durable 事实经 `FactGateway`；内部统一 `Session.append` → observer → `*.spine.jsonl`。
- `publish_ep` 负责 category 鉴权、I17 enrich、FieldProducer merge（现 `spine_enrich` 逻辑内聚于此）。
- Cognition 返回 **typed DTO**；PhaseExecutor 或 `PhaseFactEmitter` 调 FactGateway（在 `lca/loop/` 或 harness transaction 内）。
- **禁止**：`cognition/*` import `plugins/events/publishers/*`、`append_journal_event`、`record()` 写执行事实。

### 3.2 Graph-as-SSOT（Interpreter + Plan）

- **Strategy**：每个 `PhaseExecutor` 是可替换策略；图边是 **Composite** 迭代结构。
- **Chain of Responsibility**：Gate 链仅在 Think pipeline 内；不得升为 graph node。
- **Template Method**：`PhaseExecutionTransaction` 固定 visit 骨架（prepare → execute → govern → fact → reduce）；子类/插件只填 execute。
- **Observer**：Session observers 驱动 spine 文件、anomaly、projection fold；业务不直接写盘。

### 3.3 RunCommitter（Reducer 演进名，ADR-0191）

- `RunCommitter` = `Reducer` + 可选 control fact append。
- `AgentState.history` **退役**为 model-wire SSOT；rename → `control_turns`（fold 视图）。
- LLM wire **仅** `ModelContextAssembler.assemble(session)`。

### 3.4 ControlPlane 与 ThinkGuard 单一语义

| 组件 | 写 | 读 |
|---|---|---|
| `DecisionGate.enforce()` | `gate.decided.v1` via FactGateway | Session fold（Perceive 下一步 policy facts） |
| `control.think.guard` | `ControlVerdict` 到 phase result（非 durable 事实，除非 catalog 化） | 同 step 的 `gate.decided.v1` |

**收敛**：ThinkGuard **不得**再 fold Session 读 Gate 若 Decision 已携带 rewrite 结果；长期合并为 pipeline 内单次 Gate 链 + governance 只读 Decision artifact（delete-when Wave C）。

---

## 4. 明确退役清单（「垃圾链路」）

| # | 退役对象 | 理由 | delete-when |
|---|---|---|---|
| G1 | `journal.write` 于 cognition / loop 热路径 | 与 Session 双轨 | `rg 'append_journal_event\|bound\.journal' lca/cognition lca/loop` 为 0 |
| G2 | `PhaseName` 含 `"gate"`；`phase.gate.fold` EP | 无生产 emit；误导读者 | taxonomy + cursor 类型移除；grep 0 |
| G3 | `brain.gate.start/end` 无 caller EP | 死白名单 | 从 spine.yaml 删除或 wire 到 think 子 span |
| G4 | 20× `spine_reflector_*` publisher 插件 | 碎片化 | 全量 EP 经 FactGateway；reflector 目录删除 |
| G5 | `EmitPipeline` 生产路径 | SSOT hook 已 bypass | hook-less 测试路径保留至 PR-9 |
| G6 | `EventBus` 平行总线（0183 迁移态） | EnvelopeBus 收敛 | `rg 'EventBus\b' lca/ lca_kernel/` 仅 harness |
| G7 | `WritableMatrix.record_*` stub 链 | cursor WritePort 已替代 | coordinator 删除 stub |
| G8 | `state.extra["manifest_digest"]` | PerceiveProjection SSOT | reducer COMPAT 删除 |
| G9 | Transport `RunSession` 内存 resume 权威 | durable recover | transport 仅调 `recover_live_agent` |
| G10 | `build_tool_history(state.history)` | ADR-0191 | runtime 无 caller |
| G11 | `plugins/phase_graph/` 平铺 | 违反一 manifest 一包 | 迁 `plugins/phase/*` |
| G12 | cognition → spine_reflector import | 层边界 | lint-imports 规则 + grep 0 |

---

## 5. 分波实施（可并行、可验证）

> **完整 PR 清单（113 PR / 8 并行 Lane / ADR 逐条追溯）：** [0194-0195-implementation-plan.md](../specs/0194-0195-implementation-plan.md)

### Wave A — 门禁与门面（4–6 周，不搬家）

| 任务 | 交付 | 验证 |
|---|---|---|
| A1 FactGateway Protocol + 默认实现 | `contracts` + `lca/loop/fact_gateway.py` | `test_fact_gateway_single_entry` |
| A2 cognition emit 禁 import | arch test 扩展 | `test_cognition_no_emit_imports` |
| A3 AGENTS.md + 0169 taxonomy Gate 正名 | 文档 | `verify_doc_slop` |
| A4 journal 热路径迁移清单 | PR 逐文件 | `append_journal_event` cognition 计数递减 |
| A5 `lca/loop/README.md` 导读 | 人读入口 | review 新人 30min 读通 |

### Wave B — 观测收敛（3–4 周）

| 任务 | 交付 | 验证 |
|---|---|---|
| B1 移除 PhaseName.gate | contracts + cursor | OTEL live/replay parity |
| B2 spine reflector → FactGateway | 批量改 publisher call site | EP coverage 测试 |
| B3 退役 EXECUTION_POINTS manifest 副本 | 仅 spine.yaml SSOT | `test_execution_point_coverage` |
| B4 LoopCursor phase fold 与 SemanticPhase 对齐 | 6 phase only | fold deriver 测试 |

### Wave C — 目录重组（6–8 周，与功能 PR 解耦）

| 任务 | 交付 | 验证 |
|---|---|---|
| C1 创建 `lca/loop/`，迁 driver/transaction | import 兼容 shims | 全量 declarative 测试 |
| C2 `plugins/phase_graph` → `plugins/phase/*` | 一 executor 一包 | `audit-plugin-shape` |
| C3 `session/` 提升 | bind/recovery 单路径 | resume integration |
| C4 `control_contributions/act_*` → `act-chain` | 单包多 slot | 替换测试 |
| C5 `harness/graph` 自 declarative 抽出 | MTK 边界测试 | lint-imports |

### Wave D — 状态与 resume 单轨（4 周）

| 任务 | 交付 | 验证 |
|---|---|---|
| D1 history → control_turns；ModelContext 唯一 wire | ADR-0191 闭环 | model_context_parity |
| D2 transport recover_live_agent 唯一 resume | 删 RunSession snapshot 权威 | transport resume 测试 |
| D3 ThinkGuard 读 Decision artifact | 减 Session 双读 | gate integration 测试 |

---

## 6. 与既有 ADR 关系

| ADR | 关系 |
|---|---|
| 0075 MTK | **保留**；graph 子包更纯 |
| 0070 Reducer-as-Plugin | **保留**；RunCommitter 别名 |
| 0190 极端插件化 | **执行**；本 ADR 给目录映射 |
| 0191 四态分离 | **落地**；FactGateway + ModelContext 单轨 |
| 0192 Fact Plane | **加速**；FactGateway = 生产 seam |
| 0186 Session SSOT | **保留** append 语义 |
| 0169 LoopCursor | **修订**；6 phase fold；gate 子事件 |
| 0096 Journal 插件化 | **收窄**；Journal 降为 boot/audit 可选 backend，非 loop 事实 |

---

## 7. 不变量与 CI 门禁（新增）

| ID | 不变量 | 检测 |
|---|---|---|
| L1 | `lca/cognition/` 零 `FactGateway/Session.append/spine_reflector/journal` import | `test_cognition_fact_isolation` |
| L2 | 生产事实只经 `FactGateway` 或 `harness.session.emit`（catalog typed） | `test_emit_single_entry` 扩展 |
| L3 | `SemanticPhase` 与 cursor fold phase 集合相等 | 集合对比测试 |
| L4 | 每 plugin 目录 ≤8 .py（8/10/15） | `check_package_organization` |
| L5 | 无 `phase.gate.fold` 生产 emit | rg + taxonomy test |
| L6 | MTK 无具体 plugin id 字符串 | `test_mtk_no_business_ids` |

---

## 8. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 大规模 import 搬迁破坏 profile | COMPAT shim 保留 1 release；bundle `$module` 渐进改 |
| FactGateway 单点性能 | append 仍 async write-behind（0191 Wave A3 已有） |
| 第三方依赖 reflector plugin id | yaml producer 白名单兼容旧 category |
| 回滚 | Wave A 仅 additive；Wave B 前 env `LCA_FACT_GATEWAY`：未设/`1`/`true` → `DefaultFactGateway`；`0`/`false`/`no`/`off` → catalog 走 `harness.session.emit`、spine 走 `publish_via_session`（delete-when P5-01 / Wave B 完成） |

---

## 9. 验收标准（Overall Done）

1. 新人仅读 `lca/loop/README.md` + `bundles/declarative-phase-graph.yaml` 可在 30 分钟内口述完整一步 visit 链路。
2. cognition 目录 grep 零 emit/journal/spine import。
3. Session.append 为 loop 热路径唯一 durable 写入；journal _plane 不参与 tool/LLM 事实。
4. 观测 phase 集合 = 6，与执行图一致。
5. `plugins/phase_graph/`、`spine_reflector_*` 目录删除或空壳 COMPAT。
6. package-org 无 >15 .py 目录（豁免仅 ADR 登记）。

---

## 10. 参考（体检结论来源）

- 2026-09-06 Agent Loop 架构体检（runtime / phase / emit 四轨）
- [0191 Runtime DSH 收敛](0191-runtime-loop-dsh-convergence-and-control-plane.md)
- [0192 Fact Plane](0192-fact-plane-convergence.md)
- [declarative-phase-graph-spec](../specs/declarative-phase-graph-spec.md)
- [认知原语宪法 v3](../design/2026-08-19-cognitive-primitive-constitution-v3.md)
