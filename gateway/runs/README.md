# gateway.runs

> 状态：稳定 | 草稿 | 弃用
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
gateway.runs: 运行入口与执行。本 README 由脚手架生成，待包负责人补充具体细节。

## 2. 不负责
跨层职责（详见 spec §3.4 闭集纪律）

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
lca.contracts,gateway

## 6. 禁止依赖
lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins

## 7. 副作用
log:emit,file:read,file:write

## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

