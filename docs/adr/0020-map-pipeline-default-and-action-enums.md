# ADR-0020: MAP 默认评估管线深化与领域枚举

Formerly: ADR-0017（编号与 ADR-0017-no-bare-strings-no-any 冲突，重编号为 0020）

## 状态
Accepted

## 背景
ADR-0003 将 MAP 表述为五个可注入模块；默认 `Simple*` 实现为空操作，导致 Debate 等路径在默认配置下失去多轮能力。同时 action / process 等字符串字面量分散，增加漂移风险。

## 决定
1. **默认 MAP 深度表面**为 `CandidateEvaluationPipeline`（`SimpleCandidateEvaluationPipeline` 含基础评分与冲突检测）；五个 MAP Protocol 仍可作为扩展注入点保留。
2. `SimpleConflictMonitor` 默认内容感知：候选 `response_text`/`rationale` 不一致时返回冲突，使 `process="debate"` 默认可多轮。
3. 领域枚举集中于 `lca/contracts/enums.py`（含 `ActionType.STOP` / `ASK_HUMAN`），`ActionCatalog` 与 `ActionType` 对齐为行动语言单一拼写源。
4. 未知 action 通过 `UnregisteredActionError` + `Observation.degraded_from` 一等字段表达降级，禁止错误消息字符串控制流。

## 后果
- 正面：默认路径具备可测的评估/辩论深度；降级与 Action 语言可 AI 导航。
- 负面：严格依赖五个独立 MAP 实现的外部代码需显式注入，不再依赖“空壳默认”。
