# lca/contracts/atoms

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `11` 个公开模块 + `60` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：23 个显式 __all__ 条目； 60 个定义符号中，58 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.contracts.atoms].forbidden_dependencies`**:

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
**__init__.py 显式 __all__**:

- `ControlSlot`
- `FunctionalGroup`
- `NEW_RELATIONS`
- `RELATION_GROUP_HINT`
- `Relation`
- `SCOPE_ALIAS`
- `SLOT_PHASE_OWNER`
- `Scope`
- `V3_TO_0069_MAPPING`
- `all_group_ids`
- `all_relation_values`
- `all_scope_values`
- `all_slot_values`
- `as_phase_label`
- `canonical_scope`
- `is_cross_cutting`
- `parse_functional_group`
- `parse_relation`
- `parse_scope`
- `parse_slot`
- `phase_owner`
- `validate_relations`
- `validate_slot_iterable`

**模块清单**:

- `lca/contracts/atoms/artifact_state.py`
- `lca/contracts/atoms/control_slot.py`
- `lca/contracts/atoms/enums.py`
- `lca/contracts/atoms/exhaustive.py`
- `lca/contracts/atoms/functional_group.py`
- `lca/contracts/atoms/ids.py`
- `lca/contracts/atoms/plan_template.py`
- `lca/contracts/atoms/relation.py`
- `lca/contracts/atoms/scope.py`
- `lca/contracts/atoms/semantic_keys.py`
- `lca/contracts/atoms/telemetry.py`
