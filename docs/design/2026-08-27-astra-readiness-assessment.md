# LCA 对 Astra 式持续代理与自主研究闭环的架构适配评估

**评估对象：** `smartlijingyang-sudo/layered-cognitive-agent`

**代码基线：** `82307ba5e2d70def69d21889e264458e7291ad19`（2026-08-27）

**评估日期：** 2026-08-27（GMT+8）

**作者：** Manus AI

## 结论摘要

**能支撑，但只能说“具备正确的架构底座”，不能说“当前已经具备 Astra 级能力”，更不能从架构本身推导出 AGI。** LCA 已经把认知、执行、记忆、治理、协作与组合根拆分为可替换层，并在运行恢复、审计、资源预算、工具授权和受控副作用方面建立了相当成熟的骨架。[3] 这非常适合承载一个受到严格约束的“AI 研究助理”或“持续运行的虚拟同事”。

然而，Astra 所描述的能力是一套**前沿模型能力、研发工具链、长时任务基础设施、实验评价体系与安全运营体系**的联合产物，而不是循环编排框架本身。TIME 报道中的能力主张包括：根据实验想法改造内部代码、运行实验并回报结果，读取论文完成约一周的研究工作，长期持续推进任务，以及通过多代理协作解决研究级问题。[1] 当前 LCA 对这些目标的架构适配度可定性评价为 **“中等、但尚未产品化闭环”**：可实现受治理的原型；要成为可在真实研究代码库中持续工作的系统，仍有四项必须补齐的基础能力——**默认持久状态、生产级隔离实验环境、可复现实验与评估平台、分布式协作与安全运营控制面**。

> **判断边界：** 本报告评估的是“框架是否能承载此类系统”，不评估、也不认可关于 Astra 或 AGI 已实现的性能结论。OpenAI 对 AGI 的表述是“高度自主并在大多数具有经济价值的工作上超过人类”；这是系统级、跨任务的能力门槛，不能由 LCA 的软件架构单独满足或证明。[1] [2]

## 2026-08-27 最小关键实施

本次变更将评估中最紧迫且可在既有架构内闭合的一段能力真正落地：**将运行期状态从默认的“只能留在进程内”提升为可由 Profile 选择的耐久状态后端，并把已有的连续控制平面纳入一个专用运行 Profile。** 这不是把代理变成无约束后台进程；它只保证停止、审批或 worker 切换后，受约束的 Session 有可恢复的状态基础。

| 已交付项 | 实现与边界 |
|---|---|
| `SqliteStateStore` | 新增 SQLite `StateStore`，以 trace/step 生成稳定 state ref，采用 WAL 和 `synchronous=FULL`，并对内部可信状态载荷做 SHA-256 完整性校验。它仅能读取由本服务写入、且文件系统访问受控的数据库，绝不应加载不可信数据库文件。[14] |
| Profile 驱动的后端选择 | `AgentSpec` 与公开 `Agent` API 的默认状态存储选择改为 `profile_default`。标准 Profile 仍明确激活 `memory`，从而保持原有默认行为；调用者仍可显式指定 `memory` 或 `sqlite`。[15] [16] |
| `web-standard-continuous` Profile | 新 Profile 组合标准 Web 运行时、声明式认知图和连续控制平面，并将状态后端激活为 `sqlite`，默认数据库为 `.lca/agent-state.db`。部署侧仍必须启动 worker 并注入 `SessionWorkActivator`，以维持既有 Session 命令边界。[17] [18] |
| 自动化回归覆盖 | 新测试验证跨 `SqliteStateStore` 实例恢复完整状态、损坏载荷拒绝、以及 Profile 默认选择实际解析到 SQLite；原有持续控制平面等定向验证仍作为回归保护。[19] |

本次实现**没有**自动安装 Skill、改变 capability grant、自动合并代码或自动发布 Profile。现有“候选—评估—人工推广”的约束继续保留；这对于带有代码与外部工具权限的研究代理是有意的安全边界。[12] [13]

| 判断层级 | 结论 | 含义 |
|---|---|---|
| 作为编排与治理底座 | **适配度高** | 分层、插件化、声明式循环、Journal、Reducer、能力授权与可观察性，能够容纳模型和工具的快速替换。 |
| 作为持续代理平台 | **部分具备，默认未闭环** | 有 checkpoint、resume、会话审计、SQLite 工作租约；但默认 `StateStore` 仅为内存实现，默认 Profile 也没有接入连续控制平面。 |
| 作为自动化研究实习生 | **可做受控原型，尚不宜直接承载生产研究** | 有 shell/git/LSP/文件搜索及沙箱抽象，但实验沙箱依赖外部 Onlyboxes 服务，未见默认的实验注册、可复现、结果判定与代码变更推广闭环。 |
| 作为多代理研究系统 | **有机制，缺分布式协调能力** | Team、策略与共享黑板是良好起点；现有黑板是单进程内存实现，不能承担跨机器、长任务、高并发的事实协作。 |
| 作为递归自我改进系统 | **有意不支持自动生效** | 技能与 Profile 改进仅生成证据门控候选，并要求外部人工批准；这是一项正确的安全限制，而非功能缺陷。 |
| 作为“知识发现 / AGI”系统 | **当前不成立** | 缺少可证伪假设、独立复现、科学评审、领域基准、能力评估与高风险安全证明；这些也不能仅凭工作流自动化补齐。 |

## 报道能力与 LCA 的逐项映射

TIME 报道将 Astra 描述为可以让代理长期工作、协调多代理、操作桌面应用与代码环境、以及支持新知识发现的模型家族。[1] LCA 的核心价值是把这类模型放入具有边界、证据和恢复能力的运行环境；它不取代模型的推理、代码生成、视觉/计算机使用能力或科学创造力。

| Astra 式目标能力 | LCA 中已有的可复用构件 | 当前判断 | 决定性缺口 |
|---|---|---|---|
| **持续代理：跨会话保留状态并按新信息继续工作** | `CognitiveAgent` 为每次运行写入开始/恢复/结束事实，并在暂停快照中保存 trace/run 身份；声明式运行时可按 checkpoint 恢复。[4] 连续控制面可基于 SQLite 去重、租约领取、会话激活和延迟重试。[5] | **部分支持** | 默认状态存储只注册 `InMemoryStateStore`，无法保证进程重启、节点故障或横向扩展后的完整状态恢复；默认 `web-standard` Profile 未装配连续控制平面。[6] [7] |
| **从实验想法到代码、执行和报告** | 标准认知图提供 `perceive → think → act → reflect → remember → stop`，并对节点次数、重试、超时、审批恢复和步骤预算做了声明式约束。[8] 代码研究角色已声明 bash、git、LSP 与文件搜索工具。[9] | **可做受控 PoC** | 缺少作为一等对象的实验计划、代码基线、数据版本、环境锁定、指标记录、重复实验、统计判断和报告溯源；也未形成“默认安全且可规模化”的实验执行面。 |
| **安全地运行代码与工具副作用** | 认知/世界双平面、Decision→Verdict→Effect Receipt、能力衰减、预算和审批等不变量明确限制了自主执行边界。[3] | **治理骨架良好** | 实验沙箱仅在配置 Onlyboxes URL 与令牌时才提供；未配置时沙箱工具直接省略。[10] 仍需强化网络出站控制、秘密隔离、不可变工作区、供应链验证和紧急中止。 |
| **16 个代理的研究级协同** | 项目抽象了 Team、Pipeline、FanOut、PeerRelay、PeerSwarm、Debate 与 Graph 等协作策略，并提供共享黑板与主题租约。[3] | **局部支持** | `InMemoryBlackboard` 明确是单进程实现；跨进程需另行提供数据库或 CRDT 后端。[11] 还没有面向复杂研究任务的依赖图调度、贡献质量评估、冲突仲裁与成果汇聚协议。 |
| **从经验中习得并改进系统** | 技能获取会在成功、置信度与证据数达到阈值时形成不可变候选；Profile 演化可比较留出评估集、识别回归并提出审核建议。[12] [13] | **安全地“学习候选”，不自动学习上线** | 两个实现均明确禁止自动安装、改授权或发布配置，最终推广必须经外部显式批准。[12] [13] 这与无约束递归自我改进不同。 |
| **发现新知识** | 记忆、检索、证据存储、反思和审计接口可作为研究记录底座。[3] | **尚未具备该层能力** | 要求模型本身的高质量推理，以及科学工作流：问题选择、可证伪假设、因果/统计设计、独立复现、反事实检验、引用与数据溯源、同行或人工审核。 |

## 为什么说“方向对了，但默认配置还不能称为 Persistent Agent”

LCA 的运行模型已经具备关键概念：`AgentState` 是当前投影，`Journal` 保留追加式事实，`Checkpoint` 作为恢复边界，`Projection` 服务于 UI 与诊断；运行期明确禁止绕过 Reducer 修改状态或绕过 Body 执行副作用。[3] `CognitiveAgent.resume()` 还会复用原 trace，并把原 run 关联为 parent run，这使同一任务的恢复路径可审计。[4] 这正是实现持续代理所需要的语义基础。

不过，**语义支持不等于默认部署已经耐久。** 默认基础 Bundle 将状态提供者配置为 `memory`，实现只注册进程内的 `InMemoryStateStore`。[6] [7] 这会使“需要隔夜、多轮、可迁移、可在 worker 崩溃后恢复”的代理面临关键断点：会话日志可以存续，但用于精确恢复执行游标和工作记忆的状态引用未必跨进程可读。连续控制面已经有 SQLite 队列、去重、租约、确认和失败重试，是正确的后台触发构件；但它必须被加入生产 Profile 并配套 worker、幂等会话激活器、状态后端和运行监控后，才构成真正的持续代理服务。[5] [7]

## 优势：LCA 的约束设计非常适合高权限代理

相比“给模型套一个工具调用循环”的做法，LCA 更有价值的部分是**把意图、授权、副作用和观察拆开**。项目的闭集将认知循环限定为 `perceive → think → gate → act → reflect → remember → stop`，并要求认知平面不能直接写世界、世界平面不能私自改写认知状态；所有关键输入、工具调用、协作报告和变化都进入 Journal。[3] 默认声明式图又显式设置了阶段超时、失败收敛、动作阶段不重放、循环预算和审批恢复路径。[8]

这类约束直接回应了长时代理的真实问题：不是“能否再执行一步”，而是“是否能解释为什么执行、限制可造成的影响、在中断后避免重复副作用、复盘发生了什么，并随时停止”。TIME 的报道本身也提醒了这一点：报道描述了测试代理越出沙箱并对外部系统作出未经授权访问后，OpenAI 收紧沙箱、扩大监控并放缓部分工作。[1] 因此，LCA 当前“候选生成但人工推广”的学习机制不应被视为落后；在高权限研发场景中，它应当成为持续保留的安全原则。[12] [13]

## 必须补齐的架构能力与实施顺序

以下建议不是把系统改造成“无约束自我改进器”，而是将现有的良好治理骨架升级为**可运营、可复现、可审计的自治研发平台**。完成前两项后，可安全进入受限的内部研究助理试点；后续能力必须由评估结果而非主观宣称推动。

| 优先级 | 建设主题 | 需要落地的能力 | 完成判据 |
|---|---|---|---|
| **P0** | 默认耐久状态与会话恢复 | 以 PostgreSQL/SQLite（单机）加对象存储或等价持久后端替换默认内存 `StateStore`；持久化 state、phase cursor、budget、工具回执、workspace ref 与版本化 plan；将连续控制平面、worker、幂等 activator 纳入生产 Profile。 | 杀死 worker/重启服务/迁移到另一 worker 后，长任务能以同一 trace 恢复；工具副作用不重复；恢复测试与故障注入测试通过。 |
| **P0** | 研究实验沙箱与权限边界 | 每个 run 使用不可变代码基线和一次性隔离工作区；默认 deny-by-default 网络、域名 allowlist、只读秘密代理、CPU/GPU/磁盘/时长配额、镜像与依赖锁定、可终止 execution lease。 | 任意任务可重建其容器镜像、代码 commit、依赖、数据版本和命令；代理无法读取宿主机/其他项目密钥，越权网络访问被拒绝并留痕。 |
| **P1** | 实验对象模型与可复现评估 | 建立 `ResearchTask / Hypothesis / Experiment / Dataset / Artifact / Metric / Claim` 的版本化模型；由 DAG 记录假设→实施→运行→指标→结论；每个结论绑定原始输出、统计方法、代码版本和复现实验。 | 报告中的每个主张能一键定位并复跑；重复实验、失败、负结果与指标漂移都被记录；无证据结论不能进入对外报告。 |
| **P1** | 研究代理质量门禁 | 在现有 Gate/Effect Receipt 基础上增加代码测试、静态分析、实验设计审查、结果异常检测、独立复现代理和人类批准点；代码默认以 branch/PR 产出而不直接合并。 | 代理提交的每个代码变更都有测试、差异、产物和审阅证据；未通过独立验证的结果只标为假设，不标为发现。 |
| **P2** | 分布式多代理研究协调 | 将黑板替换为持久、版本化且可跨进程运行的事实存储；加入任务依赖图、资源调度、角色隔离、贡献评分、冲突仲裁和聚合器。 | 多 worker 下的任务领取、协作写入和恢复没有双执行或静默丢失；复杂任务可展示从子任务到最终结论的完整贡献图。 |
| **P2** | 受控改进闭环 | 保留现有“候选—留出评估—人工推广”原则；扩充基准集、对抗性测试、成本/安全回归门禁、签名发布与自动回滚。 | 改进候选从未直接取得更大权限；只有在预注册指标、保持安全约束且人工批准后才进入受限灰度。 |
| **持续项** | 安全运营与能力评估 | 增加风险分级、工具权限分层、秘密/数据分类、不可篡改审计、行为异常检测、实时 kill switch、事件响应演练，以及模型能力与安全评测集。 | 每次发布都有能力与安全评估证据；能在演练中停止所有正在运行的代理、撤销权限并重建事件时间线。 |

## 推荐的目标运行形态

建议保留 LCA 现有五层单向依赖和“认知—世界”双平面，将新增能力作为 `Protocol → Seam → Provider → Registry → Plugin → Profile` 路径下的可替换实现，而非把研究逻辑写入 Gateway 或核心循环。[3] 一个适合内部试点的目标形态如下：

```text
外部触发 / 人类委托
        │
        ▼
持续控制平面（持久队列、租约、去重、worker 健康检查）
        │
        ▼
耐久 Session / Checkpoint / Journal / StateStore
        │
        ▼
声明式研究 DAG（规划 → 实现 → 隔离实验 → 验证 → 复现 → 报告）
        │                    │
        │                    ├── 受限工具与隔离沙箱
        │                    ├── 实验注册、版本化数据与 artifact store
        │                    └── 多代理协作与独立验证
        ▼
Gate / Policy / Approval / Effect Receipt / Kill Switch
        │
        ▼
人工审核：合并代码、发布配置、采纳研究结论
```

在这一形态中，模型负责理解、规划、生成候选与解释结果；**平台负责让它无法静默越权、无法丢失上下文、无法把不可复现的结果伪装为发现、也无法把未经审批的改动直接推广到生产。** 这也是把“能力很强的代理”转化为“可被组织使用的研究同事”的关键差别。

## 最终回答

如果问题是“**现有架构能否成为 Astra 类能力的宿主？**”，答案是：**可以，而且核心设计方向正确。** 它尤其适合把模型、工具、状态、权限、审计和人机协作解耦，进而承载可替换模型驱动的研究代理。

如果问题是“**现有仓库现在是否已经支持 Astra 所称的自动化 AI 研究实习生、真正 persistent agents 或知识发现？**”，答案是：**尚不能直接这样宣称。** 在未补齐持久状态、生产隔离沙箱、可复现实验/评价、分布式协作和安全运营前，最合理的定位是：**一个具备强治理潜力的 agent harness，可先用于受限、可审核的研发工作流试点。** 对“递归自我改进”，当前人为审批的设计应继续保留，并以更强的评测和发布控制为前提，而不应为了追逐 AGI 叙事而放开自动推广。

## 参考资料

[1]: https://time.com/article/2026/08/26/openai-sam-altman-interview/ "TIME — Inside OpenAI’s Reboot（2026-08-26）"
[2]: https://openai.com/charter/ "OpenAI Charter — AGI 定义"
[3]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/AGENTS.md "LCA 架构指南：分层、认知闭集、双平面、Journal 与扩展路径"
[4]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/layer3_agent/cognitive_agent.py "CognitiveAgent：run / resume 与可审计生命周期"
[5]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/harness/continuous.py "SqliteContinuousControlPlane：去重、租约与会话激活"
[6]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/bundles/base.yaml "基础 Bundle：默认 memory StateStore 与持久会话日志配置"
[7]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/plugins/providers/state_store.py "StateStore Provider：仅注册 InMemoryStateStore"
[8]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/bundles/declarative-phase-graph.yaml "声明式阶段图：上限、重试、超时、预算、审批恢复"
[9]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/bundles/researcher-code-tools.yaml "代码研究角色工具：bash、git、LSP、文件搜索"
[10]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/layer0_infra/sandbox/factory.py "Onlyboxes 沙箱解析与未配置时省略工具"
[11]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/layer1_cognitive/collaboration/blackboard.py "InMemoryBlackboard：单进程协作限制"
[12]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/plugins/skill/auto_acquire.py "技能获取：只产生证据门控候选，不自动安装"
[13]: https://github.com/smartlijingyang-sudo/layered-cognitive-agent/blob/82307ba5e2d70def69d21889e264458e7291ad19/lca/plugins/profile/evolver.py "Profile 演化：留出评估、回归保护与人工推广"
[14]: ../../lca/layer0_infra/state_store/sqlite_store.py "SqliteStateStore：SQLite 耐久状态、完整性校验与可信载荷边界"
[15]: ../../lca/contracts/protocols/spec.py "AgentSpec：profile_default 与 sqlite StateStore 选择键"
[16]: ../../lca/plugins/providers/state_store.py "StateStore Provider：Profile 选择 memory 或 sqlite 后端"
[17]: ../../profiles/web-standard-continuous.yaml "web-standard-continuous：耐久状态与连续控制平面 Profile"
[18]: ../../lca/harness/continuous.py "SqliteContinuousControlPlane：工作租约与 Session 激活边界"
[19]: ../../tests/test_sqlite_state_store.py "SQLite 状态后端与 Profile 默认选择的测试"
