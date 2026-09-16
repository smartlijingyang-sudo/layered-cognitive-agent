# Agent Note: act.observe 节点拆分 — RunFact commit 独立为 act.observe.commit_fact

Status: implemented

## Problem

拆分前 `act.observe` 一个节点做三件事(评审 §6.3,G-3):receipt 归一化(纯函数)、`effect.observed` RunFact 落库(事实写入)、`should_terminate` 路由决策。三者分属 `AGENTS.md` §2.2 的三个不同类别,混在一个节点里导致:

1. 归一化规则改动与落库 payload 改动落在同一处 diff,review 无法按类别判断影响面。
2. 落库失败与归一化结果互相缠绕:`journal` capability 缺失时静默跳过落库,同时把归一化后的 receipt 照常发出,下游看不出这次观察有没有入账。
3. `should_terminate` 基于归一化后的 `failure_kind` 推导,却和归一化同节点求值,"决策依据什么事实"在代码里不可见。

## Proposal

按类别拆三段单向链,`receipt` 端口逐级透传:

```
act.observe (receipt → receipt)                    # 归一化,纯函数,无副作用
  → act.observe.commit_fact (receipt → receipt)    # RunFact 落库,唯一副作用点
    → act.observe.terminate_decide (receipt → receipt, should_terminate)   # 路由决策
```

- `act.observe.commit_fact` 构造 `RunFact(kind="effect.observed")` 并调用 `journal.commit_fact(...)` 一次;`fact_id = {plan_ref}:{node_ref}:{invocation_id}`,同一 receipt 重复调用产生同一 `fact_id`,去重由 journal capability 负责。
- `act.observe.terminate_decide` 只做 `failure_kind == EXECUTION` 或 `outcome == failed` 的推导,不写事实。
- 三段边在 `bundles/act/act_subgraph.yaml` 中为无条件 `when: true`,不引入路由分叉。

## Ownership

`lca/nodes/act/observe/`。`act.observe` 仍持有归一化闭集 `_FAILURE_KIND_TO_ERROR_REASON` 的消费方(该 map 本身由 PR-4 迁到 `lca/contracts/observability/observability/failure_reason_map.py`)。

## Failure semantics

- `receipt` 端口类型不符:三段都抛 `TypeError`,不降级。
- `journal` capability 不可用:`act.observe.commit_fact` 透传 receipt 且不落库(与拆分前行为一致)。**这是已知的静默降级**,应由 PR-5 连同 graph runtime 取用边界一起改为 fail-loud;本 Note 记录它不在本 PR 范围内。
- 落库抛异常:向上传播,不吞,不重试(节点本身不是副作用执行器,不满足 C10 窄门定义)。

## Timing

三段在一次 act 子图遍历内顺序执行,无并发。`phase.tool.call.end` 由 `act.observe` 退出时发出,`phase.act.fold.end` 移到 `act.observe.terminate_decide` 退出时发出,保证 fold 端点在决策完成后才闭合。

## External consequences

RunFact 落库点唯一化后,spine/deriver 侧 `effect.observed` 事实的 `node_ref` 由 `act.observe` 变为 `act.observe.commit_fact`。依赖该 `node_ref` 字面量的观测消费方需同步(当前 grep 无消费方读此字段)。

## Alternatives considered

1. **保持单节点,内部按顺序调三个私有函数** — 否:节点端口仍同时暴露事实与决策,`declared_outputs` 无法表达"这个端口是决策不是事实",review 面不变。
2. **把 RunFact 落库交给 kernel 在节点退出时统一做** — 否:落库 payload 是 act 域知识(`effect.observed` 的字段形状),交给 kernel 会让 kernel 认知 act 业务,违反 §2.3 控制面/观察面分离。
3. **三段拆成两个节点(commit + decide 合并)** — 否:合并后 `should_terminate` 与事实写入仍在同一节点,问题 3 未解。

## Delete-when

无过渡期。三段结构即终态;若 PR-5 把 journal 取用改为 typed 注入且要求 fail-loud,仅替换 `act.observe.commit_fact` 的 `node_execute` 内部,拓扑不变。
