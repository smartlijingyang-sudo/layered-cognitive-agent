# ADR-0023: 架构深化——溶解浅模块 + 消除冗余概念

## 状态
Accepted

## 背景
架构审查（`improve-codebase-architecture` skill）识别出 7 个深化机会：模块接口比实现复杂
（浅模块伪装深模块）、并行定义手动同步、半完成的 rename、以及无行为的占位概念。
这些问题各自不大，但累积起来增加了维护者的认知负担，与 ADR-0019 以来的"溶解冗余命名"
方向相悖。

## 决定

### 1. 内联 SimpleCandidateEvaluationPipeline 默认逻辑
`ModularBrain.think()` 现在内联默认 decompose/evaluate 逻辑（返回原始任务 + max confidence
选优 + 内容感知冲突检测）。`evaluation_pipeline` 参数变为可选（`None` = 内联）。
删除 `GuardedCandidateEvaluationPipeline` 装饰器——`install_decision_gate` 直接存储 policy
并在 think() 内联应用。`SimpleCandidateEvaluationPipeline` 保留为可独立测试的参考实现。

### 2. HOOK_NAMES 并入 HookEvent 枚举
删除 L2 `event_emission.py` 中的 `HOOK_NAMES` 字符串列表——`HookEvent` 枚举（contracts）
成为唯一事实源。`assembly.py` 直接迭代 `HookEvent`。同时补齐 `post_perceive` 触发——
原列表中有定义但循环从未触发，与其他阶段的 pre/post 对称不一致。

### 3. 完成 StepOutcome → StopOutcome 重命名 + 删除 loop_judge.py 兼容 shim
将 `StopOutcome`（types.py 中的规范名）传播到 `StopOutcomePolicy` Protocol 及所有实现。
`StepOutcomePolicy` → `StopOutcomePolicy`，`DefaultStepOutcomePolicy` → `DefaultStopOutcomePolicy`。
删除 `__getattr__` 弃用 shim 和 `contracts/loop_judge.py` 兼容模块。

### 4. 删除无行为占位概念
- `AnthropicLLMAdapter`（两个方法均 raise NotImplementedError，工厂从不返回）
- `UnimplementedTransport`（移至 `tests/support/`，原 docstring 声称"用于尚未实现的协议"，
  但 a2a/mcp 已是真实实现）
- `DelegationTool`（定义但全仓库无实例化）
- `build_action_alias_map`（定义但从不调用）
- `GetWeatherTool` 向后兼容别名

### 5. 溶解 BrainFactoryRegistry
`BrainFactoryRegistry` 仅在 `NamedRegistry[BrainFactory]` 上加了中文标签和
`list_strategies()` 别名。直接使用 `NamedRegistry[BrainFactory]`，保留
`get_global_brain_factory_registry()` 单例访问器。

### 6. FallbackActionPolicy 迁至 L1 + 抽取 _coerce_status
`FallbackActionPolicy` 从 L2 (`fallback_handler.py`) 迁至 L1
(`body/fallback_policy.py`)——ADR-0002 的表格本就将 fallback 放在 L1 body。
`_coerce_status` / `_STATUS_MAP` 从 `default_loop_judge.py` 提取到
`lca/contracts/lifecycle.py` 的 `coerce_status()` 函数，与 `TaskStatus` 同居。

### 7. 溶解 SimplePromptManager 到 SimpleReasoner
`SimpleReasoner` 内部管理模板（dict + str.format），不再依赖 `PromptManager`。
删除 `PromptManager` Protocol 和 `SimplePromptManager` 上无用的 `version` 参数。
删除 `reasoner.py` 中未使用的模块级常量（`DEFAULT_REACT_TEMPLATE`、
`HIERARCHICAL_DELEGATE_TEMPLATE`）。

## 放弃的方案
- 保留五占位概念作为"扩展点"——每个都是单实现且零行为，deletion test 确认删除后复杂度
  不扩散
- 为 `PromptManager` 添加版本管理使其"变深"——当前唯一消费者是 `SimpleReasoner`，
  内联更内聚

## 后果
- 正面：contracts 层减少 1 个 Protocol 文件（loop_judge.py）和 1 个 `__getattr__` shim；
  L2 减少 2 个文件（fallback_handler.py、strategy_registry.py 的 BrainFactoryRegistry 类）；
  L0 减少 2 个文件（anthropic_llm.py、delegation_tool.py）；概念表面积净减 ~10 个命名类型
- 负面：`PromptManager` Protocol 保留但默认实现不再被 SimpleBrainFactory 注入——
  需要 PromptManager 的场景需显式注入
- CI 全绿：ruff + mypy + lint-imports + pytest（333 passed）+ vulture（零死代码）
