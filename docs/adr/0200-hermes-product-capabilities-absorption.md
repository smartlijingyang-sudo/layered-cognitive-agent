# ADR-0200 — 吸纳 Hermes 产品能力：个人助理学习闭环与 Provider 槽

## 状态

**Proposed**（2026-09-06）

> **一句话**：迁入 Hermes 的 *产品闭环与可插拔缝*（background review-fork 学习、Curator 技能生命周期、ContextEngine 槽、toolset+check_fn、cron×skills、MemoryProvider 槽、write_approval）；**不迁** AIAgent 单体编排、把 Spine/循环热拔成社区插件、无闸自动落盘 skill、平行第二 CognitiveRuntime。用 LCA 的 Resolve→Compile→**RuntimeFacade**（[ADR-0199](0199-hermes-inspired-cognitive-plugin-convergence.md)）、Spine SSOT、ScopeKernel、0067 闸、0093 控制面、0187 AssistantHome、0189 包边界 **上位吸收与重构清理**。

**与 ADR-0199 分工（必读）**：

| 本 ADR（0200） | [ADR-0199](0199-hermes-inspired-cognitive-plugin-convergence.md) |
|---|---|
| Assistant **学什么、怎么定时、怎么策展** | Agent **怎么启动、插件怎么治理、怎么诊断** |
| review-fork / Curator / ContextEngine / MemoryProvider / no_agent | RunIntent / RuntimeFacade / Doctor / PluginOrigin / 分域 Registry |
| 依赖 0187 P0→P2 产品顺序 | Phase 1 可独立启动 |

平台层 Reject（central registry、AIAgent facade、Plugin Doctor 形状、import-time register）以 **ADR-0199 为准**；本 ADR 不重复论证。

**不 supersede**：0187 / 0167 / 0169 / 0067 / 0068 / 0069 / 0075 / 0076 / 0093 / 0189 / **0197** / **0199**。  
**交叉引用**：NousResearch/hermes-agent；[ADR-0199](0199-hermes-inspired-cognitive-plugin-convergence.md)；[adr-0190-extreme-plugin-organization.md](adr-0190-extreme-plugin-organization.md)（0189 Keep）。

**Follow-ups（诚实编号，禁止 mega 一次搬完）**：0200.1–0200.6（见 §8）。

---

## 0. 第一性原理：问题本质

| 痛点 | 根因 | 非根因 | LCA 杠杆 |
|------|------|--------|----------|
| 个人助理要持续学、定时跑、可进化 | 缺 *产品闭环*（observe→提案→闸→落盘→策展） | 「没有 Hermes 同款 loop」 | 0187 Home + SkillAcquirer + 0067 + 0093 |
| 难替换 / 难调试 | 角色糊包、注册无 Manifest、真值与投影混 | 「包数量不够」 | 0189 Def/Prov/Cons + 0076 替换测试 |
| 怕胖包 / 上帝对象 | 无分裂条件；学习/调度/循环同对象 | 「要抄 Hermes 目录」 | 0189 膨胀红线；kernel 闭集 |
| 压缩丢真 | 以 message list 为 SSOT，有损摘要当历史 | 「context 窗口太小」 | 0167 Spine 真值；压缩只动投影 |
| 自动写 skill 不安全 | write_approval 默认关；无 Artifact 闸 | 「模型不够聪明」 | 0067 + 默认 write_approval |

**删除条件（本 ADR 可废）**：若 0187.x / 0200.x 已落地且 CI 强制：学习默认 experiment、压缩不改 Spine、Curator 可卸、无第二 loop —— 本文件降为附录。

---

## 1. Hermes 是什么（吸收前先看清形状）

**公开定位**：Nous Research 的开源个人 Agent（`NousResearch/hermes-agent`）：持久会话网关、工具运行时、技能、记忆、定时任务、自改进闭环。文档入口见仓库 README / docs（agent-loop、tools-runtime、curator、memory、cron、plugins）。

### 1.1 运行时骨架（代码级）

| 层 | Hermes 现实 | LCA 对照 |
|----|-------------|----------|
| Facade | `run_agent.py` / `AIAgent` 聚合入口 | **RuntimeFacade**（ADR-0199）+ CognitiveRuntime；**禁止**再造 AIAgent 上帝门面 |
| 循环 | `conversation_loop` + `turn_*` 分文件，仍偏重 | Spine SSOT × thin control SM × ProjectionHost（**0169 Accepted** 五缝；0194 收敛） |
| 初始化 | `agent_init` / helpers / compressor 仍重 | Resolve→Compile→装配；压缩只动投影 |
| 工具 | import-time `registry.register`、AST 发现、toolsets、`check_fn` | Capability / Skill(0048) + Manifest；谓词进 Provider |
| 学习 | `background_review` fork + rubric；`skill_manage` | SkillAcquirer + 0067 Artifact 闸；默认 experiment |
| 策展 | Curator：active → stale → archived | 独立 Provider 包；可卸 |
| 记忆 | MEMORY.md / USER.md + MemoryProvider 插件（旁路增强，非替换） | Home 文件 SSOT + MemoryProvider 槽（0187） |
| 定时 | cron × skills；`no_agent`；递归守卫；可插调度器 | 0093 控制面 + Routine；禁止第二调度内核 |
| 插件 | tools / hooks / memory / context engine / platform adapters / skill taps | 0189 Def/Prov/Cons；kernel 闭集 |

### 1.2 Hermes 真正强的五件事（产品闭环，不是目录树）

1. **观察→提案→落盘→策展** 的学习闭环（review-fork + Curator）
2. **ContextEngine 可换槽**（压缩/组装策略可替换，循环不绑死）
3. **toolset + check_fn**（能力集合 × 运行时谓词）
4. **cron × skills × no_agent**（定时可走轻路径）
5. **MemoryProvider 旁路**（不推翻文件真值）

### 1.3 Hermes 不能照搬的形状

- `AIAgent` 级单体编排与重模块（init/helpers/compressor）
- 把 **Spine / 主循环 / ScopeKernel** 做成社区热拔插件
- `write_approval` 默认偏松（LCA 必须更严）
- 网关多平台适配作为 LCA 内核职责（G9 / 外部适配层已有边界）
- 以 message list 为唯一历史真值的压缩语义

---

## 2. LCA 现有杠杆（吸收锚点，禁止平行造轮）

| 能力 | ADR / 缝 | 吸收 Hermes 时怎么用 |
|------|----------|----------------------|
| Assistant 产品面 | **0187 Accepted**：Home 盘 SSOT、AssistantSpec、无新 loop | 学习产物、MEMORY/USER、技能目录落 Home；不另开 HermesHome |
| 技能与闸 | **0048 Skill** + **0067 Artifact/Acquirer** | review-fork 提案 → Artifact → 0067 闸 → 落盘；禁止无闸 skill_manage |
| Creator / 自进化 | **0067 / 0068 / 0069** | Hermes自改进映射为受闸进化，不映射为裸写文件 |
| 调度 / 例程 | **0093** | cron×skills、no_agent 轻路径挂 0093；禁止第二 Job 内核 |
| 观测 | **0167** | review-fork、Curator、压缩审计全部可观测；正常路径调用链可追 |
| 循环与投影 | **0169 Accepted**（LoopCursor·ProjectionHost·Persistence·Capture·CloseBarrier）；**0194** 收敛 | ContextEngine ≈ ProjectionHost / 组装策略槽，不改 Spine 真值；**禁止**再造 Hermes conversation_loop |
| 包边界 | **0189** | Curator / MemoryProvider / ContextEngine / tool predicate 一律 Def/Prov/Cons；Phase A 门禁先于搬迁 |
| Runtime 装配 | Resolve → Compile → **RuntimeFacade**（0199） | Hermes 插件发现映射为 Manifest 注册，不映射为 import-time 全局副作用 |

**硬规则**：吸收 = 语义迁入既有缝；若某 Hermes 概念找不到缝，先开 follow-up ADR 开缝，禁止先抄代码再找缝。

---

## 2.1 main 缝实况补丁（2026-09-06 缝映射）

> 来源：`/workspace/lca-hermes-seam-map.md`（WebFetch main，无 clone）。本补丁修正早期草稿的编号与「已落地」误判。

| 校正点 | 旧稿风险 | 正确锚点 |
|--------|----------|----------|
| AssistantAgent 编号 | 箱内 0178 | **main = 0187 Accepted**；0178 作废号 |
| 循环薄 SM | 写作「0168 路线」 | **0169 Accepted**（五缝）；**0194** 认知循环收敛 |
| Guard / 工具安全 | 易被当成待吸收 | **0197 Accepted**：Hermes ladder + DSH act guards 已编入 GateService/ToolGuard/LoopGuard/Convergence — **禁止平行 Guard 框架** |
| 事件总线 | 易与 Home EP 混淆 | **0180/0183/0185** 内核事件机制；与 0187 `assistant.*` EP **正交** |
| 0189 | 未进 main index | local Keep；Phase B=**skill**；勿占 0187 号 |
| 平台入口 | 易与 0200 产品能力混淆 | **0199** 已冻结 RuntimeFacade/Doctor；0200 只写产品 Provider 槽 |
| write_approval | 只说「比 Hermes 严」 | 0187 设计默认 **write_approval off**；本 ADR **Transform**：产品默认改为 **on**（或 evolve 路径强制闸）——与现状有意分歧，须在 0200.1/0187.x 显式决议 |
| 实现缺口 | 易当成「缝不存在」 | 0187 **PR-2…8** 仍在路上；0093 Phase1=register+manual fire；Timer→**0187.1**；GEPA→**0187.2** |

**与 0187 官方吸收顺序对齐（产品优先于新 ADR 切片）**：

1. **P0** Home + isolation + progressive skill（0187 PR-2…6）  
2. **P1** routines / 0093（含 no_agent 语义）  
3. **P2** evolve × write_approval 收严  
4. **并行** 0189.2 skill 包垂直切开（防 overlay+install+evolve 上帝包）

→ 本 ADR 的 0200.1–0200.6 **不得抢跑** P0；Curator/ContextEngine 等可在 P0 文档冻结后设计，代码跟在对应 PR 后。

**已 Reject 再强调（缝映射一致）**：新 embedded loop；ungated hot-load 进 live Context；Auto-ACTIVE / SKILL 正文进 spine；kernel 内嵌 scheduler；multi-channel Gateway 进 0187；平行 Guard 框架。

---

## 2.2 Hermes 深研补丁（2026-09-06 executor brief）

> 来源：`/workspace/hermes-absorb-brief.md`（docs + GitHub API；无 clone）。补 ADR 初稿未写满的 Keep/Reject。

### 追加 Keep（语义）

| Hermes | LCA 落点 | 备注 |
|--------|----------|------|
| **Footprint Ladder**（extend→CLI+skill→gated tool→plugin→MCP→core tool last） | 编码闸 + 0189 膨胀红线 | 防腰变粗；能力优先放边缘 |
| **Prompt stability / cache discipline** | ProjectionHost / prompt 组装不变式 | 系统提示中会话默认冻结；变更须显式用户动作或新 session；`pre_llm_call` **只注入不改写** system |
| **Skills progressive disclosure**（list→view→refs） | 0048 + 0187 D11 | 设计已有，产品化跟 0187 P0 |
| **delegate_task 隔离** + SubagentLifecycle 公 API | Worker/子会话；工具继承 fail-closed | 子体新鲜上下文；阻断 leaf 副作用工具（delegate/memory/cron 等按策略）；**不**抄 sync 编排 |
| **Hooks vs Middleware 分界** | 扩展总线 | Hooks：observe + inject；Middleware：显式 rewrite；禁投机挂勾 |
| **Platform-agnostic core** | 认知闭集 ⊥ Edge I/O | 与 Reject gateway 内核化一致 |
| **HERMES_HOME / profile 隔离** | 0187 Home | 一助理一状态根 |
| **Curator 永不自动删除**（archive+ledger+backup） | 0200.2 | consolidate 默认 opt-in（Hermes 默认 false） |

### 追加 Reject / Transform

| 项 | 裁决 |
|----|------|
| Sync-primary loop + ThreadPool 充并发 | **Reject**（与 LCA async/声明式 phase 争抢） |
| Agent-loop **特判拦截**工具（todo/memory/delegate… 绕过 registry） | **Reject** — 统一 Capability 分发 |
| MEMORY **硬字符帽**当主认知库（2.2k/1.4k） | **Reject as-is** — 保留「精选 always-on + 按需召回」分层，帽可配且不得当唯一店 |
| Lossy compress **作为唯一**上下文策略 | **Reject 唯一性** — 保留 ContextEngine 槽，可选引擎 |
| Process-global registry 无显式 dispose 作用域 | **Transform** → Manifest/装配生命周期 |
| Gateway 20+ adapter 巨面 | **Reject bulk** — 最多吸 Adapter ABC |
| 默认 compressor 巨模块形状 | **Reject 形状** — 只要 ABC 合同 |

### 与 §3 关系

§3.1–3.3 仍然有效；本表为 **增量**。冲突时：以 **0169/0187/0197 已 Accepted** 与 §2.1 产品顺序为准。

---

## 3. 决策（Keep / Transform / Reject）

### 3.1 Keep（语义保留，落 LCA 缝）

| Hermes 概念 | LCA 落点 | 不变式 |
|-------------|----------|--------|
| background review-fork + rubric | 旁路 Worker / Experiment 会话 → SkillAcquirer 提案 | 不得写主会话 Spine；默认不自动 Accepted |
| Curator 生命周期 | 独立 Provider：active|stale|archived | 可卸；策展策略可换；审计落 0167 |
| ContextEngine 槽 | ProjectionHost / ContextAssembly Provider | 只动投影与组装；禁止有损摘要回写 Spine |
| toolset + check_fn | Capability 集合 × 运行时谓词 Provider | 谓词失败 = 能力不可见/不可调；可测 |
| MemoryProvider | Home 旁路记忆增强槽 | 文件 SSOT 优先；Provider 可空 |
| cron × skills | 0093 Routine 触发 Skill / PlanTemplate | 单一控制面；递归/重入守卫 |
| no_agent 模式 | 0093 轻路径：无 LLM 或固定脚本步 | 明确声明；不可偷偷升级成全 agent |
| write_approval | 比 Hermes 更严的默认开闸 | 写 Home/技能/记忆必须过 0067 或显式人闸；**相对 0187 现状（默认 off）为有意收严** |
| Guard ladder / tool·loop guards | **已在 0197 Accepted** — 复用 GateService/ToolGuard/LoopGuard | **禁止**再造平行 Guard 栈；仅补 per-assistant overlay（若需要） |
| Footprint Ladder | 能力优先边缘；core tool 最后 | 写入编码闸 / 0189 评审 |
| Prompt stability（中会话 system 冻结） | Projection/prompt 组装不变式 | inject≠rewrite system；对齐 Hermes cache 纪律 |
| delegate 隔离（新鲜子上下文 + 阻断副作用工具） | Worker/子会话 + fail-closed 工具集 | 不吸收 sync AIAgent 子体编排形状 |

### 3.2 Transform（形状改写，禁止 1:1 目录拷）

| Hermes 形状 | 改写成 | 理由 |
|-------------|--------|------|
| import-time registry.register + AST 扫包 | Manifest + Definition 声明 + Provider 装配 | 可替换、可测、无隐式全局顺序 |
| AIAgent facade 聚合 | RuntimeFacade 装配图 + 显式端口（0199） | 反上帝对象；对齐 0189 |
| message-list 压缩当历史 | Spine 事件真值 + 投影压缩 | 对齐 0167/0169；可回放 |
| 社区插件热换 loop | kernel 闭集；插件只换 Provider | 护认知图/计划优势 |
| 默认松 write | 默认严 + experiment 隔离 | 安全与可删除性 |
| 多终端 backend 细节 | Terminal/Exec Provider 适配 | 不进认知内核 |

### 3.3 Reject（明确不迁）

1. 第二 CognitiveRuntime / 平行 HermesRuntime
2. 把 Spine、主循环、ScopeKernel、CommandEnvelope 做成可热拔社区插件
3. 无闸自动落盘 skill / 无 Artifact 的 skill_manage
4. 复制 gateway 全平台适配进 LCA 内核（留在边缘适配层）
5. 以能跑 Hermes demo 为合入标准（合入标准 = 缝清晰 + 可删除 + CI 门禁）
6. 胖域目录 / 角色糊包「先搬后拆」（违反 0189 Phase A）
7. 平行 Guard / ToolSafety 框架（**0197 已吸收 Hermes+DSH**）
8. Offline GEPA「现在就做」（仅 **0187.2** 扩展点）
9. Sync-primary loop / ThreadPool 充并发模型
10. Agent-loop 特判拦截工具（破坏统一分发）
11. 硬字符帽 MEMORY 当唯一主存
12. Process-global registry 无 dispose 作用域（须 Transform 为装配生命周期）

---

## 4. 目标架构（长远可维护的插件化形态）

### 4.1 一句话目标态

**一个认知内核（闭集）× 一组可替换 Provider（开集）× 一个 AssistantHome SSOT × 一条受闸学习闭环 × 一个调度控制面。**

Hermes 贡献的是开集上的产品闭环与槽位语义；LCA 贡献的是闭集上的认知图、计划、Spine、Scope 与工程纪律。

### 4.2 分层图（逻辑，非目录强制）

```
┌─────────────────────────────────────────────────────────┐
│  Edge：Gateway / Chat UI / Platform adapters（非内核）   │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Control：0093 Routines / Jobs（含 no_agent 轻路径）      │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Assistant Product：0187 Home + Spec + Skills + Memory   │
│    MemoryProvider(slot) │ Curator(slot) │ write_approval │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Runtime assembly：Resolve → Compile → RuntimeFacade（0199）│
│    Capability toolsets × check_fn predicates              │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  KERNEL CLOSED SET（不可社区热拔）                        │
│    Spine SSOT │ thin Loop SM │ ScopeKernel               │
│    CommandEnvelope │ single Manifest schema              │
│    ProjectionHost ← ContextAssembly/ContextEngine Provider│
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   Learning (旁路)                 Observability 0167
   review-fork → Artifact → 0067
```

### 4.3 设计模式（必须写进实现约束）

| 模式 | 用法 | 反模式 |
|------|------|--------|
| Ports & Adapters | Hermes 工具/记忆/压缩/策展 = Port；实现 = Adapter/Provider | 内核直接 import Hermes 模块 |
| Strategy | ContextEngine / Curator policy / check_fn | 在循环里写死 if-else 压缩 |
| Experiment / Fork | review-fork 只读主真值，写实验沙箱 | fork 直接 mutate 主 Spine |
| Gate / Acquirer | 一切持久化技能变更过 0067 | skill_manage 直写盘 |
| Capability Predicate | toolset 可见性由 check_fn 决定 | 注册了就能调 |
| SSOT + Projection | Spine/Home 文件为真；LLM 上下文为投影 | 压缩结果当历史 |
| Single Control Plane | 定时只走 0093 | cron 守护进程旁路 Runtime |
| Delete-by-date | 临时桥接必须 ADR + 删除日 | 「先跑通再删」无日期 |

### 4.4 保护 LCA 优势（不可被吸收冲掉）

1. **认知图 / Plan / Compile**：Hermes 无对等物；吸收不得弱化 Resolve→Compile。  
2. **Spine 可回放**：压缩与学习不得破坏事件真值。  
3. **职责边界**：0189 ROLE 注解与 CI warn → 后续 fail；禁止为赶功能糊包。  
4. **第一性原理闸**：编码代理仍须答本质/真值投影副作用/既有缝/删除条件。

---

## 5. 清理清单（该清的清：对齐 0189 + Hermes 吸收）

### 5.1 立即禁止新增

- 新的「个人助理 loop」或 HermesLikeAgent 门面类
- import-time 全局 register() 作为唯一发现机制
- 无 Manifest 的技能/工具落盘路径
- 默认关闭 write_approval 的配置预设（产品默认必须严）
- 在主会话线程内同步跑完整 review-fork（必须旁路）

### 5.2 应清理 / 应拆（发现即登记删除日）

| 对象类型 | 清理动作 | 删除条件 |
|----------|----------|----------|
| 把压缩结果写回历史真值的路径 | 改为只写投影；补回归测 | 回放测试全绿 |
| 上帝 facade（聚合学习+调度+循环+工具） | 按 0189 拆 Def/Prov/Cons | 替换测试证明可卸 |
| 无闸 skill 写入 helper | 改道 SkillAcquirer + 0067 | 无直接写盘调用点 |
| 平行 cron / 自建调度器 | 并入 0093 或标 deprecated | 单一控制面 |
| 文档中「抄 Hermes 目录即架构」表述 | 改为语义对照表 | 本 ADR Accepted 后 |
| 箱内过期编号草稿（如旧 0178 与 main 0187 冲突叙述） | 标注 superseded / 指向 0187 | 读者不再迷路 |

### 5.3 与 0189 Phase 对齐

- Phase A：只加 ROLE 注解 + CI warn；为 Curator/MemoryProvider/ContextEngine/Predicates 标 Provider；不搬目录。
- Phase B：垂直切开 skill（或经 0189.2b 的 llm）相关 Provider；学习闭环作为独立包边界验收。
- 任何「为了像 Hermes 而搬目录」→ Reject，除非 Phase A 门禁已过。

---

## 6. 不变式（CI / 评审可执行）

1. One Spine：主会话事件真值唯一；fork 只读或写沙箱。
2. One Home：助理持久态在 0187 Home；禁止第二 Home 根。
3. One Scheduler：定时与 no_agent 只经 0093。
4. One Gate：持久技能/记忆写入经 0067 或显式人闸；默认 approval=on。
5. Projection != Truth：ContextEngine 不得把有损摘要提交为 Spine 事件。
6. Kernel Closed：Spine / Loop SM / ScopeKernel / CommandEnvelope / Manifest schema 不在社区插件热拔集。
7. Providers Optional：Curator、MemoryProvider、ContextEngine 策略可空或可卸；内核仍可跑。
8. Observable：review-fork 起停、闸通过/拒绝、策展状态迁移、压缩策略 id 必须进 0167 可查询面。
9. Delete Condition：每个临时桥接带 ADR 编号 + 删除日；过期 CI warn。
10. No Second Runtime：禁止 CognitiveRuntime 平行实现「为了 Hermes 兼容」。

---

## 7. 落地阶段（诚实切片，禁止 mega PR）

### Phase 0 — 对齐与冻结（文档/门禁，0 行为变化）

- 本 ADR Proposed → 镜川 Keep/Reject 一轮（可选但推荐）
- 冻结 Reject 列表进编码代理闸（第一性原理检查表追加「Hermes 产品吸收」条）
- 确认与 [ADR-0199](0199-hermes-inspired-cognitive-plugin-convergence.md) 无平台层重复叙述
- 产出：语义对照表（Hermes 概念 → LCA 缝）进仓库 docs（可后置 PR）

**退出标准**：Reject 列表无争议；0187/0189/0169/0197 交叉引用正确；确认不与 0187 P0–P2 抢跑。

**顺序约束**：代码切片服从 §2.1 的 0187 P0→P1→P2；0200.x 是语义与包边界，不是另一条产品路线；**不得抢跑 ADR-0199 Phase 1 之前的平台入口统一**。

### Phase 1 — 0200.1 Review-fork 学习对齐（最小可用闭环）

- 旁路 experiment 会话：只读主 Spine/Home 快照
- 输出 Artifact 提案（技能草稿 / 记忆补丁），**默认不 Accepted**
- 人工或策略闸 → 0067 → 落 Home
- 0167：fork_id、rubric_id、gate_result 可查

**退出标准**：主会话零写入；一次完整 observe→提案→闸→落盘演示；失败可回滚。

### Phase 2 — 0200.2 Curator 生命周期

- Provider：active → stale → archived（策略可换）
- 与 0048 Skill 索引只读集成；不拥有 Spine
- 可卸：卸掉后技能仍可用，仅无自动策展

**退出标准**：状态机单测 + 替换测试（换策略 Provider）。

### Phase 3 — 0200.3 ContextEngine × ProjectionHost

- 将「组装/压缩策略」收束为 Provider 槽
- 禁止摘要回写 Spine；回放测试锁定
- 与 **0169** ProjectionHost 命名对齐（一篇小 ADR 或本 ADR 补丁）；勿再写「0168 路线」以免与历史编号混淆

**退出标准**：换压缩策略不改循环 SM；回放金样例稳定。

### Phase 4 — 0200.4 MemoryProvider 槽

- Home MEMORY/USER 为文件 SSOT
- MemoryProvider 旁路增强（检索/向量/摘要缓存），可空
- 写回仍走 write_approval + 0067

**退出标准**：无 Provider 时行为 = 纯文件；有 Provider 时可测增强且可卸。

### Phase 5 — 0200.5 toolset + check_fn 谓词

- Capability 分组（toolset）+ 运行时谓词
- 谓词失败：工具 schema 不可见且不可调用
- Manifest 声明谓词 id；禁止隐式全局勾子作为唯一机制

**退出标准**：谓词单测矩阵；与危险命令审批链对齐（可复用既有审批缝）。

### Phase 6 — 0200.6 no_agent Routine 轻路径

- 0093：Routine 可声明 execution_mode=no_agent|agent
- no_agent：固定步骤 / 纯 skill 脚本，不进入完整认知循环
- 递归守卫：Routine 不可无限触发自身

**退出标准**：两类 Routine 集成测；控制面仍唯一。

### 阶段依赖

```
Phase0 → Phase1 → Phase2
              ↘ Phase3（可与 2 并行，共享 Projection 纪律）
Phase1 → Phase4
Phase0 → Phase5（可早，但须 Manifest）
Phase0 → Phase6（依赖 0093 稳定）
```

---

## 8. Follow-ups 编号（禁止塞回本文件变 mega）

| ID | 标题 | 主要缝 |
|----|------|--------|
| 0200.1 | Review-fork × SkillAcquirer × 0067 | 学习闭环 |
| 0200.2 | Curator Provider 生命周期 | 技能策展 |
| 0200.3 | ContextEngine 作为 Projection 策略槽 | 0169 ProjectionHost |
| 0200.4 | MemoryProvider 旁路槽 | 0187 Home |
| 0200.5 | toolset + check_fn Capability 谓词 | 工具运行时 |
| 0200.6 | 0093 no_agent Routine | 控制面 |

若实施中发现「必须开新内核类型」—— **停**，新开 ADR，不得在 0200.x 偷渡。

---

## 9. 后果

### 9.1 正收益

- 个人助理具备 Hermes 级「能学、能定时、能策展」产品闭环，同时保住 LCA 认知图/计划/Spine。
- 学习与压缩有明确真值边界，降低静默腐化历史的风险。
- 插件化落在 Provider 开集，内核闭集可长期演进；对齐 0189。
- write_approval 默认更严，比上游 Hermes 更适合生产与团队规范。

### 9.2 代价

- 不能「clone Hermes 就宣称架构完成」；短期速度慢于抄目录。
- review-fork / Curator / ContextEngine 需多篇 follow-up，节奏受 0067/0093/0169 稳定度与 **0187 实现 PR** 约束。
- 编码代理与评审成本上升（更多不变式检查）。

### 9.3 风险与缓解

| 风险 | 缓解 |
|------|------|
| 偷渡第二 Runtime | Reject 列表 + CI 命名扫描 + 镜川评审 |
| 压缩写回 Spine | 回放金样例；Projection 写 API 收窄 |
| 无闸落盘回潮 | 默认 approval=on；禁止路径清单 |
| 0189 未完成就大搬迁 | Phase A 门禁；本 ADR Phase 依赖 |
| 编号冲突 | 0200 与 0199 分工已冻结；0187/0189 叙述以 main index 为准 |
| 把网关当内核 | Edge 层显式；G9 边界文档交叉引用 |

---

## 10. 决策记录（Proposed）

**Adopt（语义）**：Hermes 产品闭环与可插拔槽（§3.1）。  
**Adapt（形状）**：Manifest/Provider/RuntimeFacade（0199）/Spine 投影纪律（§3.2）。  
**Reject（形状与职责）**：第二 Runtime、热拔内核、无闸写、gateway 内核化（§3.3）。  
**Sequence**：§7 Phase 0–6；细节进 0200.1–0200.6。

状态升 Accepted 条件：

1. Phase 0 完成且编号确认  
2. 至少 0200.1 有可演示路径 + 0167 审计点  
3. 不变式 §6 写入编码闸或 CI 清单  
4. 与 0187/0189 无冲突叙述

---

## 附录 A — Hermes ↔ LCA 语义对照（速查）

| Hermes | LCA | 动作 |
|--------|-----|------|
| AIAgent / run_agent facade | RuntimeFacade 装配（0199） | Transform |
| conversation_loop / turn_* | thin Loop SM × Spine | Transform（不 1:1） |
| background_review | review-fork + Artifact | Keep→0200.1 |
| skill_manage | SkillAcquirer + 0067 | Transform（加闸） |
| Curator | Curator Provider | Keep→0200.2 |
| ContextEngine | Projection/ContextAssembly Provider | Keep→0200.3 |
| MEMORY.md / USER.md | 0187 Home 文件 | Keep |
| MemoryProvider | MemoryProvider 槽 | Keep→0200.4 |
| toolsets / check_fn | Capability 谓词 | Keep→0200.5 |
| cron / no_agent | 0093 Routine | Keep→0200.6 |
| plugins (tools/hooks/…) | 0189 Def/Prov/Cons | Transform |
| platform gateway | Edge adapters | Reject（入内核） |
| write_approval 默认松 | 默认严 | Transform |

## 附录 B — 参考来源

- GitHub: `NousResearch/hermes-agent`（docs: agent-loop, tools-runtime, curator, memory, cron, plugins；代码: run_agent / conversation_loop / registry）
- LCA ADRs: 0048, 0067–0069, 0075, 0076, 0093, 0167, 0169, 0187 AssistantAgent, 0189 极端插件化（local Keep）, **0197 Guard Stack（已 Accepted）**, 0194
- 缝映射全文：`/workspace/lca-hermes-seam-map.md`（main @ 2026-09-06）
- Hermes 深研 brief：`/workspace/hermes-absorb-brief.md`
- 相关产品形态对照：OpenClaw workspace；既有 AssistantAgent 吸收叙述（main 0187）

## 附录 C — 给编码代理的强制提问（落地任一 0200.x 前）

1. 问题本质是产品闭环还是又一个 loop？  
2. 真值 / 投影 / 副作用边界各是什么？  
3. 既有缝是 0187/0067/0093/0167/0189 中的哪一个？为什么不开新缝？  
4. 删除条件与日期？  
5. 是否触碰 kernel 闭集？若是 → 停，开新 ADR。

---

*ADR-0200 Proposed — 2026-09-06*
