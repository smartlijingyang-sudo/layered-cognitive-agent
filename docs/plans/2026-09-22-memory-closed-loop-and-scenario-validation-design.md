# Agent 认知记忆闭环与多场景真实验证设计方案

## 状态
**Accepted — 2026-09-22**

> **一句话**：基于第一性原理彻底闭环 LCA Agent 的长期记忆与三位一体感知能力（感知自己、感知环境、感知用户），修复预过滤漏杀与环境盲区、补齐情景记忆（Episodic）自省落盘、接入多维相关性检索（LayeredRetrievalPolicy）、消灭 Prompt 呈现冗余，并建立 5 大场景确定性端到端回归测试套件。

**Extends & Refines**：
- [ADR-0244](file:///home/lichao/layered-cognitive-agent/docs/adr/0244-cognitive-memory-closed-loop-and-sandbox-convergence.md)（认知记忆闭环与沙箱收敛）
- [ADR-0247](file:///home/lichao/layered-cognitive-agent/docs/adr/0247-agent-memory-knowledge-layer.md)（Agent 记忆知识层：结构化知识与受治理工具）
- [ADR-0242](file:///home/lichao/layered-cognitive-agent/docs/adr/0242-assistant-creation-home-runtime.md)（Assistant Home 运行时与多层记忆布局）

---

## 0. 接任务前 7 问

1. **问题是什么？**
   生产与实测暴露记忆链路三大致命痛点：
   ① 预过滤静默拦截环境事实与偏好，未加载 `.env` 凭证，且 Jev 提问偏狭窄；
   ② 检索阶段将用户 query 直接废除（`del manifest, query`），退化为无序文件平铺；
   ③ 情景记忆从未落盘，Agent 无法感知自己过往步骤的行为与结论；Prompt 呈现双重冗余且 bootstrap 存在契约断裂。
2. **受影响的事实或契约是什么？**
   - 门禁协议：`FallbackMemoryFilter`、`TypeSafeMemoryFilter`、`RegexMemoryFilter`；
   - 存储契约：`AssistantMemory.update`、`AssistantMemory.retrieve`；
   - 提示词呈现契约：`UserProfileSection`、`ContextSection`、`assistant.bootstrap`；
   - 测试基准：`tests/scenario/memory/test_memory_closed_loop_scenarios.py`。
3. **唯一真值在哪里？**
   - 助理长期记忆真值源于 `{home}/memory/<layer>.json` 与 `{home}/USER.md`；
   - 检索结果与 Prompt 为只读投影，绝不反向替代事实；
   - 用户画像 `USER.md` 由系统根据活跃事实自动回填重建。
4. **改变哪个边界？**
   - L1 运行时门禁与存储边界（`infrastructure/memory/`）；
   - L2 提示词呈现边界（`plugins/prompts/` 与 `plugins/assistant/bootstrap/`）；
   - 测试平面（新增确定性 scenario 端到端套件）。
5. **现有 Protocol / ADR 能否表达？**
   能。完全继承 ADR-0244 的四层记忆拓扑与 ADR-0247 的结构化知识层定义，不另设平行机制。
6. **失败、重试、恢复和幂等语义是什么？**
   - 预过滤异常经断路器优雅降级至本地规则，100% fail-soft；
   - 记忆落盘严格走 `dedupe_key` 幂等与 `supersede` 版本退役；
   - 检索异常降级为空列表，不阻断认知主循环。
7. **如何验证？**
   - 单元测试覆盖预过滤、情景写入、相关性排序与 Prompt 去重；
   - 5 大端到端场景矩阵 100% 自动化测试通过；
   - `ruff check` 与 `git diff --check` 0 报错。

---

## 1. 架构边界与自治等级

### 1.1 责任边界清单（Mandatory Boundaries，AP-01）
- **Owns（本方案负责实现与重构）**：
  1. `FallbackMemoryFilter` 启动时自动加载 `.env` 凭证；
  2. TypeSafe Jev Noul 提问指导词拓展至环境事实与项目规则，阈值调优至 `0.50`；
  3. `RegexMemoryFilter` 扩充客观事实、环境配置与指示词库；
  4. `AssistantMemory.update()` 补齐 `MemoryLayer.EPISODIC` 记录（工具链执行自省）；
  5. `AssistantMemory.retrieve()` 接入 `LayeredRetrievalPolicy`，实现 `relevance × recency × importance` 排序与 Token 预算剪裁；
  6. `UserProfileSection` 专职画像；`ContextSection` 排除画像冗余项，解决双写问题；
  7. 修复 `assistant.bootstrap` 投影数据契约；
  8. 构建涵盖 5 大场景的确定性端到端回归测试套件。
- **Does NOT own（严格禁止越界修改）**：
  1. 禁止修改外层认知图与子图拓扑（`bundles/outer/phase_main.yaml`、`bundles/perceive/` 结构保持不变）；
  2. 禁止修改前端 UI 组件与 WebSocket 消息协议；
  3. 禁止绕过 C10 窄门与 C4 Reducer 单写不变量；
  4. 禁止更改存储物理介质（保持 JSON 纯文本可审计性）。

### 1.2 自治等级（Autopilot Ladder）
- **等级**：`DRAFT`（记忆核心逻辑重构，涉及感知流注入，需全套测试通过方可合并）。

---

## 2. 详细技术方案

### 2.1 预过滤与环境门禁升级
1. **凭证确定性加载**：
   在 `FallbackMemoryFilter.__init__` 中调用 `load_dotenv_if_present()`，消除进程级环境变量缺失问题。
2. **TypeSafe Noul 指导词重构**：
   ```python
   instructions = (
       "该用户陈述是否表达了应当被长期记住的个人身份角色、习惯偏好、"
       "项目指导方针、系统约束或环境配置？"
   )
   ```
   阈值从 `0.65` 下调至 `0.50`，覆盖偏好表述（实测 0.61）与环境规范。
3. **本地规则词表扩展**：
   `DEFAULT_MEMORY_TOKENS` 补充“记住、别忘、环境、配置、生产、服务器、数据库、端口、密码、约定、规范”等，保障断网与熔断时本地规则依然坚挺。

### 2.2 情景记忆（Episodic Memory）落盘
1. **触发契约**：
   当 `observation` 包含具体工具产出，或本轮经历多步工具链收敛时，在 `AssistantMemory.update` 中自动生成一条情景事实：
   - `layer`: `MemoryLayer.EPISODIC`
   - `content`: `f"在任务「{task_summary}」中执行工具 {tool_names}，达成结果: {result_summary}"`
   - `importance`: `0.7`
2. **容量上限**：
   `episodic.json` 维持最近 50 条事实的滚动窗口（FIFO），既供跨轮回溯，又防文件无限膨胀。

### 2.3 多维相关性检索闭环
1. **重构 `AssistantMemory.retrieve`**：
   彻底移除 `del manifest, query`。
2. **评分公式**：
   $$\text{Score} = \text{Relevance}(\text{Query}, \text{Content}) \times \text{Recency} \times \text{Importance}$$
   - 中文按字符重叠召回，英文按词集合重叠；
   - 结合时间戳衰减与重要性加权；
   - 严格在 `token_budget`（默认 2000 tokens）内按得分降序截断，将当前最相关的知识推向 Prompt 前端。

### 2.4 Prompt 纯净化呈现
1. **`UserProfileSection`**：渲染当前有效的用户身份（`IDENTITY`）与偏好（`PREFERENCE`）；
2. **`ContextSection`**：渲染客观事实（`FACT`）、情景动作（`EPISODIC`）与程序技能（`PROCEDURAL`）；
3. **互斥去重**：`ContextSection` 在组装时剔除已由 `UserProfileSection` 负责渲染的类别，消灭双重冗余。

---

## 3. 测试不变量与五大验证场景

### 3.1 核心测试不变量（Invariants to test，AP-02）
- `INV-ENV-LOAD`：`FallbackMemoryFilter` 必定加载 `.env`，未 export 时依然能读取 `TYPESAFE_API_KEY`；
- `INV-NOUL-COVERAGE`：偏好与环境类陈述经门禁判定 `should_extract=True`；
- `INV-EPISODIC-WRITE`：工具执行后必定生成 `episodic.json` 记录；
- `INV-RELEVANCE-ORDER`：`retrieve` 输出必须按相关度得分降序排序；
- `INV-PROMPT-NO-DUP`：`CONTEXT` 与 `USER_PROFILE` 的记忆条目交集严格为 0；
- `INV-SUPERSEDE-HYGIENE`：退役记录不可在活跃查询或 `USER.md` 中出现。

### 3.2 五大场景测试设计矩阵
1. **场景 1（用户画像与偏好演化）**：录入身份与偏好 → 次轮准确引用 → 偏好变更触发 supersede → USER.md 自动同步重建且无旧残留。
2. **场景 2（环境与客观规则感知）**：无主句环境规则（“生产数据库端口 5433，严禁删除表”）正确录入并在后续操作中作为约束被遵守。
3. **场景 3（自我感知与过往行为）**：执行工具任务后，次轮提问“你刚才帮我做了什么”，Agent 从情景记忆中精准召回自己的动作与结论。
4. **场景 4（意图相关性与预算剪裁）**：多领域记忆并存时，提问特定话题，仅高相关项被排序置顶，无关条目被 Token 预算自动剪裁。
5. **场景 5（受治理工具与风控删除）**：Agent 自主调用 `memory_search` / `memory_add`，删除未经确认时被严格拦截。
