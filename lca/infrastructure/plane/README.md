# lca.infrastructure.plane

> 状态：稳定 | 草稿 | 弃用
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
lca/infrastructure/plane. 外部世界：文件、LLM、网络、进程、存储、观测、插件内核。具体职责见各包 docstring；本 README 由脚手架生成，待包负责人补充。

## 2. 不负责
认知决策、阶段编排、组合根

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
lca.contracts,lca.infrastructure

## 6. 禁止依赖
lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway

## 7. 副作用
file:read,file:write,network:openai,log:emit,subprocess:spawn

## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
`PlaneBindingError`, `PlaneBindings`, `PlaneKind`, `PlaneRef`, `PlaneRequest`, `current_bindings`, `current_primary`, `join_under`, `make_sandbox_ref`, `outputs_under`, `path_needs_approval`, `plane_bindings_scope`, `raise_if_out_of_scope`, `ref_of`, `resolve_plane_bindings`, `resolve_plane_path`, `sandbox_ref_from`

