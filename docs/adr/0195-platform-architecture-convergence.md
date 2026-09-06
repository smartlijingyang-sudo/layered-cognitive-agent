# ADR-0195 — LCA 全栈平台架构收敛：Kernel · Transport · Observability · 极端插件化

## 状态

**Implemented (P0–P5 core)**（2026-09-06）。P0–P5 按 [0194-0195-implementation-plan](../specs/0194-0195-implementation-plan.md) 落地;验收见 `tests/architecture/test_0194_0195_acceptance.py`。

**Completion note（2026-09-06）**：

| 已完成 | 待办 / 已知债务 |
|---|---|
| 四段链生产路径（FactGateway → Session → spine → deriver） | Transport carrier/read 终态拆分（P4 部分 PR） |
| platform-readme + architecture-overview 写入路径对齐（P5-04 / P-L8） | `plugins/` legacy 顶层目录删除（P5-10） |
| bundle 无 `spine_reflector_*`；`LCA_FACT_GATEWAY` 已删 | package-org CI 全绿（P5-11） |
| 平台 README 锚点（kernel / loop / transport / plugins） | acceptance **15/15** 通过 |
| loop/graph/nodes 协作图 plugin 迁移；session-runtime canonical `$module` | EventBus compat 退役（O4；delete-when 未达） |
| harness pipeline_loader EnvelopeBus-primary 类型 | — |

**延伸并统摄**：[ADR-0194](0194-cognitive-loop-architecture-convergence.md)（Loop）、[ADR-0115](0115-kernel-transport-boundary.md)（Kernel/Transport）、[ADR-0183](0183-event-bus-framework-ssot.md) / [0186](0186-session-as-event-ssot.md)（事件 SSOT）、[ADR-0190](adr-0190-extreme-plugin-organization.md)（插件物理组织）、[ADR-0191](0191-runtime-loop-dsh-convergence-and-control-plane.md)（四态分离）、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)（图内核）。

**本文档角色**：全项目**元架构**——把 Loop、Kernel、Webserver、Observability、Plugins 五块叠层债务收束为**一套**可读的环状依赖 + **一条**事实链 + **一种**插件粒度。

---

## 0. 决策摘要

LCA 在局部（声明式图、Session 方向、Kernel K1–K8、Transport plugin 化）已有正确决策，但**全栈仍像五张未对齐的地图**：

| 子系统 | 文件规模（粗估） | 核心乱象 |
|---|---|---|
| `lca/plugins/` | 43 顶层域、530+ `.py` | 上帝包（observability/session/phase_graph/transport/runs） |
| Observability | infra 131 + plugins 74 + kernel events 36 | 三平面 + Journal/Session/Spine 三轨；21 reflector；WritableMatrix 僵尸 |
| Transport/webserver | ~99 `.py` | Run 触发 + 装配 + 投影 + 终端化 + 诊断混在一棵树 |
| `lca_kernel/` | 36 `.py` | 职责清晰，但与 `harness/profile`、`plugins/events` 边界仍重叠 |
| Loop | 见 ADR-0194 | Gate 七步/六步分裂、emit 碎片化 |

**终态一句话**：

> **Kernel 编译与启动；Graph 解释执行；Loop 机制事务；Session 追加事实；Cognition 纯算法；Plugins 按 seam 替换；Transport 只承运；Observability 只 fold 与 export。**

```text
                    ┌─────────────────────────────────┐
                    │  Profile / Bundle / Patch (配置) │
                    └───────────────┬─────────────────┘
                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│ G0  lca_kernel/  — K1–K8 boot · plan compile · env · lifecycle   │
│     events/      — yaml SSOT · EnvelopeBus · fold primitives      │
└───────────────────────────────┬───────────────────────────────────┘
                                ▼ CompiledRunPlan + cordis.Context
┌───────────────────────────────────────────────────────────────────┐
│ G0  harness/graph/ + lca/loop/  — MTK · PhaseTransaction · Gateway │
└───────────────────────────────┬───────────────────────────────────┘
                                ▼
         cognition/ (零 I/O)          session/ (append SSOT)
                                ▼
                    *.spine.jsonl  ──fold──►  projections  ──export──►  OTel/UI/SSE
                                ▲
                    transport/ (trigger + wire only, 只读 fold)
```

---

## 1. 第一性原理：三时态 × 五平面

### 1.1 三时态（何时发生）

| 时态 | 问题 | SSOT | 可插件化 |
|---|---|---|---|
| **Compile-time** | 装什么？谁替换谁？ | `ResolvedProfile` → `CompiledRunPlan` | Profile/Bundle/Plugin 声明 |
| **Run-time** | 这一步做什么？ | Phase graph 解释 + Loop 机制 | PhaseExecutor、Gate、Body、Reasoner |
| **Observe-time** | 发生了什么？给人看什么？ | `Session` log → fold | Deriver、Exporter、Subscriber |

**禁止**：Run-time 写第二事实源；Observe-time 触发控制面副作用（C7）。

### 1.2 五平面（何物归属）

| 平面 | 拥有者 | 写入 | 读取 |
|---|---|---|---|
| **Fact** | `lca/session/` | 仅 append | fold 输入 |
| **Control** | `RunCommitter` / Reducer | in-process 投影 | Loop 决策 |
| **Model-visible** | `ModelContextAssembler` | 无（fold） | LLM wire |
| **Mechanism** | `lca_kernel/events/` + `loop/fact_gateway` | 鉴权 + 路由 | 全栈 |
| **Carrier** | `plugins/transport/*` | 无事实 | HTTP/SSE/CLI |

### 1.3 G0 内核闭集（不可插件化的语义）

对齐 ADR-0190 §0.1 Reject 列表，**全栈扩展**：

| G0 组件 | 位置 | 不得插件化的是 |
|---|---|---|
| K1–K2 | `lca_kernel/{source,resolve,plan}.py` | Manifest 校验、Plan 编译语义 |
| K3–K4 | `lca_kernel/{boot,closure}.py` | Fiber 启动顺序、闭包校验 |
| K6–K7 | `lca_kernel/{lifecycle,env}.py` | Fail-loud、env 白名单 |
| Graph MTK | `harness/graph/` | PG-001–008、Effect Gateway 窄门 |
| Fact append | `session/append.py` + `loop/fact_gateway.py` | append-only、鉴权矩阵 |
| Event registry | `lca_kernel/events/config/**/*.yaml` | category ↔ producer 白名单 |
| EnvelopeBus | `lca_kernel/events/bus.py` | 投递语义（实现可换 backend） |

**可插件化**：具体 Reasoner、Tool、Deriver、Exporter、Transport route handler、Assistant 目录。

---

## 2. 目标目录拓扑（全项目）

### 2.1 顶层包（9 + kernel）

```text
lca_kernel/                 # G0 启动 + 事件机制 SSOT
lca/
  contracts/                # 仅类型/Protocol（0015）
  harness/
    graph/                  # MTK：compile · validate · interpret
    composition/            # resolve · boot_products · assembler
  loop/                     # Loop 机制 + FactGateway + README（0194）
  session/                  # append · fold · repair · checkpoint · catalog
  cognition/                # 纯原语，按 v3 概念群分子包
  runtime/                  # CognitiveRuntime 窄入口
  agent/ · application/     # 调度与组合根（0005）
  infrastructure/           # 适配器；观测读路径；禁止 loop 热路径写 journal
  plugins/                  # 仅可替换贡献，<seam>/<manifest-id>/
lobehub-ui/ · vendor/       # 不直接改（AGENTS 禁止）
```

### 2.2 Kernel（`lca_kernel/`）— 保持小、保持纯

| 模块 | 职责 | 禁止 |
|---|---|---|
| `source/resolve/plan` | K1–K2 | transport import |
| `boot/closure/lifespan` | K3–K4 | 业务 plugin id |
| `observability.py` | K5 观测**装配点**（registry bind） | 写 run 事实 |
| `lifecycle/env/hmr` | K6–K8 | HTTP/Starlette |
| `events/` | yaml registry、EnvelopeBus、fold 原语、payload 类型 | 21 个 reflector 类 |

**迁移**：`harness/profile/boot*.py` 中仍留在 harness 的 K3 步骤**收拢**到 `lca_kernel/boot.py` 为唯一入口；harness 只保留 **composition 数据类**。

**人读入口**：[`lca_kernel/README.md`](../../lca_kernel/README.md)

### 2.3 Observability — 从「74+131 文件泥沼」到四段链

**现状三轨**（体检 + ADR-0183 §1.2）：

```text
journal.write  ─┐
Session.append ─┼─► 同一语义多种入口
spine reflector─┘
     └──► *.spine.jsonl ──► deriver 并集 / 重复 fold
```

**终态四段链**（Observer + Strategy 模式）：

```text
Producer (Loop/Kernel/Boot)
    → FactGateway.append / publish_ep
        → Session.append (in-process SSOT)
            → PersistenceObserver → *.spine.jsonl (durable SSOT)
                → Deriver plugins (pure fold) → Projection DTO
                    → Exporter plugins (OTel/Langfuse/SSE/Console)
```

| 段 | 目录 | 模式 | 插件化 |
|---|---|---|---|
| **Registry** | `lca_kernel/events/config/` | SSOT 表 | yaml 扩展，ADR 门禁新 category |
| **Gateway** | `lca/loop/fact_gateway.py` | Facade | G0 |
| **Session** | `lca/session/` | Aggregate + Observer | store backend 可插 |
| **Deriver** | `plugins/observability/deriver/<id>/` | Strategy | 每 deriver 一包 |
| **Exporter** | `plugins/observability/exporter/<id>/` | Strategy | OTel/Langfuse/… |
| **Sink** | `plugins/observability/sink/<id>/` | Observer | 文件/S3/… |

**明确退役**（Observability 专项）：

| ID | 对象 | 替代 |
|---|---|---|
| O1 | `infrastructure/observability/spine/manifest.py` `EXECUTION_POINTS` | `spine.yaml` only |
| O2 | `plugins/events/publishers/spine_reflector_*` (20+) | FactGateway + yaml producer |
| O3 | `plugins/observability/spine/emit_pipeline.py` 生产路径 | SSOT hook only |
| O4 | `EventBus` compat（`lca_kernel/events/bus.py` 旧类） | `EnvelopeBus` |
| O5 | `writable_matrix/coordinator` record stub | LoopCursor WritePort |
| O6 | `journal.write` on loop/tool/LLM 热路径 | Session catalog |
| O7 | infra 与 plugins 双份 spine/deriver | deriver 仅 plugins；infra 留 port |
| O8 | transport 内 `handlers/runs/observability/*` 写投影 | 迁 `transport/read/projection/` 只读 |

**保留在 infrastructure（薄适配，无业务）**：

- `infrastructure/observability/adapters/` — LLM telemetry 装饰（最终只调 FactGateway）
- `infrastructure/observability/diagnostics/` — 只读诊断，不写 run 事实
- `infrastructure/persistence/` — run buffer、fsync

### 2.4 Transport / Webserver — 承运商，非第二 runtime

对齐 ADR-0115：**Transport 不知道 Kernel 内部**，只 consume compiled capabilities。

**现状**：`handlers/runs/` 下 execute / lifecycle / session / terminal / observability / doctor / ingest **七子域混装**，含 loop 装配、RunSession 内存态、journal bind、terminal 物化。

**终态**：

```text
plugins/transport/
  webserver/
    README.md
    server.py · router.py · lifespan_adapter.py · route_register.py
    carrier/                    # 写：触发 run（无认知）
      runs/execute.py           # POST /runs → LoopDriver
      runs/resume.py            # durable recover only
      runs/answer.py            # HIL answer
      assistants/ · composio/   # 域 API
    read/                       # 读：fold 投影（C7 观察面）
      runs/live.py              # SSE/OpenAI stream
      runs/timeline.py
      runs/debug.py
    wire/                       # DTO ↔ contracts（Adapter）
    doctor/                     # 只读诊断（不修复）
```

| 职责 | 必须在 carrier | 必须在 read | 禁止在 transport |
|---|---|---|---|
| 触发 Agent run | ✓ | | |
| bind Session / run scope | ✓ | | |
| 组装 Agent/Team | ✓（调 application） | | 重复 runtime_bindings |
| fold Session → JSON | | ✓ | |
| terminal 物化 | | ✓（读 fold） | 写 AgentState |
| Loop 解释 / Reducer | | | ✓ |
| Session.append | | | ✓（经 Loop） |
| `RunSession` 内存 resume SSOT | | | ✓（ADR-0073） |

**Loop driver**：保留 `plugins/loop_drivers/` 与 `carrier/runs/` 的 Protocol 关系；driver **仅** `Agent.run()` / `Team.run()`，不解析 phase graph。

**人读入口**：[`lca/plugins/transport/README.md`](../../lca/plugins/transport/README.md)

### 2.5 Plugins — 43 顶层域 → Seam 槽位树

**原则**（ADR-0190）：一 Manifest id = 一可卸包；按 **seam** 竖切，不按「同事改过啥」堆目录。

| Seam 族 | 现顶层目录（合并目标） | 目标路径 |
|---|---|---|
| **cognitive** | brain, think, reasoner, critic, body, gate, gates, perceive, memory, sensors | `plugins/cognitive/<group>/<id>/` |
| **loop** | phase_graph, control_contributions, loop_drivers, runtime(reducer) | `plugins/loop/phase/*`, `plugins/loop/control/*` |
| **observability** | observability, events, session(部分) | `plugins/observability/{deriver,exporter,sink}/*` |
| **transport** | transport | `plugins/transport/{webserver,cli,mcp}/*` |
| **domain** | assistant, collaboration, tools, integrations, skill, learning | `plugins/domain/<domain>/<id>/` |
| **composition** | composer, factories, profile, bundles, prompts, roles | `plugins/composition/*` |
| **meta** | seams, providers, act, state, strategies | 保留，≤8 文件/目录 |

**禁止继续存在**：

- `plugins/events/publishers/spine_reflector_*`（O2）
- `plugins/session/` 18 文件 runtime 堆（提升到 `lca/session/`）
- `plugins/phase_graph/` 平铺（迁 `plugins/loop/phase/`）

---

## 3. 设计模式目录（全栈适用）

| 模式 | 应用点 | 反模式（现状） |
|---|---|---|
| **Facade** | `FactGateway`, `lca_kernel.run_kernel`, `CognitiveRuntime.run` | 134 处 `emit_*` |
| **Registry** | yaml EventRegistry, Plugin resolve registry | 硬编码 reflector 类名 |
| **Strategy** | PhaseExecutor, Deriver, Exporter, LoopDriver | transport 内 if/else 模式 |
| **Template Method** | `PhaseExecutionTransaction`, K3 boot 序列 | phase 逻辑复制到 transport |
| **Observer** | `Session.observe` → persistence + anomaly | EmitPipeline 双 enrich |
| **Adapter** | transport/wire, LLM adapters, ModelVisibleHook | DTO 散落 handlers |
| **Builder** | PlanCompiler → CompiledRunPlan | Composer 内联 new |
| **Chain of Responsibility** | DecisionGate 链（仅 Think 内） | Gate 升为 graph node |
| **Command** | `CommandEnvelope` 副作用窄门 | Body 直写 world |
| **State** | LoopCursor 进程内；ControlState fold | WritableMatrix 双写 |
| **Composite** | Phase graph 边与 loop 重入 |  imperative while loop |

---

## 4. SSOT 矩阵（全项目单表）

| Concern | SSOT | 非 SSOT（须退役） |
|---|---|---|
| 装什么插件 | `bundles/*.yaml` + resolve DAG | 代码内 default factory key |
| 怎么跑（图） | `CompiledRunPlan` / bundle topology | Python 硬编码 phase 顺序 |
| Run 事实 | `Session.append` → `*.spine.jsonl` | `journal.write` loop 热路径 |
| EP / category | `lca_kernel/events/config/observability/spine.yaml` | `manifest.py EXECUTION_POINTS` |
| Producer 授权 | yaml `publisher:` 行 | 20 reflector plugin |
| Model wire | `ModelContextAssembler` | `AgentState.history` |
| Control state | `RunCommitter` fold | transport RunSession snapshot |
| Boot 事件 | `lca_kernel/boot.py` journal boot catalog | 分散 boot emit |
| HTTP 路由 | `plugins/transport/webserver/routes_*.py` | 独立 `gateway/` 包 |
| 调试 runbook | `docs/debug/` + `lca-ops` | handler 内隐式修复 |

---

## 5. 全栈退役清单（「垃圾」汇总）

合并 ADR-0194 §4 + 本文 Observability/Transport/Plugins 项：

| 类别 | 项 | delete-when |
|---|---|---|
| 事实 | journal 执行平面 | cognition/loop 零 `append_journal_event` |
| 事实 | inbox 双写 journal+session | sensor 单读 session |
| 观测 | PhaseName.gate | taxonomy 6 phase |
| 观测 | spine_reflector 目录 | FactGateway 100% EP |
| 观测 | EmitPipeline 生产 | hook-less 测试隔离 |
| 观测 | EventBus 别名 | grep 仅剩 EnvelopeBus |
| 观测 | ADR-0065 三平面 doc 中 journal 写入路径描述 | doc 修订 + arch test |
| Transport | RunSession resume 权威 | recover_live_agent 单路径 |
| Transport | runnable 装配 duplicate | 单 application 入口 |
| Transport | terminal 写 state | read-only fold |
| Plugins | 上帝包 >15 py | package-org CI |
| Plugins | plugin→plugin import | lint-imports |
| Cognition | spine/journal import | I-FACT-2 扩展全 cognition |
| Loop | history 作 LLM SSOT | model_context_parity |
| Kernel | harness/boot 双入口 | 单 `run_kernel` |

---

## 6. 分波实施（平台级，与 0194 对齐）

> **完整 PR 清单（113 PR / 8 并行 Lane / ADR 逐条追溯）：** [0194-0195-implementation-plan.md](../specs/0194-0195-implementation-plan.md)

```text
P0 文档与门禁（2 周）
  ├─ 0194 + 0195 ADR Accepted
  ├─ README: lca_kernel, lca/loop, plugins/transport, plugins/README 修订
  ├─ SSOT 矩阵进 AGENTS.md 链接
  └─ arch tests: cognition_no_emit, transport_no_append, obs_no_journal_hotpath

P1 事实单轨（4–6 周）— 与 0194 Wave A 合并
  ├─ FactGateway
  ├─ journal 热路径 → session catalog
  └─ spine.yaml 唯一 EP 表；manifest.py COMPAT 冻结

P2 观测链收敛（4 周）— 与 0194 Wave B 合并
  ├─ reflector → gateway
  ├─ deriver/exporter 分包
  └─ transport observability → read/

P3 Transport 瘦身（4 周）
  ├─ carrier/read 目录切分
  ├─ resume durable 单路径
  └─ terminal/doctor 只读化

P4 插件物理重组（8 周）— 与 0194 Wave C + 0190 合并
  ├─ plugins/loop, plugins/cognitive, plugins/domain
  ├─ session/ 提升
  └─ harness/graph 抽出

P5 文档与遗留删除（2 周）
  ├─ 更新 observability/architecture-overview（journal 路径退役）
  ├─ COMPAT grep CI
  └─ 删空壳目录
```

**并行规则**：P1/P2 可并行；P4 与功能 PR **解耦**（shim + bundle `$module` 渐进）。

---

## 7. CI / 架构门禁（平台扩展）

| ID | 断言 | 范围 |
|---|---|---|
| P-L1 | `lca_kernel/` 零 starlette/uvicorn/transport import | kernel boundary |
| P-L2 | `plugins/transport/` 零 `Session.append`/Reducer/PhaseExecutor | transport-isolation |
| P-L3 | `plugins/transport/carrier/` 零 deriver/fold 实现 | 读写分离 |
| P-L4 | 生产 EP 仅 yaml 登记 category | registry drift test |
| P-L5 | 每 plugin 包 ≤5 .py（8 legacy 预警，12 阻断） | package-org + [cognitive-directory-discipline](../specs/cognitive-directory-discipline.md) |
| P-L6 | 无 `plugins/events/publishers/spine_reflector` 新文件 | O2 |
| P-L7 | Loop 热路径事实经 FactGateway | emit single entry |
| P-L8 | `docs/observability/*` 写入路径描述与 P-L7 一致 | doc test |

---

## 8. 与 ADR-0194 关系

| ADR-0194 | ADR-0195 |
|---|---|
| Loop 六 phase、Gate 正名 | 全栈命名一致 |
| `lca/loop/` + FactGateway | Gateway 调用 kernel EnvelopeBus |
| cognition 零 emit | 全栈 producer 规则 |
| phase 插件竖切 | 纳入 plugins/loop 大重组 |
| — | Kernel K1–K8 收拢 |
| — | Transport carrier/read 分离 |
| — | Observability 四段链 |

**0194 是子系统收敛；0195 是平台壳。** 实施时以 **P0→P1→P2** 为硬依赖，P3–P5 可分批。

---

## 9. 验收（Platform Done）

1. 新人读 4 份 README（kernel / loop / transport / plugins）+ SSOT 矩阵，45 分钟内能画出从 `lca-ops` 到 `*.spine.jsonl` 的全链路。
2. Loop、Tool、LLM 事实**零** journal 热路径写入。
3. Transport carrier 代码**零** fold/deriver；read API **零** append。
4. EP 新增只改 yaml + FactGateway，无新 reflector plugin。
5. `plugins/observability/` 无 >15 文件目录；reflector 目录删除。
6. Kernel boot 单入口 `run_kernel`；harness 无第二 boot 链。
7. package-org + kernel-boundary + transport-isolation CI 全绿（区分既有失败）。

---

## 10. 参考

- [Platform Directory Architecture](../specs/platform-directory-architecture.md)
- [0194 Cognitive Loop Convergence](0194-cognitive-loop-architecture-convergence.md)
- [0115 Kernel/Transport Boundary](0115-kernel-transport-boundary.md)
- [0183 Event Bus Framework](0183-event-bus-framework-ssot.md)
- [0190 Extreme Plugin Organization](adr-0190-extreme-plugin-organization.md)
- [package-organization-discipline](../specs/package-organization-discipline.md)
- 2026-09-06 全栈架构体检（Loop + Emit + Kernel + Transport 探索）
