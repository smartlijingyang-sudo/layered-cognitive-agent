# ADR-0022: MAP 管线收敛为单一 CandidateEvaluationPipeline

## 状态
Accepted
Supersedes: ADR-0003

## 背景
ADR-0003 将 Brain 的"Think"步骤定义为五个独立可插拔 Protocol——`TaskDecomposer`、
`StatePredictor`、`StateEvaluator`、`ConflictMonitor`、`TaskCoordinator`，预期每个模块可被
单独替换、单独测试。

落地后的事实是：这五个模块**从未被独立替换过**。`ModularBrain` 在每一条 Think 路径上都
把五者作为一组整体消费；预测、打分、冲突检测、仲裁之间共享 `candidates` 与 `state` 局部
状态，拆成五个 Protocol 带来的是接缝噪音而非插拔收益。`SimpleConflictMonitor` 的内容感知
比较逻辑与 `StateEvaluator`/`TaskCoordinator` 的选优逻辑紧耦合，独立 Protocol 既无第三方实现、
也无单元测试在隔离边界上验证单个模块。

同时 ADR-0020 §1 记载"五个 MAP Protocol 仍可作为扩展注入点保留"、ADR-0004 的 Protocol 清单
列出五者，均与代码现状不符。

## 决定
1. **五模块收敛为单一 Protocol `CandidateEvaluationPipeline`**（`contracts/protocols`），仅暴露
   `decompose(state) -> list[str]` 与 `evaluate(state, candidates) -> Decision` 两个方法——前者吸收
   `TaskDecomposer`，后者吸收 `StatePredictor` + `StateEvaluator` + `ConflictMonitor` + `TaskCoordinator`。
2. **冲突检测内联**为默认实现 `SimpleCandidateEvaluationPipeline` 的私有方法 `_check_conflicts`，
   不再保留独立的 `ConflictMonitor` 适配器；原 `SimpleConflictMonitor` 的内容感知比较逻辑原样迁入。
3. **`ModularBrain` 保留 MAP 风格五阶段编排**（skill route → decompose → generate candidates →
   parse → evaluate），但通过单一 `CandidateEvaluationPipeline` 驱动，而非五个独立 Protocol。
4. **扩展点语义变更**：替换评估行为改为整体替换 `CandidateEvaluationPipeline` 实现（或用
   `GuardedCandidateEvaluationPipeline` 装饰叠加 `DecisionGate` guardrail），不再支持单模块级替换。
5. ADR-0003 被本 ADR 整体取代；ADR-0004 Protocol 清单中"MAP 模块"那一行、ADR-0020 §1
   "五个 MAP Protocol 仍可作为扩展注入点保留"这一具体表述，均以本 ADR 为准。ADR-0004 的
   Protocol-first 可插拔总方针、ADR-0020 的领域枚举与 Action 语言决定不受影响。

## 放弃的方案
- **保留五 Protocol 作为空操作扩展点**：徒增 contracts 层表面积，且"空操作默认 + 可注入深度实现"
  的契约无人兑现——`SimpleCandidateEvaluationPipeline` 已把深度逻辑内联，五 Protocol 形同虚设。
- **改为五个 Protocol 各自注册到 Registry**：进一步放大概念噪音，与 ADR-0019 以来的"溶解冗余
  命名"方向相反。

## 后果
- 正面：contracts 层减少 5 个 Protocol；评估逻辑内聚到单一可测单元；`ModularBrain` 的依赖列表
  从 7 个收紧为 3 个（Reasoner / DecisionParser / CandidateEvaluationPipeline + Critic）。
- 负面：无法再单独替换 MAP 某一个子模块——但这一能力从未被任何实现或测试消费，属可接受损失。
- 迁移：引用旧五 Protocol 名的代码（经审计仅 `docs/` 与历史 ADR）无需改动；新代码统一面向
  `CandidateEvaluationPipeline`。
