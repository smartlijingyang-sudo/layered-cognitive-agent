# lca/plugins/composer

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
Plan-bound Agent 装配根：把已编译的 CompiledRunPlan 绑定为可运行的 AgentGraph / TeamGraph；管理 6 个 cluster 子包（act、think、perceive、collaboration、runtime、composition）之间的依赖闭包，并提供 fixture 默认用于声明式运行时测试。

## 2. 不负责
PluginSpec 声明、Profile 解析、运行时调度（这些由 harness/declarative 和 plugins/seams 负责）。

## 3. 输入
- 当前包内 `28` 个公开模块 + `87` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 87 个定义符号中，78 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/plugins/composer/action_authority.py`
- `lca/plugins/composer/agent_assembly.py`
- `lca/plugins/composer/body_composer.py`
- `lca/plugins/composer/body_provider.py`
- `lca/plugins/composer/brain.py`
- `lca/plugins/composer/brain_composer.py`
- `lca/plugins/composer/brain_provider.py`
- `lca/plugins/composer/capability_resolution.py`
- `lca/plugins/composer/fixture_runtime_adapter.py`
- `lca/plugins/composer/fixture_runtime_defaults.py`
- `lca/plugins/composer/fixture_runtime_factory.py`
- `lca/plugins/composer/fixture_runtime_input.py`
- `lca/plugins/composer/perceive.py`
- `lca/plugins/composer/perceive_composer.py`
- `lca/plugins/composer/perceive_provider.py`
- `lca/plugins/composer/plan_binding.py`
- `lca/plugins/composer/prompt_catalog.py`
- `lca/plugins/composer/runtime_assembly.py`
- `lca/plugins/composer/runtime_binding.py`
- `lca/plugins/composer/runtime_capabilities.py`
- `lca/plugins/composer/runtime_deps.py`
- `lca/plugins/composer/runtime_factory.py`
- `lca/plugins/composer/skill_store.py`
- `lca/plugins/composer/sub_composers.py`
- `lca/plugins/composer/team.py`
- `lca/plugins/composer/team_composer.py`
- `lca/plugins/composer/team_provider.py`
- `lca/plugins/composer/team_transport.py`
