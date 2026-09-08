# Agent Note: agent_lab 图管理终态 — Profile/Bundle 启用面 + GenericPlanInterpreter 吸收

Status: proposed

## Problem

`agent_lab/` 是 ADR-0206 的信息图原型：自有 YAML SSOT、自有 `compile`/`runner`、自有 `GraphPlugin` 钩子。生产认知图仍由 ADR-0075 declarative phase graph 经 Profile → Bundle → Cordis `@plugin` → `CompiledRunPlan` → `GenericPlanInterpreter` 管理。

两套宿主并存时，读者容易把「像 declarative 一样进插件系统」读成「把 lab runner 整包装进 Cordis」。那会留下第二 Runtime / 第二 Session 事实源，与 ADR-0206 Reject 与 Session 单轨（ADR-0186/0191）冲突。同时若长期把「维持双轨」当成终点，InfoEdgeSpec 语义无法进入 Profile/`why-plugin`/effects 审计宇宙。

需要一条可执行的长期口径：终态进 LCA 插件管理面；过渡期 lab 只做语义沙盒；禁止把 lab 解释器升格为生产第二内核。

## Proposal

锁定长期方向为 ADR-0206 §6 吸收路径，不新开平行宿主 ADR。

1. **管理面终态（与 declarative 同构）**  
   根图 / 阶段子图 / `model_visible` / effect / lineage 的启用、替换、能力归属、effects、审计进入 Profile/Bundle + Cordis Manifest；`why-plugin` / `audit-plugin-shape` 能回答「谁提供了这张图事实」。

2. **执行面终态**  
   `InfoEdgeSpec` 进入 `CompiledRunPlan`；解释器仍是 `GenericPlanInterpreter`（扩展 Binding / Join / 路由递归）。`agent_lab.runtime.runner` 在吸收完成后退役，不作为 Profile 挂载的第二解释器。

3. **工人节点**  
   保持图内 `factory` / Node；不为每个 ant-worker 建 Cordis `@plugin`。进程级插件只承载拓扑/能力提供者与既有 Body/Gate/SafeExecutor/control contribution。

4. **过渡期（当前 fusion-prep）**  
   lab 继续迭代 InfoEdgeSpec 形状与 act 窄门 / session·event 事件形状；节点逻辑优先落可吸收 LCA seam。禁止把整张 lab 图先挂进 `bundles/*.yaml` 假装已融合。lab `GraphPlugin` 仅服务原型横切；delete-when = 吸收 PR 内删除。

5. **切片顺序**（与 0206 P0–P8 对齐，不另立编号宇宙）  
   A 原型收敛 → B `InfoEdge*` 契约进 `lca.contracts` → C Plan 挂载 InfoEdge region → D Interpreter 递归 + P7 降级 phase_graph → E Bundle 提供图事实且 lab runner 退役。

本 Note 不修改 ADR-0075/0206 文本边界；它把「终态 = 吸收进既有插件宇宙与解释器」钉为 fusion-prep 的操作真值。

## Alternatives considered

### Why not 维持双轨到无限期？

双轨让原型迭代便宜，但管理面永久缺 `why-plugin`/effects，且 lab Session singleton 与生产 Session 单轨长期分叉。双轨只允许作为 A–D 过渡，不能当终点。

### Why not 立刻把 agent_lab runner 挂进 Bundle？

会制造第二 Runtime 与第二图真相，缺 delete-when，违反 ADR-0206 Reject 与「compiler projects Bundle facts；interpreter 不认 plugin id」纪律。正确顺序是契约与 Plan 先吸收，再退役 lab 解释器。

### Why not 每个 `@node` 工人一个 Cordis `@plugin`？

工人是图内 factory，不是进程级 capability。逐节点 Manifest 会膨胀 DAG/生命周期，且与 declarative「topology 是数据、executor 是 capability」切法不一致。

### Why not 让 lab GraphPlugin 宇宙与 Cordis 长期并存？

横切双轨会重复 observer / control / session 写入路径。横切应收敛到既有 observer、Session.append、control contribution；lab 钩子只是原型脚手架。

## Acceptance criteria

- 任意读者能从本 Note + ADR-0206 §6 得出同一结论：终态管理面 = Profile/Bundle；终态执行面 = `GenericPlanInterpreter`；lab runner 非生产宿主。
- fusion-prep 分支不新增「lab 图进 Bundle 试跑」路径；若出现，同 PR 必须带退役条件或被拒绝。
- 吸收到达 C 时：`CompiledRunPlan` 可携带 InfoEdge 闭包且 `plan validate` / 相关契约测试 fail-loud。
- 吸收到达 E 时：`python -m agent_lab.run` 不再是生产入口；出厂 Profile 的图启用可经 `why-plugin` 追溯；lab 第二解释器与 lab Session singleton 生产路径为 0。

## Risks

- 过早写 Bundle 包装会固化第二真相；用「禁止 C 之前 Bundle 挂 lab runner」约束。
- 0206 仍为 Proposed、P7 未落地时，生产 SSOT 仍是 0075 phase_graph；本 Note 不授权跳过 P7 直接替换生产拓扑。
- contracts 引入 `InfoEdge*` 若与 harness 反向依赖，须保持 `contracts → …` 单向；实现落 infrastructure/harness，不落 contracts I/O。
