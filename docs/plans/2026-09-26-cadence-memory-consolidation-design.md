# 基于 Cadence 生物范式的昼夜双轨记忆固化架构设计

**日期**：2026-09-26  
**对应决策**：[ADR-0249](../adr/0249-cadence-inspired-dual-track-memory-consolidation.md)  
**作者/设计者**：Antigravity & 李超  

---

## 1. 目标与范围 (Goals & Boundaries)

### 1.1 核心目标
将 LCA Agent 的记忆机制从“每轮同步进行的大开颅手术”解耦为符合生物学第一性原理的**“快变缓冲与慢变沉淀的自组织共识系统”**：
1. **白天在线快变轨（Day / Fast Path）**：单轮对话毫秒级残差门控（Residual Governor），低残差零开销收敛，高残差（报错/纠偏/强意图）毫秒级追加至短期便签（`EPHEMERAL_FAST`），主会话响应零延迟阻塞。
2. **夜晚离线慢变轨（Night / Consolidation Engine）**：后台/闲时自发做梦（Dreaming），对短期事件按有界切片（Patch）进行确定性聚类、复现统计、冲突消解（Supersede）与晋升（`CONSOLIDATED_SLOW`），经由 C10 窄门安全回填至 `{home}/USER.md`、`{home}/memory/semantic.json` 与技能库。

### 1.2 强制边界 (AP-01 & AP-05)
- **Owns（本模块负责）**：
  - 契约层：`MemoryPatch`、`MemoryRecord`、`ResidualGovernorStrategy` 与 `ConsolidationStrategy`；
  - 基础设施层：`ResidualGovernor` 门控执行器、`MemoryConsolidationEngine` 做梦引擎、四大切片仓储（`Identity` / `Preference` / `Procedural` / `Episodic`）；
  - 窄门适配：通过 `EffectGateway` 统一回填并生成 `revisions/` 快照；
  - 运维与调度：会话空闲钩子与 `lca-ops memory dream <asst_id>` 命令。
- **Does NOT own（严格负向边界，严禁侵入）**：
  - 严格保持认知六相闭集（Invariant C1）：不破坏 `perceive → think → act → reflect → remember`；
  - 严格遵守 Reducer 单写（Invariant C4）：禁止直接向 `AgentState` 属性赋值；
  - 严格遵守事实单轨（Invariant C3）：单轮运行事实依然唯一流向 `Session.append`，不另设平行总线；
  - 不侵入修改前端源码或 vendor 依赖。
- **Autopilot 爆炸半径等级**：`DRAFT`（需完整设计审阅、契约冻结与测试闭环）。

---

## 2. 领域驱动设计（DDD）模型

### 2.1 聚合根与实体
- **`MemoryPatch`（聚合根）**：
  - `patch_id: PatchKind`
  - `entries: List[MemoryRecord]`
  - `version: int`
- **`MemoryRecord`（实体，强类型冻结契约）**：
  - `record_id: str`
  - `dedupe_key: str`
  - `patch_kind: PatchKind (IDENTITY | PREFERENCE | PROCEDURAL | EPISODIC)`
  - `lifecycle_state: LifecycleState (EPHEMERAL_FAST | CANDIDATE | CONSOLIDATED_SLOW | SUPERSEDED)`
  - `content: StructuredFact`
  - `recurrence_count: int`
  - `confidence: float`
  - `provenance: Provenance (source_trace_id, source_type, created_at)`

### 2.2 核心状态机跃迁

```text
               (单轮产生高残差)
[新观察] ──────────────────────────► EPHEMERAL_FAST (快变便签，仅本会话有效)
                                            │
                                            │ (做梦阶段: recurrence >= 2)
                                            ▼
                                        CANDIDATE (候选慢变)
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      │ (做梦阶段: 稳定验证 / 授权)                 │ (新事实发生冲突覆盖)
                      ▼                                           ▼
             CONSOLIDATED_SLOW                               SUPERSEDED
             (慢变真值，持久入库)                           (废弃，移入历史归档)
```

---

## 3. 详细数据流与设计模式

### 3.1 在线快变轨（白天 / Day）
1. 用户输入与工具调用产生结果进入 `reflect` 阶段；
2. 激活 `ResidualGovernor` 门控（策略模式：`ErrorSignalStrategy` / `DirectUserCommandStrategy` / `TypeSafeArousalStrategy`）；
3. 若残差低于阈值，直接收敛结束，单轮耗时 $<2\text{ms}$；
4. 若残差显著，格式化为单条结构化事实，以 `EPHEMERAL_FAST` 状态写入 `{home}/memory/episodes/`，不调用慢速持久化回填。

### 3.2 离线做梦慢变轨（夜晚 / Night）
由 `MemoryConsolidationEngine.dream(asst_id)` 执行管道（Pipeline 模式）：
1. **Cluster & Count**：按 `dedupe_key` 聚类未固化的短程便签，累加 `recurrence_count`；
2. **Conflict Resolution & Supersede**：检测相悖事实（如旧偏好 vs 新偏好），将旧记录置为 `SUPERSEDED`；
3. **Promotion & Narrow-Gate Flush**：达到阈值者晋升为 `CONSOLIDATED_SLOW`，通过 Unit of Work 模式生成 `revisions/` 快照，经 `EffectGateway` 原子写入 `USER.md`、`SOUL.md` 或 `skills/`。

---

## 4. 架构不变量在自动化测试中的断言矩阵 (AP-02)

| 不变量 | 断言内容 | 预期测试文件 |
|---|---|---|
| **C1 认知闭集** | `assert set(graph.nodes) == EXPECTED_SIX_PHASES`，无同步 consolidation 节点 | `tests/contracts/test_memory_phase_purity.py` |
| **C2/C10 执行窄门** | 持久化回填必经 `CommandEnvelope` + `EffectGateway`，且生成前置快照版本 | `tests/infrastructure/memory/test_consolidation_narrow_gate.py` |
| **C3 事实可追溯** | `assert record.provenance.source_trace_id is not None`，拒绝无源记录 | `tests/contracts/test_memory_record_provenance.py` |
| **C4 Reducer 单写** | 静态 AST 检查断言 `infrastructure/memory/` 下严禁写 `state.*` | `tests/architecture/test_memory_no_state_writers.py` |
| **C8 确定性算法** | 固定输入下，聚类排序与覆盖判定 100% 确定可重现 | `tests/infrastructure/memory/test_consolidation_determinism.py` |
| **C13 信息血统闭合**| `assert MemoryRecord.model_config.get("frozen") is True` 强类型禁止 extra | `tests/contracts/test_memory_contracts_frozen.py` |
