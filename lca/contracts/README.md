# lca/contracts

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
数据契约层：Protocol 接口、领域枚举、不可变 dataclass、事件 / wire-level 模型。定义 L1-L5 各层之间的接口边界，任何层都不能跨过 这层去访问具体实现。

## 2. 不负责
实现细节、I/O、配置解析、运行时副作用（这些都是下层的职责）。

## 3. 输入
- 当前包内 `171` 个公开模块 + `1107` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 1107 个定义符号中，1074 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.contracts].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.harness`
- `lca.infrastructure`
- `lca.plugins`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/contracts/action.py`
- `lca/contracts/action_handler.py`
- `lca/contracts/activation.py`
- `lca/contracts/agent.py`
- `lca/contracts/agent.py`
- `lca/contracts/approval.py`
- `lca/contracts/artifact.py`
- `lca/contracts/artifact_closure.py`
- `lca/contracts/artifact_manifest.py`
- `lca/contracts/artifact_state.py`
- `lca/contracts/attachment.py`
- `lca/contracts/budget.py`
- `lca/contracts/cancellation.py`
- `lca/contracts/capabilities.py`
- `lca/contracts/capabilities.py`
- `lca/contracts/capability.py`
- `lca/contracts/capability_gate.py`
- `lca/contracts/capability_plan.py`
- `lca/contracts/casting.py`
- `lca/contracts/cli_debug_command.py`
- `lca/contracts/coding_agent_tools.py`
- `lca/contracts/cognition.py`
- `lca/contracts/cognitive_pipeline.py`
- `lca/contracts/command.py`
- `lca/contracts/command_envelope.py`
- `lca/contracts/compensation.py`
- `lca/contracts/composer.py`
- `lca/contracts/composition.py`
- `lca/contracts/consultation.py`
- `lca/contracts/content_addressable.py`
- ... 共 171 个
