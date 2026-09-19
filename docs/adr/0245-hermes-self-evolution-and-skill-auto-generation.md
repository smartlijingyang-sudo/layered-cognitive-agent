# ADR-0245 — Hermes 自我进化机制与 Skill 自动生成调研

## 状态

**Research — 2026-09-19**

> **一句话**：对 `~/.hermes/` 生产系统的全面调研，揭示了两套并行的 Skill 生成机制（`self_evolution` 实验模块 + `curator//learn` 生产机制）以及基于基因匹配的进化引擎，为 LCA 程序性记忆沉淀（ADR-0244）提供完整的参考实现蓝图。

**Informs**：
- [ADR-0244](0244-cognitive-memory-closed-loop-and-sandbox-convergence.md)（认知记忆闭环与程序性记忆沉淀）
- [ADR-0243](0243-assistant-skill-tool-isolation-config.md)（技能与工具 Home 驱动隔离）
- [ADR-0200](0200-hermes-product-capabilities-absorption.md)（Hermes 产品能力吸收）

---

## 背景

本 ADR 记录对 `~/.hermes/hermes-agent/` 生产系统、`~/wiki/` 文档库、`~/layered-cognitive-agent/` 以及 `~/.agents/skills/` 的多维度并行调研结论，聚焦于：

1. Agent 如何从执行轨迹自动结晶 Skill
2. 两套 Skill 生成机制的定位与质量差异
3. 进化基因库（EvoMap GEP 风格）的工程实现
4. 分层记忆 L0~L4 的数据结构与持久化策略
5. LCA/LobeHub 内置 Worker Agent 的 Skill 写入协议

---

## 一、整体架构：五层递进的自进化系统

```
层次0  基因层   GeneStore        — 遇到特定信号时触发预设进化策略
层次1  结晶层   SkillCrystal     — 成功任务 SOP 化，固化为可复用技能
层次2  记忆层   MemoryLayers     — L0~L4 跨会话知识积累
层次3  元层     SkillFactory     — AI 主动观察并生成新 SKILL.md
层次4  框架层   mercury-agent    — 下一代 Agent 架构探索（新记忆抽象）
```

**调研时实际运行数据**：
- 已积累 **125 个结晶技能**，90+ 模板文件
- L1 洞察索引 **1129 行**
- 进化日志（`evolution_log.jsonl`，34KB）覆盖 2026-04-21 ~ 2026-04-28

---

## 二、两套并行 Skill 生成机制

### 2.1 机制 A：`self_evolution` 模块（实验性）

位置：`~/.hermes/hermes-agent/self_evolution/`

通过**自动补丁**集成到 `run_agent.py`，每次对话结束后非阻塞触发：

```python
self._evolution_engine.process_task_result(
    task_id=self.session_id,
    task_description=user_message[:500],
    execution_trace=execution_trace,  # 工具调用序列
    result=final_response[:1000],
    success=True/False
)
```

**成功路径 → 技能结晶**（触发条件：`success=True AND len(trace) >= 2`）：

```
执行轨迹
  → skill_id = MD5(task_description)[:12]
  → tool_sequence 提取（工具名 + args 模板）
  → sop_steps 生成（编号步骤列表）
  → trigger_patterns 提取（长度>3的词，最多10个）
  → tags 打标（文件操作/终端命令/网络/搜索）
  → 触发词重叠≥3 → 合并已有技能
  → 写入 ~/.hermes/self_evolution/skills/templates/<id>.json
  → 同步 L3 + 更新 L1 索引
```

**失败路径 → 基因进化**：

```
_extract_error_signals()
  → GeneStore.select_gene(signals, category='repair')  # 匹配度≥30%
  → _generate_evolution_suggestion()
  → record_event() → events.jsonl
  → 存储失败模式到 L2
```

> **已知问题**：当前实现将用户每条消息都当作任务结晶，`min_trace_length=2` 阈值过低，导致"看看启动了 ccs 了吗"等调试消息也被结晶为 Skill，产生大量低价值记录。**建议提高阈值（≥5）并增加语义过滤。**

### 2.2 机制 B：`curator + /learn` 机制（生产级）

| 组件 | 文件 | 触发方式 |
|------|------|---------|
| `/learn` 命令 | `agent/learn_prompt.py` | 用户主动执行 |
| 后台 Curator | `agent/curator.py` | 空闲≥2h 且距上次≥7天 |
| Skill 维护工具 | `tools/skill_manager_tool.py` | LLM 调用 |

**`/learn` 生成流程**：

```
/learn <描述/URL/目录>
  → build_learn_prompt() 注入 AUTHORING_STANDARDS
  → Agent 收集素材（read_file / web_extract / search_files）
  → 小型素材 → 单个 SKILL.md (≤200行)
  → 大型素材 → knowledge-base 布局（lean SKILL.md + references/*.md）
  → 检查相似 skill（skills_list / skill_view）
  → 存在  → skill_manage(action="patch")
  → 不存在 → skill_manage(action="create")
  → 写入 ~/.hermes/skills/<category>/<name>/SKILL.md
```

**AUTHORING_STANDARDS 关键约束**：
- `name`: lowercase-hyphenated，≤64 chars
- `description`: ≤60 chars（截断后仍能路由）
- `author`: 永远写 `"Hermes"`（防隐私泄露）
- 大型素材必须使用 knowledge-base 布局

**Curator 老化管理**：
- 30天不活跃 → `STATE_STALE`
- 90天不活跃 → 移入 `.archive/`（可恢复）
- LLM 整合 pass（可选）：找前缀集群 → 合并为伞形技能（umbrella skill）
- 安全规则：只能 archive 不能 delete；pinned/cron 引用技能跳过

### 2.3 两套机制对比

| 维度 | `self_evolution` | `curator + /learn` |
|------|------------------|--------------------|
| 触发 | 每任务自动 | 用户命令 + 后台定时 |
| 输出格式 | JSON dataclass | 标准 SKILL.md + references/ |
| 存储位置 | `~/.hermes/self_evolution/skills/` | `~/.hermes/skills/<category>/` |
| Skill 质量 | 低（无语义过滤） | 高（遵循 AUTHORING_STANDARDS） |
| 失败学习 | ✅ 基因匹配进化建议 | ❌ 无 |
| 生产成熟度 | 实验性 | 生产级核心功能 |

---

## 三、进化基因库（GeneStore）

内置 4 个基因，每个基因结构：`signals_match + strategy + constraints + validation`

| 基因 ID | 类别 | 触发信号 | 作用 |
|---------|------|---------|------|
| `hermes_repair_from_error` | repair | error/exception/traceback | 提取错误→最小可逆修复→固化知识 |
| `hermes_optimize_tool_usage` | optimize | 重复操作/低效 | 分析工具序列→合并批量操作 |
| `hermes_crystallize_skill` | crystallize | success/task_completed | 提取轨迹→SOP→存入技能库 |
| `hermes_context_optimize` | optimize | context_full/token_limit | 识别关键上下文→压缩归档 |

**安全约束**（`constraints` 字段）：禁止 `rm -rf`、`DROP TABLE` 等高危操作。

---

## 四、分层记忆系统 L0~L4

```
L0  元规则（5条）   ~/.hermes/self_evolution/memory/L0_meta_rules.json
    — 不可变行为约束，check_rule() 每次操作前自动触发
    — rule_safety_first / rule_preserve_user_data / rule_log_everything
    — rule_crystallize_success / rule_evolve_from_failure

L1  洞察索引（1129行）  L1_insight_index.json
    — 快速路由，title/tags/summary 文本匹配，search_index() 检索

L2  全局事实            L2_global_facts.json
    — 稳定事实积累（success_patterns / failure_patterns），去重存储

L3  技能存储            L3_skills/ 目录
    — 每个结晶技能一个 JSON 文件，含 sop_steps / tool_sequence / trigger_patterns

L4  会话归档            L4_session_archives/ 目录
    — 归档会话（最后50条消息 + 自动摘要），search_archives() 支持关键词检索
```

**用户侧三文件架构**（与自进化模块正交）：

| 文件 | 路径 | 容量限制 | 性质 |
|------|------|---------|------|
| SOUL.md | `~/.hermes/SOUL.md` | 无 | 宪法（只读，用户编写） |
| MEMORY.md | `~/.hermes/memories/` | **2,200 字符** | 动态工作笔记（Agent维护） |
| USER.md | `~/.hermes/memories/` | **1,375 字符** | 用户画像（Agent维护） |

**Flush 机制**：每次会话开始以**冻结快照**注入上下文，中途写入下一会话才生效。

---

## 五、LCA/LobeHub 内置 Worker Agent 协议

这是本次调研的最重要发现，来自 `~/layered-cognitive-agent/` vendored 的 LobeHub 实现：

### 5.1 四个内置 Worker Agent

```
用户对话结束
    │
    ├──→ [self-reflection]（同turn即时）
    │     高置信度 + 低风险 → writeMemory / createSkillIfAbsent / replaceSkillContentCAS
    │     不确定            → recordSelfFeedbackIntent（降级给 nightly）
    │
    ├──→ [skill-management]（同turn，反馈路由到 skill 域时）
    │     每次最多一次写 → createSkillIfAbsent / replaceSkillContentCAS
    │
    ├──→ [self-feedback-intent]（异步）
    │     处理 agent 在对话中声明的自反馈意图
    │
    └──→ [nightly-review]（每日一次，mini 模型，低成本）
          读取有界摘要 → 批量 skill 更新 / 创建 proposal（需人工审批）
```

### 5.2 SkillMaintainer API（系统级，不对用户暴露）

| API | 功能 |
|-----|------|
| `createSkillIfAbsent` | 不存在时创建（需 name/title/description/bodyMarkdown） |
| `replaceSkillContentCAS` | CAS 乐观锁更新（防并发冲突，须传 baseSnapshot） |
| `listSkills` | 列出 managed skills |
| `getSkill` | 读取 skill bundle |
| `renameSkill` | 重命名 + 同步 frontmatter |

### 5.3 Nightly Review 证据强度要求

- 工具活动单独**不能**触发 skill 创建/细化
- 必须结合 `document / feedback / topic / receipt` 证据
- 每个非 noop 行动必须附 `policyHints`：`evidenceStrength + userExplicitness + sensitivity + mutationScope`

### 5.4 安全闸门分级

| 行动类型 | 处理方式 |
|---------|---------|
| 非结构性全文 refine（skill fresh 时） | ✅ 自动执行 |
| 补充性 create（不存在且证据充分） | ✅ 自动执行 |
| 结构性/破坏性变更 | 🔐 创建 proposal，等待人工审批 |
| 路径/激活变更、split/merge/delete | 🔐 创建 proposal，等待人工审批 |

### 5.5 Skill 名称规范

- `name` 必须是 slug 格式：`小写ASCII + 数字 + 连字符`
- 人类可读标签放 `title` 字段（与 name 分离）

---

## 六、渐进式 Skill 加载（Token 效率）

```
元数据层  始终在上下文  name + description，~100词
SKILL.md  触发时加载    理想 < 500行
附属资源  按需加载      scripts/ references/ assets/
```

---

## 七、元技能：SkillFactory

位置：`~/.hermes/skills/meta/skill-factory/SKILL.md` + `plugins/skill_factory.py`（15KB）

**工作阶段**：
1. **静默观察**：追踪重复动作、多步工作流、工具组合模式
2. **触发条件**：重复≥2次 / 用户说"保存为技能" / 会话结束时
3. **命令接口**：`/skill-factory propose|list|status|queue|save|clear`

---

## 八、Proactive Agent 进化行为守则

**ADL Protocol（防漂移）**：
- 禁止为显示智能增加复杂度
- 禁止无法验证的改变
- 优先级：**稳定性 > 可解释性 > 可复用性 > 可扩展性 > 新颖性**

**VFM Protocol（价值优先修改）加权评分**：

| 维度 | 权重 |
|------|------|
| 高频使用 | 3x |
| 减少失败 | 3x |
| 减轻用户负担 | 2x |
| 节省 token 成本 | 2x |

**阈值**：加权分 < 50 不执行改变。

黄金原则：`"Does this let future-me solve more problems with less cost?"`

---

## 九、对 LCA 架构的影响与建议

### 9.1 可直接采纳的设计

1. **CAS 乐观锁写 Skill**：防并发冲突，强制传 `baseSnapshot` + `idempotencyKey`
2. **证据强度要求**：工具活动单独不触发 skill 变更，必须结合 feedback/topic 证据
3. **人工审批 proposal**：结构性/破坏性变更不自动执行
4. **nightly-review mini 模型**：低成本异步处理，不占用主模型 token budget
5. **渐进式三层加载**：元数据层常驻 + SKILL.md 触发加载 + 附属资源按需

### 9.2 需规避的问题

1. **`min_trace_length=2` 过低**：应提高到 ≥5，并增加语义过滤（排除调试类问题）
2. **两套 skill 存储路径不统一**：`self_evolution/skills/` vs `skills/<category>/` 容易混淆
3. **MEMORY.md 2200 字符上限**：重复工作流必须迁移为 Skill，否则会被自动压缩丢失
4. **Flush 快照延迟**：中途写入的记忆下一会话才生效，设计长会话时需考虑

### 9.3 与 ADR-0244 的对接点

- **程序性记忆沉淀** → 对应 Hermes SkillCrystal 的 `success + trace≥N` 结晶逻辑
- **认知主图反思** → 对应 `self-reflection` Worker Agent 的同turn即时写入
- **夜间批处理** → 对应 `nightly-review` mini 模型的有界摘要批量处理
- **L0 元规则** → 对应 LCA 的 hardcoded invariants（安全第一、保护数据、完整记录）

---

## 关键文件速查

| 文件路径 | 大小 | 作用 |
|---------|------|------|
| `~/.hermes/hermes-agent/self_evolution/evolution_engine.py` | 11.7KB | 进化引擎主控 |
| `~/.hermes/hermes-agent/self_evolution/gene_store.py` | 9.7KB | 基因存储与匹配 |
| `~/.hermes/hermes-agent/self_evolution/skill_crystal.py` | 11.9KB | 技能结晶逻辑 |
| `~/.hermes/hermes-agent/self_evolution/memory_layers.py` | 11KB | 分层记忆系统 |
| `~/.hermes/hermes-agent/agent/learn_prompt.py` | — | /learn 命令 Prompt 构造 |
| `~/.hermes/hermes-agent/agent/curator.py` | — | 后台 Skill 维护编排器 |
| `~/.hermes/self_evolution/genes/genes.json` | 3.3KB | 4个进化基因定义 |
| `~/.hermes/self_evolution/skills/skills_index.json` | 174KB | 125个结晶技能索引 |
| `~/.hermes/self_evolution/memory/L1_insight_index.json` | 42KB | 洞察索引（1129行） |
| `~/.hermes/self_evolution/evolution_log.jsonl` | 34KB | 进化事件日志 |
| `~/.hermes/plugins/skill_factory.py` | 15KB | 技能工厂插件 |
| `~/.hermes/SELF_EVOLUTION_SUMMARY.md` | 8.6KB | 系统总结 |
| `~/.hermes/AUTO_INTEGRATION_COMPLETE.md` | 7.3KB | 集成报告 |
| `~/wiki/hermes-agent-完全指南.md` | 325行 | 完整用户手册 |
| `~/wiki/hermes-记忆系统正确打开方式.md` | 166行 | 记忆系统指南 |
