# 多智能体契约层架构 v3 落地 PR 列表

基于文档给出的五层架构、契约拆包方案与第 17 节迁移顺序，拆解为 13 个可独立评审、可独立回滚的 PR。整体分三个阶段推进，严格遵循"低风险先行"原则。

> **落地状态（2026-07-28）**：核心架构思想已按本仓库实际代码落地，见 **ADR-0016**。
> 下列项相对原文做了**有意纠正**（勿按原文机械执行）：
>
> 1. **不**把实现层改名为 `cognition/`/`embodiment/` 等顶层包——保留 ADR-0001 的 `layer0_infra`…`layer4_app`。
> 2. **不**把 Loop 改成 think→…→perceive 九步——保留 ADR-0002 的 `perceive→think→act→reflect→update→judge`，CI 校验该顺序。
> 3. ADR 编号使用 **0016**（0015 已用于 contracts 无行为类）。
> 4. `SharedMemoryStore` 保持 CoALA layer API；新增 `SharedMemoryTool` 包装，而非改成全局 KV。
> 5. `ActionRegistry` 具体类迁出 contracts → L1（符合 ADR-0015）。

## 总览：阶段划分与依赖关系

```
阶段一·契约收口（PR-0~PR-7）        阶段二·实现层落地（PR-8~PR-9）    阶段三·多agent验收（PR-10~PR-12）
PR-0 ADR定稿
  └─ PR-1 契约物理拆包
       ├─ PR-2 CI红线（先立住，此时应免费通过）
       │    └─ PR-3 协议改名+参数序统一
       │         └─ PR-4 L0内部改名三连
       ├─ PR-5 跨层机制类归位
       ├─ PR-6 Turn类型迁移
       └─ PR-7 TeamAssignment/SharedMemoryStore归位
                └─ PR-8 L1~L3实现层目录补齐 ── 依赖 PR-2/3/4/5/6/7
                     └─ PR-9 StepRuntime标准编排 + 15.4 CI + 单体集成测试
                          └─ PR-10 SharedMemoryTool + DefaultTeamEntrypoint + 15.5/15.6 CI
                               └─ PR-11 端到端多agent集成测试（第16节场景）
                                    └─ PR-12 全量验收清单核验与文档收口
```

**关键风险提示（贯穿全局）**：PR-9 与 PR-10 不得并行推进——一旦两条链路同时改动，一旦集成测试红了，无法快速定位是单体循环回归还是团队编排新引入的问题。这是文档 17.10 明确提出的约束，本列表严格保留。

---

## 阶段一：契约层收口

### PR-0：ADR-0015 契约层 v3 架构定稿入库

| 项目 | 内容 |
|---|---|
| **问题分析** | v2 遗留三处结构性缺口（团队编排算法缺失、共享存储访问路径未定义、DELEGATE 与 TeamEntrypoint 边界不清），若不先固化决策记录，后续 PR 评审时容易反复拉扯"为什么这么设计"，拖慢评审效率 |
| **架构方案** | 仅新增 `docs/adr/ADR-0015-contracts-v3.md`，不改动任何代码。内容=本文档 v3 全文的浓缩版：五层依赖方向图、六条硬约束、v2→v3 变更摘要表（文档末尾附表）。作为后续所有 PR description 的引用锚点 |
| **变更范围** | 仅新增 1 个 markdown 文件，零代码改动 |
| **依赖** | 无 |
| **验证方式** | 走文档评审流程（非 CI），需架构负责人 sign-off |
| **效果** | 后续 12 个 PR 的 description 都可以引用 `ADR-0015 §X.Y`，评审时不再需要重复解释设计动机 |
| **风险** | 无（纯文档） |

---

### PR-1：契约层物理拆包（`protocols.py` → `types.py` + `mechanisms.py` + `protocols/`）

| 项目 | 内容 |
|---|---|
| **问题分析** | 现状契约定义可能集中在单文件或结构与五层不对应，违反硬约束一"路径即层次坐标"。`AgentState` 等跨层类型若定义在某一层文件里，会造成"下层反向 import 上层类型"的假象 |
| **架构方案** | 1) 新建 `lca/contracts/types.py`，迁入 `AgentState/RawDecision/Decision/ActionType/Observation/Reflection/SubTask`（`Turn`/`TeamAssignment` 留到 PR-6/PR-7，避免本 PR 承担过多变更）；2) 新建 `lca/contracts/mechanisms.py`，迁入 `NamedRegistryProtocol/TransportRegistryProtocol/EventBus/Hook/HookRegistry`；3) 新建 `lca/contracts/protocols/{infra,cognition,embodiment,memory,runtime,agent,orchestration}.py` 七个文件，按层拆分现有协议定义；4) `protocols/__init__.py` 做**全量 re-export**，保证 `from lca.contracts.protocols import X` 全仓库零改动 |
| **变更范围** | `lca/contracts/*.py`（新增/移动），不改任何调用方代码 |
| **依赖** | PR-0 |
| **迁移验证** | 1) 全仓库 `grep -r "from lca.contracts" ` 确认无人直接 import 子文件路径（除 `protocols/__init__.py` 自身）；2) 跑全量单测，预期零失败（这一步是纯搬迁，行为不应有任何变化）；3) `python -c "from lca.contracts.protocols import *"` 能成功导入且 `__all__` 与旧导出符号集合做差集比对，差集为空 |
| **效果** | 目录树与五层架构第一次产生物理对应关系；后续任何"这是哪一层契约"的疑问可以直接靠路径回答，无需读代码 |
| **风险与回滚** | 风险极低（无行为变更，纯文件移动）。回滚方式：`git revert` 单个 commit 即可，不影响其他模块 |

---

### PR-2：CI 红线首批落地（分层依赖 + 签名顺序 + 命名黑名单）

| 项目 | 内容 |
|---|---|
| **问题分析** | 硬约束四"约定要能被 CI 拦下来"——如果规则只停留在文档，团队默契会随人员流动衰减。必须在真正开始做实质性改名/迁移之前先把红线立住，这样后续每一个 PR 都能立刻验证自己是否符合规范，而不是最后集中补测 |
| **架构方案** | 落地文档 15.1/15.2/15.3 三个 CI 脚本：1) `tools/ci/check_state_first_param.py`——AST 扫描 `contracts/protocols/**` 与 `mechanisms.py`，凡签名含 `AgentState` 标注的方法，首个非 self 参数必须命名为 `state`；2) `.importlinter` 配置 `layered-architecture` 契约，五层单向依赖，显式豁免 `mechanisms.py`/`types.py`；3) `tools/ci/check_handler_naming.py`——全仓库禁用 `class .*Handler` 命名 |
| **变更范围** | `tools/ci/*.py`（新增）、`.importlinter`（新增）、CI pipeline 配置（新增三个 job） |
| **依赖** | PR-1（AST 扫描路径依赖 `protocols/` 包已存在） |
| **迁移验证** | **关键验证点**：三条规则首次跑起来时必须**全部免费通过**（因为 PR-1 只是物理搬迁，未改动任何签名/命名）。如果这一步跑不过，说明现状代码本身已经违反约定，需要先在本 PR 内顺手修掉，再合入 CI gate。跑通后把三个 job 标记为 required check，此后任何 PR 都会被自动拦截 |
| **效果** | 从这个 PR 开始，"参数顺序错误""层间反向依赖""引入 XxxHandler 命名"这三类问题不再依赖 code review 肉眼发现，而是 CI 红叉直接拦截 |
| **风险与回滚** | 风险：如果历史代码里存在大量违规命名/依赖，可能导致本 PR 被迫夹带大量修复，建议如果违规点 >20 处则拆分成"先修复"和"后立规则"两个子 PR。回滚：直接移除 CI job 配置，不影响业务代码 |

---

### PR-3（配 ADR-0016）：协议改名与参数序统一

| 项目 | 内容 |
|---|---|
| **问题分析** | 历史命名可能存在 `ActionHandler`/`FallbackHandler`/`RegistryProtocol` 等不符合新约定的类名，且各协议方法参数顺序不统一，违反硬约束二"签名即契约" |
| **架构方案** | `ActionHandler → ActionOperation`、`FallbackHandler → FallbackPolicy`、`RegistryProtocol → NamedRegistryProtocol`；全部协议方法参数序统一为 `(self, state, decision, ...)`——`state` 恒为第一个非 self 参数。同步更新 `protocols/__init__.py` 的 `__all__` 导出列表 |
| **变更范围** | `lca/contracts/protocols/embodiment.py`、`mechanisms.py`，以及全仓库对这几个类名的引用点 |
| **依赖** | PR-2（改名后立刻能被 15.1/15.3 两条 CI 规则验证，不会出现"改了但没人知道对不对"的情况） |
| **迁移验证** | 1) 全局 `grep` 确认旧类名零残留（`ActionHandler`/`FallbackHandler`/`RegistryProtocol` 三个词全仓库搜索为空，`RegistryProtocol` 需排除 `NamedRegistryProtocol`/`TransportRegistryProtocol` 子串误伤）；2) CI 15.1/15.3 两条 job 必须转绿；3) 单开 ADR-0016 记录改名理由，供未来"为什么叫这个名字"的追溯 |
| **效果** | 契约层类名与参数顺序第一次做到"签名可预测"——任何新协议只要看到 `AgentState` 类型标注就知道第一参数是什么，降低新人上手/评审心智负担 |
| **风险与回滚** | 中等风险：改名是破坏性变更，若有外部依赖方直接 import 旧类名会报错。建议保留一版 deprecated alias（`ActionHandler = ActionOperation` 加 DeprecationWarning）过渡一个发布周期后再删除。回滚：`git revert`，alias 兜底 |

---

### PR-4：L0 内部改名三连（纯物理搬迁）

| 项目 | 内容 |
|---|---|
| **问题分析** | `layer0_infra/` 内部子包命名可能与"单协议·多后端型 / 协议族·扩展方向型"两种命名判据不一致，如 `registry.py`、`tool_protocol/`、`state_mgmt/` 等旧路径不能一眼看出对应哪个协议 |
| **架构方案** | `registry.py → component_registry.py`、`tool_protocol/ → tools/`、`state_mgmt/ → state_store/`，仅做路径重命名，不改动任何类实现逻辑。同步在 `layer0_infra/__init__.py` 写入协议→子包→内置实现的映射表（文档第 12 节表格） |
| **变更范围** | `lca/layer0_infra/` 目录结构、`__init__.py` 文档字符串 |
| **依赖** | PR-3（先完成协议改名，避免 L0 侧改名和契约层改名交叉产生大范围冲突） |
| **迁移验证** | 1) `import-linter` 15.2 规则转绿；2) 全量单测零失败（纯搬迁不应影响任何行为）；3) 人工核对 `__init__.py` 映射表与实际目录结构逐行对应 |
| **效果** | L0 目录第一次做到"只看路径猜对协议"，与契约层的路径对应关系形成闭环 |
| **风险与回滚** | 低风险（纯路径搬迁）。回滚：`git mv` 逆操作 |

---

### PR-5：跨层机制类归位

| 项目 | 内容 |
|---|---|
| **问题分析** | `EventBus`/`Hook`/`HookRegistry` 若散落在各业务层文件里，会让读者误以为它们是某一层的业务协议，实际上它们"不产生业务认知语义，只负责挂载/触发/查找"，应该跨层共用 |
| **架构方案** | 把散落的 `EventBus`/`Hook`/`HookRegistry` 收进 `contracts/mechanisms.py`；`PromptManager` 挪进 `contracts/protocols/cognition.py`（横切工具，不占据链路骨架步骤位）。同步补齐文档第 3 节的"三者边界判定表"docstring，固化到 `mechanisms.py` 顶部注释 |
| **变更范围** | `lca/contracts/mechanisms.py`、`lca/contracts/protocols/cognition.py`、各业务层中原本内联定义这些机制的位置（删除） |
| **依赖** | PR-1 |
| **迁移验证** | 1) `protocols/` 包内搜索 `Registry`/`EventBus`/`Hook` 关键字应零命中（对应第 18 节验收标准）；2) 全量单测零失败 |
| **效果** | `mechanisms.py` 第一次成为"纯机制"文件，`protocols/` 包第一次成为"纯业务契约"文件，边界不再靠人肉核对 |
| **风险与回滚** | 低风险。回滚：`git revert` |

---

### PR-6：Turn 类型迁移与 MemorySystem 两阶段写入改造

| 项目 | 内容 |
|---|---|
| **问题分析** | 若 `AgentState.history` 当前存的是裸 `Observation`，`Reasoner.think` 在下一步就看不到"自己上次怎么想的"（决策+复盘），只能看到"发生了什么"，信息不完整 |
| **架构方案** | 1) `types.py` 新增 `Turn(decision, observation, reflection: Reflection \| None = None)`，`AgentState.history` 类型从 `tuple[Observation, ...]` 改为 `tuple[Turn, ...]`；2) `MemorySystem` 协议拆两阶段：`perceive`（Critic.reflect 之前，写入 `reflection=None` 的 Turn）+ `update`（Critic.reflect 之后，补齐 reflection 字段）；3) 同步修改所有 `MemorySystem` 实现（如 `WorkingMemorySystem`） |
| **变更范围** | `lca/contracts/types.py`、`lca/contracts/protocols/memory.py`、所有 `MemorySystem` 实现类、依赖 `AgentState.history` 遍历逻辑的调用方 |
| **依赖** | PR-1 |
| **迁移验证** | **需要一次性数据迁移脚本**：存量持久化的 `AgentState`（若已有生产数据）需要把 `history: tuple[Observation,...]` 转换为 `history: tuple[Turn,...]`（`decision` 字段可能需要用占位值或从旁路日志补齐，需单独评估数据可迁移性）。验证方式：1) 迁移脚本跑一遍 dry-run，抽样比对转换前后条数一致；2) 单测覆盖"perceive 写入 reflection=None"与"update 补齐 reflection"两个独立断言；3) 全量回归测试 |
| **效果** | `Reasoner.think` 第一次能在同一次调用里同时看到历史观察和历史决策/复盘，为后续 `PlanningReasoner` 之类的前瞻规划实现提供数据基础 |
| **风险与回滚** | **本 PR 风险等级最高（阶段一内）**——涉及存量数据结构变更。建议：1) 先双写（新旧字段并存一个版本）过渡；2) 迁移脚本必须支持幂等重跑；3) 回滚预案：保留 `Observation` 兼容读取路径至少一个发布周期 |

---

### PR-7：TeamAssignment / SharedMemoryStore 契约归位到 orchestration.py

| 项目 | 内容 |
|---|---|
| **问题分析** | v2 遗留缺口之一：团队级分工单元若与单体内部的 `SubTask` 共用同一类型，读者无法从类型本身分辨"这是单体内部计划还是团队分工"；`SharedMemoryStore` 若定义位置不对（比如误放在 L1 memory.py），会造成"单会话状态"和"团队共享状态"概念混淆 |
| **架构方案** | 1) `types.py` 新增 `TeamAssignment(member_id, objective, depends_on)`，与 `SubTask` 语义分离并在 docstring 里写明区别；2) `protocols/orchestration.py` 新增 `SharedMemoryStore` Protocol（`read/write/delete`，按 `team_id` 分区）+ `OrchestrationContext`（team_id/members/shared_memory）+ `TeamEntrypoint`/`OrchestrationStrategy`/`Synthesizer` 三个协议 |
| **变更范围** | `lca/contracts/types.py`、`lca/contracts/protocols/orchestration.py`（新增内容） |
| **依赖** | PR-1、PR-6（`TeamAssignment` 与已迁移的 `Turn`/`SubTask` 处于同一文件，放在同一 PR 里改动面更小） |
| **迁移验证** | 1) 全仓库搜索 `SharedMemoryStore` 定义，唯一命中位置应是 `orchestration.py`；2) 搜索 `TeamAssignment` 定义唯一命中 `types.py` 且与 `SubTask` 不共用同一个类（对应第 18 节验收标准）；3) 这一步只是契约定义，尚无实现，因此单测仅覆盖 Protocol 的 `isinstance`/类型检查层面，不涉及运行时行为 |
| **效果** | 团队编排契约在 PR-1 时就已预留（`orchestration.py` 是七个协议文件之一），本 PR 第一次把内容填实，为 PR-10 的 `DefaultTeamEntrypoint` 实现提供类型基础 |
| **风险与回滚** | 低风险（新增契约，无现有调用方）。回滚：删除新增类型定义即可 |

---

## 阶段二：实现层落地

### PR-8：L1~L3 实现层目录补齐与 import-linter 包名对齐

| 项目 | 内容 |
|---|---|
| **问题分析** | PR-2 的 `import-linter` 分层规则引用了 `lca.cognition`/`lca.embodiment`/`lca.memory`/`lca.runtime`/`lca.agent`/`lca.orchestration` 六个包名，但如果这些实现包尚未按新命名规范创建，该规则实际上是"空转"——规则存在但没有对应实体去验证 |
| **架构方案** | 按文档第 13 节新增六个实现包及各自 `__init__.py`（写入"协议→子包→内置实现"映射文档），骨架内容包括：`cognition/{reasoner,decision_parser,critic,conflict_monitor,task_coordinator,completion_policy,task_decomposer,skill_router,prompt,planning}/`、`embodiment/{actions,tool_registry,safe_executor,fallback}/`、`memory/`、`runtime/{step_outcome}/`、`agent/`、`orchestration/{shared_memory,strategy,synthesizer}/`。本 PR **只建骨架和已有实现的物理归位**，不包含 StepRuntime/TeamEntrypoint 的核心编排逻辑（留给 PR-9/PR-10） |
| **变更范围** | 六个顶级包的目录结构、`__init__.py` |
| **依赖** | PR-3、PR-4、PR-5、PR-6、PR-7（需要契约层命名/结构先稳定，否则实现层归位后还要跟着契约层改名返工） |
| **迁移验证** | 1) `import-linter` 的 `layered-architecture` 契约首次对六个真实包名转绿（此前该规则引用的包名可能不存在或结构不符）；2) 全量单测零失败；3) 人工核对每个 `__init__.py` 映射表与实际类文件逐行对应 |
| **效果** | `import-linter` 第一次从"规则存在但空转"变成"规则对真实代码生效"；实现层目录与契约层第一次形成完整的镜像对应关系（硬约束一在实现层同样成立） |
| **风险与回滚** | 中等风险：涉及大量文件搬迁，建议按子包拆成多个小 commit（比如 `cognition/` 一个 commit，`embodiment/` 一个 commit）便于单独回滚定位问题 |

---

### PR-9：StepRuntime 标准编排落地 + 15.4 CI + 单体集成测试

| 项目 | 内容 |
|---|---|
| **问题分析** | 硬约束五"组合逻辑要能被读出来"——如果 `StepRuntime.run()` 的九步编排顺序只停留在文档描述里，实际代码可能因为重构悄悄改变调用顺序（比如有人把 `MemorySystem.perceive` 移到 `Critic.reflect` 之后），而没有任何机制能拦下这种漂移 |
| **架构方案** | 1) 把文档第 9.1 节伪代码落为 `lca/runtime/step_runtime.py` 的真实实现——严格九步：`think → parse → enforce → act → perceive → reflect → resolve → update → judge/is_complete`；2) 落地 15.4 CI 脚本 `tools/ci/check_step_runtime_order.py`——AST 扫描 `StepRuntime.run` 方法体内九个调用点的相对顺序，与文档约定顺序做字符串序列比对 |
| **变更范围** | `lca/runtime/step_runtime.py`、`tools/ci/check_step_runtime_order.py`、`lca/runtime/step_outcome/budget_step_outcome_policy.py` |
| **依赖** | PR-8（需要 `runtime/` 包骨架已存在）、PR-6（九步中的 perceive/update 依赖 Turn 类型两阶段写入语义） |
| **迁移验证/验收** | 1) 15.4 CI 转绿；2) **集成测试覆盖四类分支**（文档 17.9 明确要求）：单步执行、多步循环、提前终止（`StepOutcomePolicy`/`CompletionPolicy` 任一为真）、`ConflictMonitor` 拒绝决策后的改写路径；3) 覆盖率要求：九个调用点各自的失败/异常分支至少一条用例 |
| **效果** | 单体循环第一次从"文档描述的九步"变成"CI 可验证的九步"——这是第 18 节验收标准里唯一一条贯穿契约到实现的动态检查，标志着硬约束五在单体链路上首次真正落地 |
| **风险与回滚** | 中等风险：这是核心执行循环，建议灰度发布（先在测试环境跑满一个完整业务场景的真实流量回放，比对新旧实现的最终 `AgentState` 是否一致，再上生产）。回滚：保留旧编排实现一个版本作为 feature flag 兜底 |

---

## 阶段三：多智能体验收（v3 核心新增，本次修订的验收锚点）

### PR-10：SharedMemoryTool + DefaultTeamEntrypoint + BroadcastOrchestrationStrategy 落地 + 15.5/15.6 CI

| 项目 | 内容 |
|---|---|
| **问题分析** | 这是 v2→v3 修复的两个最核心缺口：(1) `TeamEntrypoint`/`OrchestrationStrategy` 契约存在但从未有可执行编排算法；(2) `SharedMemoryStore` 契约存在但团队成员"如何在单体循环内部实际访问到它"从未定义，容易被后续实现绕过契约直接持有引用，破坏"团队协作对 Body/Runtime/AgentEntrypoint 三层协议零改动"这条设计初衷 |
| **架构方案** | **核心设计决策**：共享存储不新增协议，而是包装成一个普通 `Tool`——团队成员看到的就是"多了一个叫 `shared_memory` 的工具"，走 `Body.act` 现有的第二级分发（`ToolCallOperation → ToolRegistry.get → SafeExecutor.execute`），与调用任何其他工具无区别。具体落地：1) `lca/orchestration/shared_memory/shared_memory_tool.py`——`SharedMemoryTool(Tool)`，`team_id` 构造期闭包绑定，`run(op, key, value)` 支持 read/write/delete；2) `lca/orchestration/team_runtime.py`——`DefaultTeamEntrypoint`，构造期绑定 `OrchestrationContext`/`strategy`/`synthesizer`，`run(objective)` 只做两步：`dispatch` → `synthesize`；3) `lca/orchestration/strategy/broadcast_strategy.py`——`BroadcastOrchestrationStrategy`，全员并发、无依赖拓扑，把 objective 按模板改写成每个成员的 `TeamAssignment` 后并发调用现成的 `AgentEntrypoint.execute()`，不重新发明单体循环；4) 落地 15.5（`dispatch`→`synthesize` 顺序检查）与 15.6（禁止 `cognition/`/`embodiment/` 目录下任何文件直接 import `orchestration.shared_memory` 具体实现类，保证共享内存只能作为 Tool 被访问） |
| **变更范围** | `lca/orchestration/{team_runtime.py, shared_memory/, strategy/, synthesizer/}`、`tools/ci/check_team_runtime_order.py`、`tools/ci/check_shared_memory_access_path.py` |
| **依赖** | PR-9（必须等单体循环有集成测试兜底后再启动，避免两条链路同时出问题时难以定位问题源头——这是文档 17.10 明确写出的顺序约束）、PR-7（`SharedMemoryStore`/`TeamAssignment` 契约已就位）、PR-8（`orchestration/` 包骨架已存在） |
| **迁移验证/验收** | 1) 15.5/15.6 两条 CI 转绿；2) 单测覆盖：`SharedMemoryTool` 的 read/write/delete 三个 op、`BroadcastOrchestrationStrategy.dispatch` 的并发调用（用 mock `AgentEntrypoint` 验证确实是并发而非串行）、`DefaultTeamEntrypoint.run` 确认 `dispatch` 返回值原样传给 `synthesize`（而非重新构造）；3) 组装期依赖注入的示例代码（文档 10.2 节"researcher + writer 两人团队"）需要有对应的构造函数级单测，验证每个成员的 `ToolRegistry` 确实被注入了绑定同一 `team_id` 的 `SharedMemoryTool` 实例 |
| **效果** | 团队协作能力第一次做到"`AgentEntrypoint`/`Runtime`/`Body` 三层协议一个字不改"——完全通过组装期依赖注入实现，验证了文档"团队协作是纯粹的依赖注入问题，不是契约设计问题"这一核心论断 |
| **风险与回滚** | **高风险**（新链路，无历史生产验证）。建议：1) 先在单一团队场景（两人团队）灰度；2) `SharedMemoryStore` 初期用 `InMemorySharedMemoryStore`，避免引入外部存储依赖增加排查复杂度；3) 回滚预案：`TeamEntrypoint` 是全新能力，未上生产前可以整体 feature-flag 关闭，不影响单体链路 |

---

### PR-11：端到端多智能体集成测试（第 16 节场景复现）

| 项目 | 内容 |
|---|---|
| **问题分析** | 15.4/15.5/15.6 三条 CI 都是**静态**检查（AST 扫描调用顺序、import 关系），能拦住"顺序被改错""被绕过访问"，但**拦不住**"两个 agent 并发读写共享内存时是否真的能正确协作产出结果"这种**动态**正确性问题。文档第 18 节明确把"端到端集成测试通过"列为与"contracts 层文件名对应层次"同等重要的验收项，缺一不可 |
| **架构方案** | 严格复现文档第 16 节场景：`team_id="team-report-001"`，`researcher`（配 mock 搜索工具）+ `writer`（无工具）两人团队，目标"写一份关于 X 主题的简报"。测试断言覆盖七个编号步骤：①`team_runtime.run` 入口 → ②`dispatch` 并发驱动两个成员 → ③researcher 内部两步循环（检索 + 写入共享内存）→ ④writer 内部循环（读共享内存，若未就绪需验证等待/重试路径不属于契约层强制约定这一设计留白）→ ⑤结果汇总 → ⑥`LLMSynthesizer.synthesize` 产出最终文本 → ⑦返回应用层。额外补一条"researcher 临时 DELEGATE 给团队外翻译 agent"的支线用例，验证 10.3 节判定表"两条路径互不依赖、可并行发生"的论断 |
| **变更范围** | `tests/integration/test_team_e2e_report_scenario.py`（新增），可能需要 mock 版 `LLMAdapter`/`SearchTool` 固定返回值以保证测试确定性 |
| **依赖** | PR-10 |
| **迁移验证/验收** | 1) 测试断言 researcher 的 `history` 中包含"检索"与"写入共享内存"两个 Turn；2) 断言 writer 能读到 researcher 写入的内容（验证共享存储跨成员可见性，而非各自实例隔离）；3) 断言最终产出文本来自 writer 的正文 Turn，而非 researcher 的调研笔记；4) DELEGATE 支线用例断言不影响主线 `dispatch`/`synthesize` 的推进 |
| **效果** | "多agent 链路清晰"从文档承诺第一次变成可重复运行、可在 CI 里长期把关的自动化证据，而不是"看了实现才知道对不对" |
| **风险与回滚** | 低风险（纯测试新增，不改动生产代码）。若测试暴露 PR-10 的实现问题，回滚点是 PR-10 而非本 PR |

---

### PR-12：全量验收清单核验与文档收口

| 项目 | 内容 |
|---|---|
| **问题分析** | 文档第 18 节列出 11 条验收标准，分散在各个 PR 里逐一达成，但缺一个"收口"动作去确认全部标准同时成立（比如 PR-9 达成时 PR-10 尚未合入，某条标准可能在中间状态被误判为通过） |
| **架构方案** | 不产生新的业务代码，只做：1) 逐条核对第 18 节 11 条验收标准并在 ADR-0015 文档里补一张"验收标准 → 达成 PR → CI job 名称"对照表；2) 跑一次全量 CI（15.1~15.6 六条规则 + 单体/多agent 两套集成测试）确认全绿；3) 更新 `README`/架构文档中的目录树描述与本次落地后的真实目录树做最终 diff，确保文档与代码零漂移 |
| **变更范围** | `docs/adr/ADR-0015-contracts-v3.md`（补充验收对照表）、项目根 `README.md`（如有架构描述章节） |
| **依赖** | PR-0~PR-11 全部合入 |
| **迁移验证/验收** | 逐条核对文档第 18 节 11 条标准： |

**验收标准对照表**（PR-12 核心交付物）：

| 第18节验收标准 | 达成PR | 验证方式 |
|---|---|---|
| 契约层文件名对应层次，无一例外 | PR-1 | 人工核对 + 目录快照 |
| 实现层文件路径对应协议，无一例外 | PR-8 | 人工核对 + 目录快照 |
| mechanisms/types 只含非业务语义内容 | PR-5 | `grep` 关键字零命中 |
| 全仓库无 `class .*Handler`（除豁免） | PR-2、PR-3 | CI 15.3 |
| `AgentState` 方法首参数恒为 `state` | PR-2、PR-3 | CI 15.1 |
| import-linter 分层契约全绿 | PR-2、PR-8 | CI 15.2 |
| StepRuntime 九步顺序与文档一致 | PR-9 | CI 15.4 |
| DefaultTeamEntrypoint dispatch→synthesize 顺序一致 | PR-10 | CI 15.5 |
| cognition/embodiment 不直接 import shared_memory 实现 | PR-10 | CI 15.6 |
| SharedMemoryStore/TeamAssignment 定义位置唯一 | PR-7 | `grep` 定位 |
| 第16节端到端场景集成测试通过 | PR-11 | 集成测试 job |

| 效果 | 内容 |
|---|---|
| | 全部 11 条验收标准第一次同时被同一次 CI 流水线验证通过，架构方案从"文档承诺"正式转为"代码事实"，v3 相对 v2 的三处结构性缺口全部关闭 |

---

## 补充建议

1. **PR-6 与 PR-10 是全流程风险最高的两个节点**，都涉及"存量行为改变"（前者是数据结构迁移，后者是全新执行链路），建议这两个 PR 各自安排独立的灰度观察期，不与其他 PR 打包发布。
2. **15.1~15.6 六条 CI 规则建议做成 required check**，一旦 PR-2/PR-9/PR-10 落地后，任何后续业务需求 PR 都会被自动挡在"违反分层/顺序/命名约定"的门外，这是本方案相比"停留在文档"的核心增量价值。
3. 如需要，我可以针对某一个 PR（比如 PR-9 或 PR-10）进一步展开到"具体代码 diff 级别的实现草案 + 单测用例清单"，告诉我优先级即可。
