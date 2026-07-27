# ADR-0003: MAP 五模块 Brain 架构

## 状态
Accepted

## 背景
"Think"这一步如果只是"调 LLM 拿结果"，就无法支撑复杂的认知任务（任务分解、状态预测、冲突检测等）。需要一个模块化的 Brain 设计，让认知过程本身也可组合、可替换。

## 决定
Brain 采用 MAP（Modular Architecture for Problem-solving）五模块设计：

| 模块 | Protocol | 职责 |
|---|---|---|
| TaskDecomposer | `TaskDecomposer` | 将复杂任务分解为子步骤 |
| StatePredictor | `StatePredictor` | 预测执行某动作后的状态变化 |
| StateEvaluator | `StateEvaluator` | 评估预测状态的好坏（打分） |
| ConflictMonitor | `ConflictMonitor` | 检测候选方案间的冲突 |
| TaskCoordinator | `TaskCoordinator` | 在多个候选方案中做最终仲裁 |

加上 `Reasoner`（生成候选方案）和 `Critic`（反思/批评），共同组成 `ModularBrain`。

`ModularBrain` 是 `BrainStrategy` 的一种实现。写新的 Strategy（如 `PlanExecuteStrategy`、`ToTStrategy`）不需要用 MAP 五模块——MAP 只是默认实现，不是唯一路径。

## 放弃的方案
- **单一 Reasoner 直出决策**：简单场景够用，但无法支撑需要"先预测再评估再仲裁"的复杂决策。
- **固定 Pipeline**：五模块的调用顺序不应硬编码——通过 `TaskCoordinator.arbitrate()` 做最终编排，允许不同 Strategy 以不同顺序使用这些模块。

## 后果
- 正面：每个认知子能力可独立替换和测试；新增认知能力（如"类比推理"）只需加一个模块 + 一个 Protocol。
- 负面：五模块协作的 Token 消耗高于单步决策——通过 StrategyRegistry 让简单任务跳过 MAP 直接用轻量 Strategy。
