# ADR-0002: 认知闭环 perceive→think→act→reflect→remember→stop（v3 supersession）

> **Status (2026-08-19): SUPERSEDED by `2026-08-19-cognitive-primitive-constitution-v3.md`.**
>
> The original "hook-only extension" stance in §"横切关注点的接入方式" and
> §"CI 门禁" below is **废止**.  The v3 constitution replaces the "新特性
> 只能 Hook" rule with a Protocol-first / Reducer-only model.  The CI gates
> ``AST ≤ 30`` / ``HOOK_NAMES`` / "新特性只能 Hook" **were never implemented
> in tree** (实测 ``_loop`` 嵌套语句约 55；no test gates them).  The new
> gates live in ``tests/test_architecture_conformance.py`` (PR1 canary).
>
> **保留** the 六步 cognitive skeleton (now ``perceive → think → act →
> reflect → remember → stop``).  **保留** the 不可变 cognitive-loop set.
> **删除** the implicit "Hook = 默认扩展点" 假设。

## 状态
Superseded — see v3 constitution.

## 背景
Agent 的核心行为需要一个可解释的循环结构。业界有两种主流选择：
1. **纯状态机/图编排**（如 LangGraph）——灵活但"为什么这么走"需要额外埋点
2. **纯 ReAct 循环**——简单但缺乏反思和记忆更新环节

## 决定
采用六步认知闭环（v3 名词对齐：``observe`` → ``reflect``，``update`` → ``remember``）：

```
perceive → think → act → reflect → remember → stop
```

- **perceive**: 记忆检索与状态感知（``PerceiveHub.perceive``）
- **think**: 决策生成（``Brain.think``）；``DecisionGate`` ⊂ Think
- **act**: 工具执行或委派（``Body.act``）；``ExecutionControl`` ⊂ Act
- **reflect**: 自我评估（``Brain.reflect``，返回 ``Reflection``）
- **remember**: 记忆写入（``MemorySystem.propose`` + ``MemoryPolicy.commit``）
- **stop**: 终止判定（``StopRule.decide``，纯函数，PR5）

每个 `StructuredDecision` 强制携带 `rationale` 字段，使认知过程结构化可追溯。

v3 落地（PR1–PR12）：
- ``_loop`` 只编排协议：``perceive_hub.perceive`` / ``brain.think`` / ``body.act`` /
  ``brain.reflect`` / ``memory.propose`` / ``memory_policy.commit`` / ``reducer.apply_*``
  / ``stop_rule.decide``
- ``_emit`` 返回值被忽略（PR5）；PR10 拆除
- ``Reduxer.apply_*`` 是 ``AgentState`` 唯一写入路径（v3 §5.1）
- 控制面不再经 Hook：Hook 仅观察；Gate ⊂ Think；Body 决定审批

## 放弃的方案
- **纯 ReAct（think→act→observe 三步）**：缺少反思环节，无法支持 Reflexion 等自我改进策略。
- **纯图编排（DAG/状态图）**：灵活但学习曲线陡。图编排作为 `BrainStrategy` 的一种实现
  （GraphStrategy）接入，而非替代 Loop 本身。
- **Hook 作为默认扩展面**（v3 废止）：hook 不能改 Decision / State；只能观察。
- **新循环阶段 / 平行 schema**：v3 闭集纪律——见 `2026-08-19-cognitive-primitive-constitution-v3.md`
  §4.3 扩展法。

## 后果
- 正面：认知可解释性内建于循环；策略可切换（ReAct/Plan-Execute/ToT/Reflexion 都是
  ``Brain`` 的不同实现）；插件只换实现，不在循环上开洞。
- 负面：v3 引入 PerceiveHub 协议 + ContextManifest 重建要求 + Reducer 单一写入——迁移期
  dual-write / feature flag（PR2/PR3a）；迁移完成前允许旧路径存在。

## 补充约束

### v3 横切承重系统（替代原 "Hook = 默认扩展面"）

| 系统 | 接入方式 | 组件位置 |
|---|---|---|
| Journal 事实源 | Protocol / 单事件单发射点 | `lca/contracts/models/observability/journal*.py` |
| Context Lifecycle | PerceiveHub + ContextManifest | `lca/layer1_cognitive/perceive_hub.py` |
| Execution Control | ExecutionEnvelope + SafeExecutor | `lca/contracts/models/core/execution.py` |
| Collaboration Control | TeamStrategy + TeamMessage | `lca/layer3_agent/` |
| 终止判定 | ``StopRule``（纯函数，PR5）+ ``StopOutcomePolicy`` | `lca/layer2_runtime/default_stop_rule.py` |
| 降级（未知 action → respond/use_tool） | ``DegradationPolicy``（防腐层） | `lca/layer1_cognitive/brain/degradation.py` |
| 事件发布（step_completed / action_degraded） | Protocol-boundary ``record()``（PR10，not Hook） | `lca/layer2_runtime/event_emission.py` |
| Checkpoint 写入 | ``StateStore`` + ``reducer.apply_*`` | `lca/layer2_runtime/runtime_loop.py` |

### v3 CI 门禁（替代原 "AST ≤ 30 / HOOK_NAMES"）

- `tests/test_architecture_conformance.py` 守住：
  - 控制口纯净（无 listener 改 Decision/State）
  - L1 ↛ harness
  - 闭集纪律（COGNITIVE_PHASES 只减不增）
  - ``loop_warning`` 零写入（PR4）
  - ``_loop`` 调用白名单（perceive/think/act/reflect/propose/commit/apply_*/decide/save）
- `tests/test_journal_reducer_apply_delta_equivalent_to_fold_events.py` 守住
  Hub ↔ Reducer 等价（PR3a）。
- `tests/test_policy_fact_survives_into_next_manifest.py` 守住 PolicyFact 准入
  （PR4 / v3 §5.5）。

### v3 架构命令（PR1–PR12 落地）

1. **PR1** — 冻结 hook 控制面，删死插件（loop_intervention / step_budget）及
   空 `lca.plugins.guards` 兼容包，ADR supersession 前向引用（本 ADR）。
2. **PR2** — Journal 缺口 + ContextManifest dual-write。
3. **PR3a/b/c** — PerceiveHub 协议 + 具名工厂 + Reasoner 切断私有路径。
4. **PR4** — RepeatToolCallGate 替代 loop_intervention；PolicyFact 替代 WM。
5. **PR5** — `_emit` 返回忽略；StopRule 纯函数；L4 `build_cognitive_runtime`。
6. **PR6** — ExecutionEnvelope；审批事件；Gates 只读 Manifest artifact。
7. **PR7** — MemoryPolicy + CompactionPolicy shadow。
8. **PR8** — `/runs` 走 followup；inbox-facts Sensor。
9. **PR9/9b** — TeamMessage + Blackboard。
10. **PR10** — 拆除 `_emit`；StepCompleted/ActionDegraded 移到协议边界。
11. **PR12** — PluginMeta TypedDict 进 contracts；inspect 派生能力图。
12. **PR13/14** — workspace-instructions / skill-catalog Sensor。
