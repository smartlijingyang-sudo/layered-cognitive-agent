# lca.cognition.memory

> 状态：稳定 | 草稿 | 弃用
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
lca/cognition/memory. 认知平面：感知、推理、批评、决策、记忆、协作。具体职责见各包 docstring；本 README 由脚手架生成。

## 2. 不负责
执行副作用、阶段编排、组合根、HTTP 路由

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
lca.contracts,lca.infrastructure,lca.cognition

## 6. 禁止依赖
lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins,gateway

## 7. 副作用
llm:call,log:emit

## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
lca.cognition.memory
