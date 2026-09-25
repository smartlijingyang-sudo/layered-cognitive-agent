# ADR-0249 — 基于 Cadence 生物范式的昼夜双轨记忆固化架构

## 状态

**Accepted — 2026-09-26**

> **一句话**：借鉴 Cadence 局部有界修复与小脑-皮层昼夜节律范式，将 LCA Agent 记忆系统解耦为“白天毫秒级残差门控快记（Fast Path）”与“夜晚离线做梦固化慢变（Night Consolidation）”双轨闭环，通过有界切片（Patch）、DDD 聚合根与受治理 C10 窄门回填，消除单轮阻塞与记忆污染，实现确定性自主演化。

**Extends & Refines**：
- [ADR-0247](0247-agent-memory-knowledge-layer.md)（Agent 记忆知识层：从原文存档到结构化知识）
- [ADR-0244](0244-cognitive-memory-closed-loop-and-sandbox-convergence.md)（认知记忆闭环与沙箱收敛）
- [ADR-0242](0242-assistant-creation-home-runtime.md)（Assistant Home 运行时与画像持久化）
- [ADR-0195](0195-platform-architecture-convergence.md)（SSOT 矩阵与信息血统闭合）

---

## 0. 接任务前 7 问

1. **问题是什么？** 
   现有的 Agent 记忆抽取要么在主对话轮次（`reflect/remember`）中强行调用重量级 LLM，导致单轮高延迟、Token 浪费与幻觉噪音；要么沦为纯静态文件，缺乏类似生物大脑将短期碎片经验在闲时/睡眠时去重、消解冲突并固化为本能慢权重的自演化机制。
2. **受影响的事实或契约？**
   `MemoryPatch` 契约抽象、`MemoryRecord` 增强生命周期状态机、`ResidualGovernorStrategy` 残差门控协议、`ConsolidationStrategy` 固化策略协议、`MemoryConsolidationEngine` 领域服务与 C10 回填窄门。
3. **唯一真值在哪里？**
   - 助理长期知识 SSOT：`{home}/USER.md`、`{home}/SOUL.md`、`{home}/memory/` 及 `{home}/skills/`；
   - 单轮交互事实流 SSOT：`Session.append` 与 `<run_id>.spine.jsonl`；
   - 慢变画像与规则由系统做梦引擎通过受治理通道更新，禁止任意组件直接裸写。
4. **改变哪个边界？**
   - 契约层：新增 `contracts/protocols/memory/` 下 Patch 与 Consolidation 协议；
   - 基础设施层：新增 `infrastructure/memory/consolidation/` 与 `governor/`；
   - 调度面：新增会话空闲钩子与 `lca-ops memory dream` 运维调度通道；
   - 不改变认知六相闭集，不入侵现有认知图。
5. **现有 Protocol / ADR 能否表达？**
   能。作为 ADR-0247 记忆知识层与 ADR-0244 闭环的演进扩展，将生物学昼夜双轨原则引入现有生命周期。
6. **失败、重试、恢复和幂等语义？**
   - 残差门控失败时降级为 DefaultSkip，绝不阻断正常会话；
   - 做梦固化采用工作单元（Unit of Work）与前置快照（Revision Snapshot），写入失败原子回滚；
   - 聚类与冲突消解算法为纯函数，具备绝对确定性（C8）与幂等性。
7. **如何验证？**
   - 契约测试：冻结契约不可变性（C13）；
   - 架构测试：AST 静态扫描确认无直接修改 `AgentState`（C4），六相闭集保持不变（C1）；
   - 单元与场景测试：白天毫秒级快写拦截验证、夜间做梦聚类覆盖（Supersede）与画像回填验证。

---

## 1. 第一性原理与本质剖析

### 1.1 传统 Agent 记忆 vs. Cadence 生物范式

| 维度 | 传统 Transformer / RAG 外挂记忆 | Cadence（生物具身大脑）范式 | LCA 昼夜双轨架构演进 |
|---|---|---|---|
| **学习时机** | 预训练后权重冻结；会话中靠无限拉长 Prompt 上下文（$O(L^2)$ 成本） | 白天快速局部查表，夜晚自发做梦回放（Consolidation） | **昼夜解耦**：白天毫秒级快变追加，夜晚离线批量蒸馏回填 |
| **突触/知识更新** | 全局反向传播，牵一发而动全身，导致灾难性遗忘 | 平衡态对比局部调整，一个 Patch 修复不影响其他区域 | **局部有界 Patch**：四大领域切片隔离，局部消解冲突，互不污染 |
| **单轮监控成本** | 每轮无差别跑全量反思提取或向量检索 | 监工补丁仅苏醒 23.8%，仅在分歧与残差高时激活 | **残差门控（Residual Governor）**：仅在报错、纠偏与强意图时唤醒 |
| **抗污染与可信度** | 用户随意一句话立刻全量注入持久画像 | 必须在睡眠中经受多次重复与一致性验证才晋升慢权重 | **状态机跃迁**：`EPHEMERAL -> CANDIDATE -> CONSOLIDATED` 门槛机制 |

### 1.2 核心本质
记忆不应是“每轮同步进行的大开颅手术”，而应是**“快变缓冲与慢变沉淀的自组织共识系统”**。白天负责低成本捕获分歧，夜晚负责确定性消除矛盾并固化规则。

---

## 2. 领域驱动设计（DDD）与核心契约

### 2.1 领域模型（Domain Models）

```text
                        ┌────────────────────────────────────────────────────────┐
                        │                MemoryPatch (聚合根)                     │
                        │  - patch_id: PatchKind (identity/preference/procedural)│
                        │  - entries: List[MemoryRecord] (实体集合)              │
                        │  - version: int                                        │
                        └───────────────────────────┬────────────────────────────┘
                                                    │ 1 : N
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       MemoryRecord (领域实体)                                          │
│  - record_id: str (UUID)                                                                               │
│  - dedupe_key: str (领域唯一特征键，用于局部覆盖与归一化)                                                  │
│  - patch_kind: PatchKind (IDENTITY | PREFERENCE | PROCEDURAL | EPISODIC)                              │
│  - lifecycle_state: LifecycleState (EPHEMERAL_FAST | CANDIDATE | CONSOLIDATED_SLOW | SUPERSEDED)        │
│  - content: StructuredFact (强类型结构化断言，拒绝自由文本噪音)                                           │
│  - recurrence_count: int (重现与命中频次计数)                                                           │
│  - confidence: float (0.0 ~ 1.0)                                                                       │
│  - provenance: Provenance (来源 trace_id, 触发事件, 证据签名)                                           │
│  - created_at / last_validated_at / expires_at: datetime                                               │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心值对象与枚举
- **`PatchKind`**：
  - `IDENTITY`：用户与助理核心身份设定（对应 `{home}/USER.md` 与 `{home}/SOUL.md`）；
  - `PREFERENCE`：环境、工具偏好与协作习惯（对应 `{home}/memory/semantic.json`）；
  - `PROCEDURAL`：操作踩坑经验与工作流模板（对应 `{home}/skills/` 自演化技能库）；
  - `EPISODIC`：单次运行中发生的具体情景事实（短期上下文事件）。
- **`LifecycleState`**：
  - `EPHEMERAL_FAST`：白天即时记下的快变便签，仅在当前会话生效；
  - `CANDIDATE`：多次重现（Recurrence $\ge 2$）但尚未完全定型的候选慢变；
  - `CONSOLIDATED_SLOW`：经做梦阶段消除冲突并固化的长期慢变真值；
  - `SUPERSEDED`：已被更新的事实覆盖作废，保留作为审计与溯源归档。

---

## 3. 双轨生命周期与设计模式

### 3.1 昼夜节律协作流水线

```text
【白天 · 在线快变轨 (Day / Fast Path)】— 单轮毫秒级、零阻塞
 用户输入 / 工具执行回执
       │
       ▼
 [reflect 阶段] ───► ResidualGovernor（残差门控）
                            │
               ┌────────────┴────────────┐
       [无显著残差]                     [高残差: 报错/纠偏/指令]
               │                                 │
               ▼                                 ▼
         直接收敛结束                     快速结构化为单条事实
                                                 │
                                                 ▼
                                        写入 memory/episodes/
                                       (标记 EPHEMERAL_FAST，耗时<5ms)


【夜晚 · 离线慢变轨 (Night / Consolidation Engine)】— 后台异步做梦、深度消化
 触发源 (Session Idle / 显式 CLI: lca-ops memory dream / 定时 cron)
       │
       ▼
 MemoryConsolidationEngine.dream(asst_id)
       │
 ┌─────┴────────────────────────────────────────────────────────────────┐
 │ 阶段 1：扫描聚类 (Cluster & Count)                                   │
 │   - 读取近期 EPHEMERAL_FAST 与 CANDIDATE 记录                         │
 │   - 按 dedupe_key 进行局部聚合，累加 recurrence_count                │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 阶段 2：局部冲突消解与废除 (Conflict Resolution & Supersede)          │
 │   - 若同一 Patch 出现相悖事实（如“喜欢A” vs “改用B”）                  │
 │   - 最新权威事实胜出，旧记录状态迁移为 SUPERSEDED，生成审计追溯链      │
 ├──────────────────────────────────────────────────────────────────────┤
 │ 阶段 3：晋升慢权重 (Promotion & Narrow-Gate Flush)                   │
 │   - 达标事实（满足频次或用户明确授权）晋升为 CONSOLIDATED_SLOW          │
 │   - 走 C10 窄门（CommandEnvelope + EffectGateway）原子回填：          │
 │       • IdentityPatch    ──► 回填 {home}/USER.md + revisions/       │
 │       • PreferencePatch  ──► 回填 {home}/memory/semantic.json        │
 │       • ProceduralPatch  ──► 生成或修订 {home}/skills/ 技能排错库     │
 └──────────────────────────────────────────────────────────────────────┘
       │
       ▼
 清理已固化短期便签 (Reset Daytime Store at Dawn)
```

### 3.2 落地设计模式
1. **策略模式（Strategy Pattern）**：
   - `ResidualGovernorStrategy`：支持规则检测（`RuleGovernor`）、错误捕获（`ErrorGovernor`）与 TypeSafe 语义探针（`ArousalGovernor`）插拔；
   - `PatchConsolidationStrategy`：四大 Patch 具有差异化的晋升策略（如 `Identity` 遵循权威单次覆盖，`Procedural` 遵循成败对比统计）。
2. **仓储模式（Repository Pattern）**：
   - `MemoryPatchRepository` 封装底层文件读写与行级锁，确保多并发场景下数据完整。
3. **工作单元与快照模式（Unit of Work & Snapshot）**：
   - `ConsolidationTransaction` 在做梦落盘前自动对旧文件在 `revisions/` 中快照存档，确保可逆可溯。

---

## 4. 架构不变量在自动化测试中的硬断言（AP-02）

| 不变量 ID | 不变量要求 | 自动化测试中的硬断言（Deterministic Asserts） | 测试用例文件 |
| :--- | :--- | :--- | :--- |
| **C1 认知闭集** | 认知图六语义阶段不变，不破坏核心循环 | `assert set(graph.nodes) == EXPECTED_SIX_PHASES`<br>断言认知图中未插入任何长耗时的同步 consolidation 节点 | `tests/contracts/test_memory_phase_purity.py` |
| **C2 & C10 执行窄门** | 记忆持久化不得裸调 `open()`，必须受治理且保留审计快照 | `mock_effect_gateway.assert_called_with(...)`<br>断言所有对 `USER.md`、`SOUL.md` 的回填必须经由 `CommandEnvelope` 提交，且 `revisions/` 中必然生成前置快照版本 | `tests/infrastructure/memory/test_consolidation_narrow_gate.py` |
| **C3 事实可追溯** | 任何记忆必须具备确定的证据链 | `assert record.provenance.source_trace_id is not None`<br>断言每条生成的 `MemoryRecord` 都有合法的血统溯源，拒绝无源幽灵记忆 | `tests/contracts/test_memory_record_provenance.py` |
| **C4 Reducer 单写** | 记忆知识层不得反向修改 `AgentState` | 静态 AST 检查断言：`infrastructure/memory/` 目录下所有源码禁止直接向 `state.*` 进行赋值操作 | `tests/architecture/test_memory_no_state_writers.py` |
| **C8 确定性算法** | 做梦聚类、去重与冲突消解在相同输入下必须 100% 可重现 | `assert result_run_1 == result_run_2`<br>断言在固定输入列表下，晋升排序、dedupe_key 分组和 supersede 判定绝对确定，不依赖时间戳随机抖动 | `tests/infrastructure/memory/test_consolidation_determinism.py` |
| **C13 信息血统闭合** | 跨边界实体必须为强类型冻结契约 | `assert MemoryRecord.model_config.get("frozen") is True`<br>`assert MemoryRecord.model_config.get("extra") == "forbid"`<br>严禁未经 typed 契约的数据越界流转 | `tests/contracts/test_memory_contracts_frozen.py` |

---

## 5. 迁移与兼容策略

1. **存储向后兼容**：
   - 现有的 `{home}/memory/semantic.json` 自动作为 `PreferencePatch` 与 `IdentityPatch` 的慢变初始数据载入；
   - 新增 `{home}/memory/episodes/` 目录用于承载白天快速快变日志，未迁移的 Assistant 默认自动初始化。
2. **渐进开启**：
   - 在 profile 配置中支持 `memory.governor.enabled` 与 `memory.consolidation.enabled` 开关；
   - 默认采用规则级残差门控（零外部依赖，极速），可选配 TypeSafe Arousal 探针。
