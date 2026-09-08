# ADR-0207 — 图编排式认知 Agent 内核：多图协作与编译期信息契约

## 状态

**Superseded by [0206](0206-information-graph-kernel.md) — 2026-09-08**

> 本文原为 0206 的 companion，承载「如何运行」语义（六原语、think-as-call、ContextManifest、CompiledGraphBundle、并行/Join、错误路由边）。复核后发现与 0206 是同一决策的两半：同一根因（ADR-0201 工具结果失明）、同一不变量（G1–G9 ≡ C1–C9）、同一落地切片（P0–P3 ≡ 0206.1–6）。分成两份产生不变量双表与词汇漂移（本文仍引用已退役的 `ControlPlan` 与已占用的 `ProjectionSpec`）。
>
> 因此本文不再单独维护。唯一权威记录是 [0206](0206-information-graph-kernel.md)，本文内容已并入其 §2（两层三视图切法）、§5（运行时语义）、§6（目标架构）、§10（落地阶段）。

**落点去向**（0206）：
- 五图族 → §2「两个可执行平面（控制面 / 信息边）+ 三个派生视图（模型可见 / 效应回执 / 溯源）」
- 六原语（Artifact/Port/Node/Graph/Binding/Fact）→ §1 本体论
- think=graph.call → §5.2
- Context Graph → ContextManifest → §5.3
- Effect→Observation→Context 闭环 → §5.4
- Parallel/Join 与错误路由边 → §5.5 / §5.6
- CompiledGraphBundle / plan_hash recovery → §5.1
- 不变量 G1–G9 → §3 C1–C10