# 03b — 六格正名表（C/I/P = ADR-0206）

> **正名冻结**：`C`=ControlPlan · `I`=InfoEdgeSpec · `P`=ProjectionSpec（不是认知/基础设施/插件）。
> 跨缝未拆 → Delete。`Defer-Add*` = M1 绿前不进 Keep；intervene/plan/delegate/fanout = **边 + sub_spec_ref/端口义务**，禁新节点种类 / `*NodeRuntime`。
> M1：**立刻开** — Delete 双边 SSOT + recovery 进 outer + 本表故障域义务矩阵作附件。

| Keep/Merge/Delete | 层(C/I/P=0206) | 既有缝 | 义务/故障域 | 删除条件 | 业界一句 |
|---|---|---|---|---|---|
| Keep | C | phase.main.outer 六阶段拓扑 + terminal.commit | 控制拓扑唯一脊；边谓词决定下一跳 | 无（闭集控制骨架；仅允许边增补不得第二外环） | runner outer loop |
| Keep | C | Think waterfall → gate.chain（Gate⊂Think） | 意图形成后唯一改写 Decision 的控制门 | 无（Gate 位置不变） | pre-act verdict |
| Keep | C | Act：validate→authorize→envelope→dispatch 路由 | 副作用前控制链；authorize↔envelope 可挂 interrupt 边 | 无（链形状可加边，不得旁路） | tool pre-pipeline |
| Keep | I | effect.execute → Body→SafeExecutor→Sandbox | 世界平面副作用信息边/执行契约；唯一出口 | 无 | tool body |
| Keep | I | act.observe / receipt 折叠（执行结果→结构化回执） | 执行结果信息边归一；供 reflect/Gate 消费 | 与 reflect.observation 合并后仍保留单条 observe 信息缝 | observe normalize |
| Keep | C | Reflect：score + admit_recovery 边谓词 | 恢复准入控制；有界，缺边=编译失败 | 无（谓词可调，缝不删） | replan admit |
| Keep | I | Remember write → memory_receipt | 记忆写入信息边；非控制跳转 | fold 并入 write 后仍保留本缝 | memory flush |
| Keep | C | guard-stack / LoopGuard / ToolGuard（插件挂控制义务） | 单调降权/循环刹车——编译进 ControlPlan 义务，非第七 phase 节点 | 无（永不升格为 phase） | monotonic guards |
| Keep | P | loop_cursor.spine_* / Journal 投影 | 观察面投影；非控制真值；resume 读 Journal 不读 spine | 无（禁平行 checkpointer） | timeline projection |
| Keep | C | ADR-0225：预算/max_turns 在边义务与 Gate，禁 per-node max_visits | 控制预算挂边，不进节点动物园 | 已否决方案发现即删 | max_turns on edges |
| Merge | I | perceive 生产栈 ∪ concept.perceive.* → 单一 perceive 信息管线 | 感知采集/折叠一条信息路径 | delete-when: `rg` 无第二 perceive 工厂 + web-standard parity 绿 + profile 全切 | sense pipeline |
| Merge | C | act.* ∪ concept.action.turn → 单一 act 控制链词汇 | resolve/grant 并入 validate/authorize/envelope | delete-when: `rg concept.action.turn` 零引用 + act 子图 parity 绿 | single tool turn |
| Merge | I | act.observe ∪ reflect.observation.build → concept.observe.normalize | 观测归一单信息缝 | delete-when: 双 builder 零引用 + 契约测绿 | one normalize |
| Merge | I | think.reason.render ∪ concept.prompt.render → 单一 prompt 信息装配 | 模型可见前缀一条装配缝 | delete-when: 重复 render 零引用 | prompt assemble |
| Merge | I | decision.parse ∪ decision.classify → 单一 parse→compose | 决策解析信息缝唯一 | delete-when: 双 parse 零引用 | parse path |
| Merge | I | remember write+fold → 单 write 出 memory_receipt | 写与回执同信息节点 | delete-when: phase.remember.fold 零引用 | write receipt |
| Merge | C | think.route 空 hop → think.route.decide | 路由控制单跳 | delete-when: think.route 节点移除 + 边重挂 | router |
| Merge→Delete | C | agent.run.phase 线性外环 | 第二控制脊 | delete-when: 仅 phase.main.outer 进生产 profile；agent.run.phase 降文档模板或删 | forbid dual runner |
| Delete | C | declarative-phase-graph 边 SSOT | 与 outer YAML 双 ControlPlan | delete-when: outer YAML 含全边（含 recovery/预算）+ `rg declarative-phase-graph` 仅历史 + parity | no dual SSOT |
| Delete | C | declarative-recovery 独挂恢复边 | 恢复控制边游离 | delete-when: reflect→think recovery 边进 outer + 插件边表清空 | recovery on outer |
| Delete | P | 指南 stop.main / 旧文件名投影文案 | 命名漂移污染投影/文档 | delete-when: docs 全改 terminal.commit / outer/phase_main.yaml | rename |
| Delete | C | @graph_node 装饰器路径 | ADR-0228 否决的控制注册旁路 | delete-when: 代码路径清零 + 仅手写 @plugin | hand plugins |
| Delete | C | 外品名 node id / 每计数器一节点 / 第二 Runtime / 平行 checkpointer | 厨房水槽或双驱动 | delete-when: 发现即拒合入；存量清零有 ticket | anti kitchen-sink |
| Defer-Add* | C | outer 边义务：recovery / loop budget / intervene|plan|delegate 的 sub_spec_ref 靶 | 控制边自洽；靶是子图入口不是新节点种类 | M1 绿后才实现；删条件=边义务证明可无独立子图则收回 | edges before nodes |
| Defer-Add* | C | intervene 边（authorize→envelope 之间断）+ Command resume 闭集 | HITL 控制中断；副作用未发才可断；缺 approval_resume_node=fail-closed；超时 abort 禁滑 envelope | M1 附件写死故障域后；无合规 HITL 需求可不上边 | HITL interrupt |
| Defer-Add* | C | act.fanout|join 屏障义务（可先是边/端口义务） | N 路必须 join；部分失败域编译期声明；cursor 未结清禁 advance | M1 义务矩阵后；无并行需求可不上 | parallel barrier |
| Defer-Add* | C/P | budget/compact/repair | 先证编译期边义务→挂 C；否则进 P 插件策略，不进节点 Keep 表 | 证不出边义务 → Delete 节点提案，改插件 | prove-or-plugin |

## M1 附件要点（衡岳三行）

1. **恢复**：`admit_recovery` 有界；无界/缺边 → 编译失败；禁静默跳过。
2. **interrupt**：副作用未发才可断；`Command` 闭集 resume；缺 `approval_resume_node` → fail-closed；超时/放弃 → abort，禁滑进 envelope。
3. **fanout**：N 路必须配 join；部分失败域编译期声明（全停 / 部分承认+审计 / HITL）；禁无 join 的 fanout。

## 相对 03-six-column.md

旧表层定义作废；以本文件为准。
