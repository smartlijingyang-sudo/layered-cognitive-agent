# ADR-0265：系统提示装配顺序契约（stable→volatile）

## 状态

**Proposed — 2026-10-02**

> **一句话**：把"系统提示里各 section 按什么顺序出现"从模板实现细节升为契约——顺序即设计：越靠前越稳定（宪法层），越靠后越易变（行为规则/运行上下文）；profile 扩展只许在带内增删，不许打乱带序。ADR-0255 §1.1 装配顺序的 LCA 落地提案。

## 0. 背景：生产 Muse 的装配顺序

ADR-0255 §1.1 记录了生产实例每 turn 的固定装配顺序：[1]系统指令层 → [2]Runtime 行 → [3]Developer 时间戳 → [4]Standing 文件注入 → [5]Goals 状态 → [6]工具定义 Schema → [7]对话历史 → [8]后台 Handoff → [9]本 turn 用户消息。**顺序本身是设计**：越靠前的越稳定、越靠后的越易变；易变层绝不污染稳定层。抄作业要点：系统指令是"宪法"（发版级稳定），standing 文件是"法律"（文件级热更新）——两层分离是热更新的前提。

## 1. LCA 现状（实证，2026-10-02）

系统提示的 section 顺序由 `lca/plugins/prompts/template_provider.py::_builtin_templates()` 决定，`SectionManifestPromptAssembler` 按模板顺序逐段渲染。`react_prompt` 的实际顺序（19 段）：

| # | section | kind | 可选 | 备注 |
|---|---|---|---|---|
| 1 | role | pure | 否 | |
| 2 | goal | pure | 否 | |
| 3 | backstory | pure | 否 | 含 SOUL.md 点名守卫（0261 C2） |
| 4 | vocal_contract | stateful | 是 | ADR-0248 gated 声带契约 |
| 5 | current_date | stateful | 否 | |
| 6 | tools | stateful | 否 | |
| 7 | cloud_sandbox | stateful | 否 | |
| 8 | available_skills | pure | 否 | |
| 9 | activated_skills | stateful | 否 | |
| 10 | task | stateful | 否 | |
| 11 | context | stateful | 否 | |
| 12 | react_workflow | pure | 是 | fallback "" |
| 13 | react_tool_usage_guidelines | pure | 是 | fallback "" |
| 14 | user_profile | stateful | 是 | |
| 15 | home | stateful | 是 | |
| 16 | autonomous_presets | stateful | 是 | |
| 17 | memory_retrieval | stateful | 是 | 承载 ADR-0260 C2 检索义务决策树 |
| 18 | developer_timestamp | pure | 是 | fallback "" |
| 19 | runtime_env | pure | 是 | fallback "" |

代码里已有对齐意图的痕迹：`adr0255_tail = memory_retrieval_ref + developer_timestamp_ref + runtime_env_ref`——作者命名时明确想过 0255，但只对齐了"尾部三段"，没对齐带序原则。`routing_prompt` / `hierarchical_prompt` 在 react 基础上追加 team 段，尾部三段共用同一 `adr0255_tail`。

## 2. 实证缺口（与 0255 §1.1 的三处偏离）

### D1 时间锚点尾置且可选

0255 把 Runtime 行 [2] 与 Developer 时间戳 [3] 放在系统指令层之后、standing 之前——"现在"的可信锚点是稳定的前置块。LCA 的 `developer_timestamp` 在第 18 位、可选（fallback ""），`runtime_env` 在第 19 位、可选；`current_date` 虽在第 5 位且必需，但"now 唯一可信来源"被拆成两处。尾置有 recency 加权的合理性，但**可选**意味着某些 profile 下时间锚点整体缺席——与 ADR-0259 C1（developer 时间戳是"now"唯一可信来源，不变量）的信任语义存在张力：信任语义已立，位置语义未立。

### D2 standing 落在 tools 之后

0255 的顺序是 standing [4] → 工具 Schema [6]；LCA 是 tools [6] → user_profile/home [14–15]。standing（USER CONTEXT 热更新通道，0255 §1.5"文件即热更新通道"）在 LCA 里被工具 schema 隔在宪法层之后。按 stable→volatile 原则：工具 schema 是发版级稳定，standing 是 turn 级可变——live 的用户配置应先于工具 schema，两者相对顺序反了。

### D3 行为规则段可整体缺席

`react_workflow` / `react_tool_usage_guidelines` / `memory_retrieval` 均为可选（fallback ""）。`memory_retrieval` 承载 ADR-0260 C2 的检索义务决策树——模板级可选意味着检索义务在某些 profile 下整段消失，这是 0260 未覆盖的**模板层盲区**（0260 只处理了 `_has_home` 渲染条件的代码层盲区）。

## 3. 契约

### C1 带序约束（band ordering），不锁死精确顺序

系统提示 section 必须落在以下带内；带内顺序可调，跨带不许逆序：

- **B1 宪法层**：role / backstory（身份与人格，永不后移）
- **B2 任务目标**：goal（本 run 要什么）
- **B3 时间锚点**：current_date / developer_timestamp（"now" 的可信来源，位置固定、可合并）
- **B4 用户 live 配置**：user_profile / home / autonomous_presets（USER CONTEXT 热更新通道）
- **B5 能力面**：tools / cloud_sandbox / available_skills / activated_skills
- **B6 运行上下文**：task / context
- **B7 行为规则**：react_workflow / react_tool_usage_guidelines / memory_retrieval / vocal_contract
- **B8 环境尾注**：runtime_env（per-turn 固定格式信息，可置尾）

### C2 扩展纪律

profile YAML 扩展模板（"the default surface Profile YAML extends"）只许在带内追加，或把可选段改为必需；不许：① 把新段插到 B1 之前；② 把 B4/B7 的段移到 B5 之前（打乱 live→stable 关系）；③ 把 B3 的段改为可选。违反 → 模板加载期报错（fail-fast，与 ADR-0256 的 wiring-time fail-fast 同一思想）。

### C3 可选段的语义分级

可选只许用于"能力缺席"（如无 team 时 teammates 为空），不许用于"义务缺席"：承载契约义务的段（`memory_retrieval` ← ADR-0260 C2 检索义务）不得为可选。若某 profile 确实不需要该义务，走显式的 profile 级豁免声明（留痕），而不是静默 fallback ""。

## 4. 待拍板

1. **带序 vs 精确顺序**：C1 只约束带（给 profile 扩展留空间），还是把三模板的精确段序锁死为单测快照？精确锁死维护成本更高，但能防止渐进漂移。
2. **D1 时间锚点**：`developer_timestamp` / `runtime_env` 移到 B3（`current_date` 旁）并改为必需，还是维持尾置（承认 recency 加权的设计意图）？若维持尾置，需在文档中明确写下设计理由。
3. **turn 级装配**：本契约只覆盖系统提示内部；0255 §1 的完整 9 块（系统提示/历史/handoff/用户消息的 turn 级顺序）是否另立 ADR？LCA 的 turn 级装配分散在 run 组装链路中，尚未做顺序审计。
4. **D3 的豁免形态**：profile 级豁免声明放在 profile YAML 里，还是单独的豁免注册表？

## 5. 验收

- **T1**：三模板（react/routing/hierarchical）的渲染 section 顺序单测，带序断言（B1–B8 不许逆序）；
- **T2**：profile 扩展在 B1 之前插段 → 模板加载期抛错；
- **T3**：`memory_retrieval` 在默认三模板中为必需段（或带显式豁免声明）；
- **T4**：routing/hierarchical 的 team 段追加不改变 B1–B5 的相对顺序。

## 6. 与现有 ADR 的关系

- **ADR-0255 §1.1**：本 ADR 的对齐基准（stable→volatile 原则、宪法/法律两层分离）。
- **ADR-0259**：C1 已立 developer 时间戳的信任语义（"now" 唯一可信来源）；本 ADR 补位置语义（D1）。
- **ADR-0260**：C2 检索义务决策树；本 ADR 指出其模板层盲区（D3），C3 与其呼应。
- **ADR-0258**：standing 热更新与压缩豁免；B4 的 live 配置定位与 0258 一致（standing 永不进压缩流、每 turn 重注）。

---

## 7. 决策记录（2026-10-02，李超授权 Athena 按 muse 思想裁决）

1. **带序 vs 精确顺序：带序（维持 C1），不锁死精确快照**。理由：精确快照会在带内合法变更（如 T4 认可的 team 段追加）时产生 toil 式失败——防不住真正的违规，只增加维护成本。可精确判定的违规是"跨带逆序"，C2 的加载期 fail-fast 已经覆盖它；T1/T4 的带序断言就是验收。fail-closed 用在可精确判定处，带内顺序不属于。
2. **D1 时间锚点：`developer_timestamp` 移入 B3 并改为必需；`runtime_env` 留 B8**。理由：ADR-0259 C1 已立"now 唯一可信来源"为不变量——不变量不能是可选的，可选的时间锚点等于没有时间锚点，这是必改项；位置上 stable→volatile 原则要求可信锚点前置，recency 加权只是模型行为假设，不能凌驾契约不变量。`runtime_env` 是环境尾注（B8 的语义正是"per-turn 固定格式信息"），不是信任锚点，留在尾部。实现项：react 模板第 18 位前移 + 去 fallback，转 tests/quality 落地。
3. **turn 级装配：先做顺序审计，不直接立 ADR**。理由：LCA 的 turn 级 9 块顺序从未实证审计过——为没测量过的东西立法是 premature legislation（YAGNI）。裁决是"审计先行"：arch lane 下一轮输出 run 组装链路 9 块顺序实证，有缺口再立 ADR。已记 backlog 跟踪，不是丢弃。
4. **D3 豁免形态：profile YAML 内声明**。理由：豁免是 profile 的属性，放一起读一次看全；独立注册表是第二个 SSOT，会漂移（注册表与 profile 不一致时以哪个为准？——与 ADR-0254 选 A 同一理由：无裁决机制的同步是复杂度而非机制）。审计需求用工具扫描所有 profile YAML 的豁免声明满足（机制，不人肉对表）。豁免声明须结构化（义务项、理由、时间），C2 加载期校验覆盖。

5. **T1 带倒置的归属（arch lane 解释注记，2026-10-03；非新裁决，是 §7① 的解释应用）**。背景：`tests/plugins/prompts/test_adr0265_assembly_order.py` 的 T1（3 红，预期红契约钉）断言带序不逆序，2026-10-03 基线 `95097d756` 实测 `_builtin_templates()` 有 4 处相邻倒置：goal(B2)→backstory(B1)、vocal_contract(B7)→current_date(B3)、react_tool_usage_guidelines(B7)→user_profile(B4)、skill_duty(B7)→developer_timestamp(B3)。裁决：测试的 `_SECTION_BANDS` 解释**忠实于 C1 原文 + §7①**（"跨带逆序是可精确判定的违规，T1 带序断言就是验收"），**不是测试过度解读**；4 处均为模板侧对 C1 的真实违反。完备性：相邻对检查在数学上等价于全局带序单调（序列单调非减 ⟺ 所有相邻对非减），4 处即全部违规、无遗漏。D2（standing 的 B4 段落在 tools 等 B5 段之后）在 §7 未单独立项，但被 §7①"跨带逆序即违规"覆盖——本注记明确计入：guidelines(B7)→user_profile(B4) 正是 D2 在相邻检查中的表现，完整修复必须把 B4 整组（user_profile/home/autonomous_presets）前移到 tools 之前，而非只挪 guidelines。skill_duty(B7)→developer_timestamp(B3)：§7② 落地（developer_timestamp 前移 B3 转必需）后自然消除，不单独修。处置：① T1 三红继续作为预期红契约钉保留（钉的是已裁决契约的未落地部分，名实相符）；② 带序重排提案转 quality lane（**行为变化**：system prompt 字节变化，需 prompt 相关测试全回归；目标顺序见下）；③ tests lane 后续：重排落地后 T4 的 `react_b1_b5[:4]` 哨兵断言同步更新为 `["role", "backstory", "goal", "current_date"]`，T1 docstring 中"memory_retrieval(B7)→developer_timestamp(B3)（D1）"一行已过期（现为 skill_duty 相邻）顺手更新。目标顺序（react_prompt，供 quality lane 落地；routing/hierarchical 的 team 协作段未定带，重排时保持其相对位置、且 B1–B5 相对顺序不得变——T4 约束）：role(B1) → backstory(B1) → goal(B2) → current_date(B3) → developer_timestamp(B3，必需) → user_profile(B4) → home(B4) → autonomous_presets(B4) → tools(B5) → cloud_sandbox(B5) → available_skills(B5) → activated_skills(B5) → task(B6) → context(B6) → react_workflow(B7) → react_tool_usage_guidelines(B7) → memory_retrieval(B7) → skill_duty(B7) → vocal_contract(B7，ADR-0248 gated 可选语义不变) → runtime_env(B8)。注意 routing/hierarchical 用"react 基座[:13] + team 段拼接"组装，重排后切片含义变化，quality lane 落地时一并处理。

6. **§7 落地注记（arch lane，2026-10-03 08:09；实测验证，非新裁决）**。① 带序重排（§7①）已落地：quality lane commit `609d25a3c`（merge `d27457a13`）。本轮实测 `_builtin_templates()`：react 20 段与第 5 条注记的目标顺序**逐段一致**；routing 24 段 / hierarchical 23 段：team 段保持"react 基座块之后、尾段（memory_retrieval→skill_duty→vocal_contract→runtime_env）之前"的相对位置，B1–B5 相对顺序不变——与第 5 条注记要求一致。② D1 时间锚点（§7②）已落地（commit `07193338a`，merge `3294e2c3c`，2026-10-03 06:09 轮）：`developer_timestamp` 前移 B3 且必需；第 5 条"§7② 落地后 skill_duty→developer_timestamp 倒置自然消除"预言兑现。③ T1：3 预期红契约钉 → **全绿**（quality 轮 `tests/plugins/prompts/` 45 passed / 2 failed，T1 三例绿）——第 5 条处置①（"继续预期红"）已过期，划掉。④ T4：现红**仅**卡在过期哨兵行 `react_b1_b5[:4]==["role","goal","backstory","current_date"]`，实测模板已是 `role,backstory,goal,current_date`；交 tests lane 把哨兵翻转为 `["role","backstory","goal","current_date"]`（纯卫生动作），T4 实质断言（routing/hierarchical B1–B5 顺序与 react 一致）quality 轮已独立脚本验证通过。⑤ 诚实边界：system prompt 字节顺序变化已发生（行为变化），quality 轮落盘消息已明示，非 refactor 包装。
