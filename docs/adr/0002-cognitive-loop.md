# ADR-0002: 认知闭环 perceive→think→act→observe→reflect→update

## 状态
Accepted

## 背景
Agent 的核心行为需要一个可解释的循环结构。业界有两种主流选择：
1. **纯状态机/图编排**（如 LangGraph）——灵活但"为什么这么走"需要额外埋点
2. **纯 ReAct 循环**——简单但缺乏反思和记忆更新环节

## 决定
采用六步认知闭环：

```
perceive → think → act → observe → reflect → update
```

- **perceive**: 记忆检索与状态感知（`MemorySystem.perceive_and_retrieve`）
- **think**: 决策生成（`BrainStrategy.think`）
- **act**: 工具执行或委派（`Body.act`）
- **observe**: 执行结果收集（返回 `Observation`）
- **reflect**: 自我评估（`BrainStrategy.reflect`，返回 `Reflection`）
- **update**: 记忆更新（`MemorySystem.update_multi_level`）

每个 `StructuredDecision` 强制携带 `rationale` 字段，使认知过程结构化可追溯。

Loop 本体保持稳定不变（<25 行），所有策略切换、Prompt 模板、错误恢复通过 Hook 和 StrategyRegistry 注入。

## 放弃的方案
- **纯 ReAct（think→act→observe 三步）**：缺少反思环节，无法支持 Reflexion 等自我改进策略。
- **纯图编排（DAG/状态图）**：灵活但学习曲线陡，且"为什么走这条路径"的解释性不如认知闭环直观。图编排作为 `BrainStrategy` 的一种实现（GraphStrategy）接入，而非替代 Loop 本身。

## 后果
- 正面：认知可解释性内建于循环；策略可切换（ReAct/Plan-Execute/ToT/Reflexion 都是 `BrainStrategy` 的不同实现）。
- 负面：MAP 五模块协作增加单步延迟与 Token 消耗——因此设为可配置，简单任务可用轻量 Strategy 直出决策。

## 补充约束（2026-07-28）

### 横切关注点的接入方式

以下横切关注点**必须**通过可替换组件接入，**不得**直接修改 `_loop` 方法：

| 关注点 | 接入方式 | 组件位置 |
|---|---|---|
| 终止判定 / 输出提取 | `StepOutcomePolicy` 协议 | `lca/contracts/protocols.py` |
| 降级（未知 action → respond/use_tool） | `FallbackDecoratedBody`（Body 装饰器） | `lca/layer1_cognitive/body/` |
| 事件发布（step_completed / action_degraded） | Hook（`make_event_emitting_hook`） | `lca/layer2_runtime/hooks.py` |
| Checkpoint 写入 | `_checkpoint` 私有方法 | `lca/layer2_runtime/runtime_loop.py` |

### CI 门禁

- `_loop` 方法 AST 语句数 ≤ 30（`test_architecture_conformance.py::TestCognitiveLoopSkeleton`）
- `runtime_loop.py` 禁止 import `fallback_handler`、`event_bus` 实现、`contracts.action`（import 白名单测试）
- `HOOK_NAMES` 作为 Loop 唯一对外开放的挂载点，新特性只能以注册 Hook 或实现 `StepOutcomePolicy` / Body 装饰器的方式接入
