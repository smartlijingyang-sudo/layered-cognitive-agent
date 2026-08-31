# lca/harness

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `92` 个公开模块 + `593` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 593 个定义符号中，387 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.harness].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/harness/action_authority.py`
- `lca/harness/activation.py`
- `lca/harness/agent_state.py`
- `lca/harness/approval.py`
- `lca/harness/approval_resume.py`
- `lca/harness/assemble.py`
- `lca/harness/assembler.py`
- `lca/harness/audit_control_surface.py`
- `lca/harness/audit_direct_commands.py`
- `lca/harness/audit_hook_attach.py`
- `lca/harness/audit_state_writers.py`
- `lca/harness/authority.py`
- `lca/harness/boot.py`
- `lca/harness/boot_products.py`
- `lca/harness/boot_projection.py`
- `lca/harness/boot_report.py`
- `lca/harness/capability_plan_resolver.py`
- `lca/harness/command_router.py`
- `lca/harness/compiler.py`
- `lca/harness/continuous.py`
- `lca/harness/continuous_queue.py`
- `lca/harness/continuous_serialization.py`
- `lca/harness/continuous_session.py`
- `lca/harness/coordinator.py`
- `lca/harness/declarations.py`
- `lca/harness/diagnose.py`
- `lca/harness/dispatch.py`
- `lca/harness/effect_policy.py`
- `lca/harness/effect_receipt.py`
- `lca/harness/engine.py`
- ... 共 92 个
