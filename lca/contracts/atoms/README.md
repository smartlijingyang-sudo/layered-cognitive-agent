# lca.contracts.atoms

> 状态：稳定 | 草稿 | 弃用
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
lca/contracts/atoms. 职责见各包 docstring 与 .py 文件注释；本 README 由脚手架生成，等待包负责人补充具体职责描述

## 2. 不负责
实现细节、I/O、配置解析、业务编排

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
lca.contracts

## 6. 禁止依赖
lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins

## 7. 副作用


## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
`NEW_RELATIONS`, `RELATION_GROUP_HINT`, `SCOPE_ALIAS`, `SLOT_PHASE_OWNER`, `V3_TO_0069_MAPPING`, `ControlSlot`, `FunctionalGroup`, `Relation`, `Scope`, `all_group_ids`, `all_relation_values`, `all_scope_values`, `all_slot_values`, `as_phase_label`, `canonical_scope`, `is_cross_cutting`, `parse_functional_group`, `parse_relation`, `parse_scope`, `parse_slot`, `phase_owner`, `validate_relations`, `validate_slot_iterable`

