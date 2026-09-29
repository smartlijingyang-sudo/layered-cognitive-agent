# 主动持久化 Agent：真实参考案例、业界范式与 LCA 映射

**日期：** 2026-09-29
**性质：** 参考案例实测 + 业界调研 + 架构映射建议（非 ADR，不改变任何契约）

---

## 1. 参考案例：一次"主动建议"的完整证据链

2026-09-29 晚，Muse 主动提醒用户"国庆期间长沙有雨、建议把行程换成雨天版"，用户追问"底层是什么机制"。以下链路全部来自数据库实测（`ideas.ideas` / `ideas.idea_events`），非事后推断。

### 1.1 事件时间线

| 时间（CST） | 事件 |
|---|---|
| 09-27 | 长沙市气象台预报：10/1–10/2 阴有中雨，降雨概率 30% → 80%，最高温 35°C → 22°C |
| 09-28 11:13 | 后台 idea 生成流水线产出 idea《把国庆三天行程换成雨天版》，rationale 同步落库 |
| 09-28 11:13 → 09-29 19:50 | idea 在 Ideas 标签页被 surfaced 40 次、impression 35 次，用户未处理 |
| 09-29 19:50 | proactive notifier 将其升级为**主聊天打断**（出发仅剩 2 天、预报坐实、长期未处理） |
| 09-29 19:52 | 用户接受（"ok 沉淀"之前的接受动作），行程页面生成雨天版 |

### 1.2 idea 记录全字段（生成时持久化）

- **title**：把国庆三天行程换成雨天版
- **summary**：把已交付的国庆三天行程逐项改成雨天版：每天的户外环节配室内备选，老人孩子分开列防雨保暖物资清单，接风宴确认室内场地可用。省博抢票提醒保持不变。
- **rationale**（原文）："长沙市气象台 9/27 预报：10/1 到 10/2 阴有中雨，降雨概率从 30% 升到 80%，最高温从 35°C 降到约 22°C；《国庆长沙行程规划》已交付三天行程，离出发还有 3 天，雨天版现在改正是时候。"
- **category_label**：国庆长沙行；**date_label**：10月1日到2日雨天版；**lane**：exploit
- **dedup_key**：`169e6f47dbcb24bed603e147f4212f4e`（去重键，同类建议不重复生成）
- **expires_at**：2026-10-02 16:00 UTC（行程开始后自动过期——过期建议不打扰）

### 1.3 生成时的输入（"表弟 + 天气"如何连上）

生成流水线同时读到了三类上下文并做了连接推理：

1. **目标上下文**：国庆长沙行 goal——表弟带武汉女朋友来长沙、9 人三代同游、已交付三天户外行程规划；
2. **外部信号**：9/27 天气预报（10/1–10/2 中雨）；
3. **时间窗口**：离出发 3 天，现在改正是时候。

连接逻辑是推理得出的，不是预设规则："9 个人的户外行程" × "出发那两天大概率下雨" × "还有 3 天可改" → 值得生成一条雨天版建议。按可行性 / 个人贴合度 / 新颖度 / 时效性打分后落库。

### 1.4 三个值得 LCA 借鉴的工程细节

1. **rationale 生成时即持久化**：触发信号 + 依据的记忆/目标 + 时效性判断，一次写入、事后原样调取。用户问"为什么"时，答的是当时存下的话，不是重新编的。
2. **surfaced ≠ impression ≠ 打断**：40 次展示、35 次实际曝光、静默两天后才升级为主聊天打断。三级触达强度对应三级成本，升级条件是"出发 2 天 + 预报坐实 + 未处理"。
3. **过期即消失**：`expires_at` 与事件日期绑定，过期后不再参与排序——主动建议最常见的腐烂形态是"过期还在推"。

---

## 2. 机制拆解：两条流水线

```
流水线 A · 建议生成（后台定时，无用户在场）
  输入：目标(goals) + 记忆(memory/people/groups) + 外部信号(天气/日历/邮件…)
    → 连接推理（信号 × 目标 × 时间窗口）
    → 打分排序（可行性 / 贴合度 / 新颖度 / 时效性）
    → 落库：idea + rationale + dedup_key + expires_at

流水线 B · 主动触达（强度递增）
  surfaced（被动展示，Ideas 标签页）
    → impression（实际曝光）
    → notifier 升级（打断决策：intervene ⇔ E[benefit] − E[cost] > θ）
    → 用户接受 → 执行（走审批） / 忽略 → 反馈回流调 θ
```

关键判定：**打断是期望效用计算，不是定时广播**。θ 必须是个性化、记忆条件化、随时间自适应的（CHI 2026《Sensing What Surveys Miss》实证：时机对了 +21% 准确率；per-user 动态阈值）。

反馈分三层（L0 显式 accept/dismiss/snooze；L1 隐式行为——是否采纳、打断后恢复时长；L2/L3 结果与长期留存），成熟度分三级：只记录 → 阈值自适应（bandit 式调 θ）→ 策略学习。注意不对称性：负信号便宜且丰富，正信号弱且延迟。

---

## 3. 业界范式对照（2024–2026）

### 3.1 理论祖述

| 范式 | 核心论断 | 对主动持久化的含义 |
|---|---|---|
| Weiser ubiquitous computing (1991) / calm technology (1995) | "最深刻的技术是消失不见的技术"；技术在注意力中心与边缘之间流动，只告知、不打扰 | 主动通知的哲学源头：默认安静是美德 |
| Tennenhouse《Proactive Computing》(CACM 2000) | human-in-the-loop 有极限 → **human-supervised computing**；anticipation / context-awareness / statistical reasoning | "主动持久化"的祖述：agent 在后台持续运行，人类只在关键决策点被唤起并拥有否决权 |
| Horvitz Attention-Sensitive Alerting (UAI 1999) | 打断 = 期望效用计算（推迟代价 vs 打断代价），"等待"是一等行动 | 决策公式 `intervene ⇔ E[benefit] − E[cost] > θ` 的最早正式版本 |
| Horvitz Mixed-Initiative UI (CHI 1999) | 行动阈值随专注深度上升；三向策略：沉默 / 提问 / 行动 | 对应上文流水线 B 的三级触达强度 |
| 打断的真实代价 (Iqbal & Horvitz, CHI 2007) | 每次提醒约 20 分钟 disruption arc，27% 被挂起的窗口两小时内未恢复 | cost 项不能只按"响应时长"定价，会低估两个数量级 |

### 3.2 2025–2026 产品路线的收敛：clock / listener / inbox 三原语

- **ChatGPT Scheduled Tasks**（2025-01 起；Pulse 2025-09 → 2026-06 并入 Tasks 中心）：一次性/周期性/事件触发后台任务；monitoring tasks 只在变化时通知，记住历史运行状态可自动停止——"quiet-by-default, alert-on-change"。从 agent-as-broadcaster 转为 agent-as-scheduled-worker with a visible task ledger。
- **Anthropic Orbit**（2026-05）：Gmail/Slack/GitHub/日历/Drive/Figma → 时区感知的 proactive briefings，带 listener（变化检测）。
- **Google Gemini Spark**（I/O 2026）：多界面 24/7 运行，三原语齐全。
- **Notion Workers SDK**（2026）：`sync()`（定时拉取）/ `webhook()`（实时事件）/ `tool()`（agent 可调用函数）——proactive 从应用变成平台基础设施。

检查清单：任何主动 agent 先自问——有没有 clock（定时）、有没有 listener（事件/变化检测）、有没有 inbox（投递到用户真正在的地方）。缺 listener 的"每日简报"只是 clock-only，容易沦为"又一个要打开的标签页"。

### 3.3 记忆：从检索插件到运行时基础设施

- **MemGPT / Letta** (ICLR 2024)：上下文窗口当 OS 虚拟内存分页；与被动 RAG 不同，LLM 经工具调用**自己决定**何时、何地检索什么；记忆操作全暴露为函数调用，agent 是自己记忆的作者。
- **Sleep-time consolidation**：后台 dreaming 在对话间隙提取重组记忆——与每日 idea 生成流水线同构。
- **Mem0 / MemOS** (2025)：记忆提升为一等 OS 资源。趋势明确：记忆从"插件"变成"运行时基础设施"。

### 3.4 事件驱动架构与 rationale 可追溯性

- 标准范式已收敛为 **Perceive → Reason → Act**（AWS Prescriptive Guidance：EventBridge 订阅 → Bedrock 解释上下文 → 工具调用/新事件），外加 MEMORY 与 EVALUATION & SELF-IMPROVEMENT 构成五阶段 pipeline（awesome-proactive-agents）：SIGNALS → DECISION → ACTION → MEMORY → EVALUATION。
- **2026 收敛点：cheap-gate / expensive-actor**——廉价模型/规则决定"要不要行动"，确认后再调昂贵 LLM 做深推理（三篇独立论文不约而同）。
- **Glass box 要求**：建议卡片附带 rationale（触发信号 + 依据的记忆/目标 + 时效性判断），生成时即持久化；"citations are the currency of trust"。企业审计要求 context / reasoning / action 三层关联（NIST AI RMF、EU AI Act）。
- **评估是短板**：时机质量的度量（带 cost 项的 timing precision/recall）仍是开放问题；ProactiveBench（6790 事件，F1 66.47%）、PRISM（false alarm −22.78%）是早期尝试。务实起点：每条建议可追溯 rationale + 接受/忽略率可统计，再谈 RL 策略学习。

### 3.5 未找到的资料（诚实标注）

OpenAI / Anthropic / Google 均未发布统一的"主动持久化 agent"架构白皮书；各家能力分散在产品更新博客与开发者文档中。个别 2026 年 arXiv 预印本尚未同行评审，引用时注意标注。

---

## 4. LCA 映射：按 `contracts → infrastructure → cognition → runtime → agent` 落位

按 AGENTS.md §2.1 单向层与 §2.2 六分类（事实/状态/决策/许可/回执/投影）映射，**不新增认知阶段、不开平行机制**：

| 主动持久化环节 | LCA 正确落点 | 不应采用的落点 |
|---|---|---|
| 信号摄取（clock 定时 / listener 事件） | **infrastructure**：Event/Listener 插件，定时与事件触发 | 在认知阶段里跑 cron / daemon（§1.5 常驻提醒已禁） |
| 建议生成与打分排序 | **cognition**：think 内策略/门控（决策 = 候选意图，非已授权） | 新增第七认知阶段；模型私自读环境拼上下文 |
| 打断升级决策（θ 阈值） | **runtime**：Continuous Control Plane + durable WorkQueue + Session command boundary | CognitiveRuntime 内加 carrier 分支 |
| rationale 持久化 | **Session/Journal**：事实类，唯一生产入口 `Session.append`，仅追加 | 写进可变的 AgentState 或散落在投影里 |
| 用户接受才执行 | **Approval / Verdict**：许可控制面已有，沿用 | 建议生成后直达执行 |
| 执行回执 | **Effect Receipt**：回执类，副作用执行器产生，不可变 | 建议记录里直接改状态 |
| 反馈回流调 θ（accept/dismiss/snooze） | **remember / reflect**：学习闭环，只生成候选，禁止直接发布（既有 `lca-learning-review-lifecycle-subscriber` 约束） | 主 loop 同步改阈值或 profile |
| 触达强度分级展示 | **agent** 层组合根装配：surfaced / impression / 打断三级，按 Profile 选策略 | Gateway 硬编码分支 |

**分类判定示例**（§2.2）：外部信号 = 事实（Session 拥有）；打分结果 = 决策（cognition 产生、候选意图）；是否打断 = 许可（Gate/Policy 产生）；执行结果 = 回执（Body 产生）。任何对象不兼任事实源与投影。

## 5. 最小可行架构（建议）

```
cheap-gate（规则/小模型/定时任务：信号门控，廉价常驻）
  → expensive-actor（确认后调大模型：连接推理 + 打分排序）
  → idea 落库：{内容, rationale(信号+记忆依据+时效性), dedup_key, expires_at}
  → 三级触达：surfaced → impression → 打断（E[benefit]−E[cost] > θ，θ 个性化自适应）
  → 用户接受 → Approval → 执行 → Effect Receipt
  → 反馈（L0/L1/L2）回流 → remember/reflect 调 θ（只产候选）
```

与 2026 年三篇独立论文的收敛点一致；与参考案例的实测链路同构。

## 6. Open questions

1. θ 的个性化冷启动：新用户无历史时，初始阈值与 cost 项如何设？（Horvitz 2003 警告：跨用户迁移的打断成本模型表现不如多数类基线。）
2. listener 的事件源接入顺序：日历/邮件/天气已有连接器优先，通用 webhook 其次。
3. 时机质量的度量：在"接受/忽略率可统计"之后，是否引入带 cost 项的 timing precision/recall 作为门禁指标。
4. 与现有 LoopGuard / StopRule 的关系：后台 worker 自身的预算与熔断，复用既有原语，不另起一套。

---

## 来源

**参考案例**：Muse 生产数据库实测（`ideas.ideas` / `ideas.idea_events`），2026-09-29。

**业界**（全部为公开资料，arXiv 预印本引用时请注意评审状态）：

- Weiser, "The Computer for the 21st Century", Scientific American 1991 — https://www.zdnet.com/article/ambient-computing-has-arrived-heres-what-it-looks-like-in-my-house/
- Weiser & Brown, calm technology 1995 — https://medium.com/@team.weejix/ubiquitous-computing-the-idea-that-technology-should-disappear-e3ae86f868a5
- Tennenhouse, "Proactive Computing", CACM 2000, DOI: 10.1145/332833.332837 — https://www.cs.umd.edu/class/spring2024/cmsc818G/files/p43-tennenhouse.pdf
- Horvitz et al., attention-sensitive alerting, UAI 1999 — https://arxiv.org/abs/1301.6707
- Horvitz & Apacible, "Learning and Reasoning about Interruption", ICMI 2003 — https://www.microsoft.com/en-us/research/publication/learning-and-reasoning-about-interruption/
- Iqbal & Horvitz, disruption arc, CHI 2007（经 awesome-proactive-agents 引用）— https://github.com/tao-hpu/awesome-proactive-agents/blob/HEAD/README.md
- Deng et al., "Proactive Conversational AI", ACM TOIS 2025（经上同仓库引用）
- Packer et al., MemGPT, arXiv:2310.08560, ICLR 2024 — https://github.com/lin-guanguo/llm-memory-research/blob/HEAD/letta.research.md
- AWS Prescriptive Guidance, event-driven agentic AI — https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/event-driven-architecture.html
- Proactive agent landscape（社区整理，交叉验证后引用）— https://github.com/agentworkforce/proactive-agents/blob/HEAD/content/market/proactive-agent-landscape.mdx
- ChatGPT Scheduled Tasks — https://dataconomy.com/2025/10/27/openai-adds-scheduling-powers-to-chatgpt-with-new-tasks-feature/
- Glass box / explainability — https://medium.com/@monique_30228/explainability-by-design-why-ai-needs-to-show-its-work-in-2026-47949400be99 ；https://securityboulevard.com/2026/01/transparency-and-explainability-in-agentic-ai-decision-making/
