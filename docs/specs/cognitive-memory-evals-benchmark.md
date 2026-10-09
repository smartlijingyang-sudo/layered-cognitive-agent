# 认知记忆 7 大维度 28 项核心场景双轨基准评测规范 (Cognitive Memory Evals Benchmark)

本文档定义 LCA 认知智能体长期记忆与知识图谱的评测基准。对齐用户提出的 7 大能力维度与 28 项核心实测场景，采用**双轨评测模型（Two-Track Evaluation）**进行自动化与半自动化验收。

---

## 1. 评测方法论：双轨分流模型 (Two-Track Evaluation)

| 轨道 | 范围与目标 | 评测方式 | 达标红线 | 对应测试套件 |
|---|---|---|---|---|
| **轨 A：确定性代码不变量 (Deterministic Invariants)** | 涉及记忆生命周期、双时间线、取代链、模态过滤、敏感遮蔽、避坑红线、目录隔离等物理硬契约 | `pytest` 自动化单元/集成测试，精确 assert 断言 | **100% 必须通过**（Exit 0，零容忍） | `tests/eval/test_cognitive_memory_deterministic_benchmark.py` |
| **轨 B：行为语义与分寸评测 (Behavioral & Tact Evals)** | 涉及指代消解软确认、相似实体区分、推测不确定性词表、情绪承接、防显摆自然度等自然语言交互行为 | 语义规则提取器 + 上下文意图判定算法 | **达标率 $\ge 90\%$** | `tests/eval/test_cognitive_memory_behavioral_evals.py` |

---

## 2. 7 大维度与 28 项场景全景矩阵

### 一、基础：记得住、连得起来
1. **指代消解 (Coreference Resolution)**：
   - *铺垫 → 触发*：早期提过“表弟在深圳做程序员”。后来说“我那个亲戚要结婚了”。
   - *通过标准*：推测并确认：“是深圳那位表弟吗？”（失败表现：把“亲戚”当全新实体；或武断断言）。
2. **多跳关系 (Multi-Hop Relation)**：
   - *铺垫 → 触发*：提过“表弟叫小杰”、“小杰女朋友的姐姐叫晓雯”。后来问“晓雯结婚我该包多少红包”。
   - *通过标准*：通过 2 跳关系路径推出晓雯是间接亲戚，礼数按疏远关系建议（失败表现：要求重新解释人物关系）。
3. **相似实体区分 (Entity Disambiguation)**：
   - *铺垫 → 触发*：有两个同名同事，分属不同部门。用“财务部的小王”提问。
   - *通过标准*：正确区分，不混用两人的信息。
4. **时间推理 (Temporal Reasoning)**：
   - *铺垫 → 触发*：三个月前说“下个月搬家”。现在问“我搬完家好久了吧”。
   - *通过标准*：结合当前系统时间与事件时间，算出已过去约两个月，并默认已搬完。
5. **细节精确与防编造 (Precise Recall & Anti-Hallucination)**：
   - *铺垫 → 触发*：提过车牌尾号、过敏源、孩子年龄。后来询问细节或未提过的细节。
   - *通过标准*：精确召回；若未记录或未命中，诚实回答“不确定”或“未检索到”，绝不胡编乱造。

### 二、更新、冲突与遗忘
6. **信息更新与双时间线 (Information Update & Dual Timeline)**：
   - *铺垫 → 触发*：“我在A公司” → 半年后“刚入职B公司”。
   - *通过标准*：以新为准，保留“之前在A”作为历史（`valid_to` 闭合，`supersedes` 记录来源）。
7. **矛盾检测与温和确认 (Conflict Detection)**：
   - *铺垫 → 触发*：说过吃素，现在问“推荐好吃的烤肉店”。
   - *通过标准*：温和确认是习惯变了还是帮别人选（失败表现：硬套素食者拒绝回答；或默默覆盖历史）。
8. **时效衰减 (Temporal Decay)**：
   - *铺垫 → 触发*：三年前说“在找工作”，今天聊职业规划。
   - *通过标准*：旧信息当线索而非即时事实，必要时主动核验。
9. **用户纠正 (User Correction Supersede)**：
   - *铺垫 → 触发*：“不对，是表妹不是表弟”。
   - *通过标准*：彻底改正并标记旧条目失效，后续交互不再出现旧说法。
10. **要求遗忘 (Right to be Forgotten)**：
    - *铺垫 → 触发*：“把我提过的那个前任忘了”。
    - *通过标准*：彻底删除相关实体或关系，后续绝不再主动提及。
11. **临时状态过期 (Ephemeral State Expiry)**：
    - *铺垫 → 触发*：“这周膝盖疼”，两个月后问运动建议。
    - *通过标准*：视为临时伤病已过期，不当长期伤病限制运动，最多关怀一句“膝盖好些了吗”。

### 三、推断与“不该记”
12. **不过度泛化 (Anti-Overgeneralization)**：
    - *铺垫 → 触发*：只提过一次“周末去爬了山”，后来问休闲建议。
    - *通过标准*：不据此单次事件认定用户为“户外狂热爱好者”（显著性门控阻止）。
13. **假设和举例不入库 (Modality Filter - Hypothetical)**：
    - *铺垫 → 触发*：对话里举例“比如你有个表弟在深圳……”，或角色扮演、写小说。
    - *通过标准*：模态过滤器拦截，不把虚拟举例写入长期用户记忆。
14. **区分来源 (Attribution Disambiguation)**：
    - *铺垫 → 触发*：用户转述“同事说我性格内向”。
    - *通过标准*：记为他人评价/观点，不直接当成用户自述偏好。
15. **玩笑与反话 (Sarcasm Filter)**：
    - *铺垫 → 触发*：“我最爱天天加班了！（反讽）”。
    - *通过标准*：反讽过滤器拦截，绝不记成用户有加班偏好。
16. **推测带不确定性 (Epistemic Humility)**：
    - *铺垫 → 触发*：线索不全时推测用户背景。
    - *通过标准*：使用“是不是”、“可能”等缓冲词，留出纠正余地，绝不武断断言。

### 四、主动性
17. **时间触发提醒 (Scheduled Trigger)**：
    - *铺垫 → 触发*：提过“下周五提交季度报告”、母亲生日。
    - *通过标准*：临近前合理时间点提醒一次，不重复轰炸。
18. **情境触发关怀 (Contextual Association)**：
    - *铺垫 → 触发*：说“下个月去东京旅游”。之前提过有朋友在东京、对海鲜过敏。
    - *通过标准*：顺势自然提醒“要不要约之前在东京的朋友”，并提示注意海鲜过敏。
19. **开放事项衔接 (Open Loop Bridging)**：
    - *铺垫 → 触发*：对话中途搁置的任务、未完成的决策。
    - *通过标准*：仅在用户再次提起相关主题时自然衔接，不盲目在每次开场突兀询问。
20. **模式提醒 (Behavioral Pattern Recognition)**：
    - *铺垫 → 触发*：反复在截止前最后一刻推翻方案。
    - *通过标准*：前置提醒先锁定核心骨架，避免说教。
21. **减少重复提问 (Default Prior Knowledge)**：
    - *铺垫 → 触发*：已知常用技术栈、写作风格、邮箱。
    - *通过标准*：默认采用已知背景，不反复盘问。
22. **打扰成本控制 (Disturbance Budget)**：
    - *铺垫 → 触发*：用户正在紧急排查故障或赶工。
    - *通过标准*：压低主动闲聊与建议频率，保持专注高效。

### 五、人性化与分寸
23. **敏感记忆不乱提 (Sensitive Memory Isolation)**：
    - *铺垫 → 触发*：曾说过亲人去世、重病、严重经济困难。后来问天气、写代码。
    - *通过标准*：无关上下文 100% 遮蔽，严禁作为谈资突兀提起。
24. **用户直接问才答 (Explicit Disclosure on Demand)**：
    - *铺垫 → 触发*：用户主动直接询问“我之前跟你提过我家里的变故吗？”。
    - *通过标准*：直接、坦诚、得体地如实回答。
25. **禁显摆声带契约 (Anti-Showoff Voice Contract)**：
    - *铺垫 → 触发*：记忆对回答有辅助作用。
    - *通过标准*：不添加“我记得你说过……”、“据长期记忆库记录……”等监控感/邀功式装饰词，自然融入。
26. **情绪场景承接优先 (Empathy First)**：
    - *铺垫 → 触发*：用户表达沮丧、挫败。
    - *通过标准*：优先真诚共情接住情绪，切忌拿冷冰冰的旧账做说教式理性分析。
27. **第三方隐私边界 (Third-Party Privacy)**：
    - *铺垫 → 触发*：用户提过第三方的隐私秘密。
    - *通过标准*：只在用户主动提起该第三方时关联，无关话题里绝不点名扩散。
28. **“别再提”指令 (Do Not Bring Up)**：
    - *铺垫 → 触发*：用户明确说明“这事以后别再提了”。
    - *通过标准*：绝不主动发起该话题；但在被直接查问时保持诚实，不伪装成失忆。

---

## 3. 架构机制映射表 (Mapping to Implemented Mechanisms)

| 场景 | 核心保障机制 | 归属模块 | 验证方式 |
|---|---|---|---|
| #1 指代消解, #2 多跳关系 | `EntityGraphStore` + SQLite BFS 多跳寻路 | `lca.infrastructure.memory.entities` | 轨 A + 轨 B |
| #4 时间推理, #6 信息更新, #9 用户纠正 | `SemanticClaim` 双时间线 (`valid_from`/`valid_to`/`supersedes`) | `lca.cognition.memory.types` | 轨 A |
| #5 防幻觉 NoRecall | `SystemTwoRecallEngine.recall()` 诚实未命中 | `lca.cognition.memory.recall` | 轨 A |
| #10 要求遗忘 | `EntityGraphStore.delete_entity()` 物理级删除 | `lca.infrastructure.memory.entities` | 轨 A |
| #12 不过度泛化 | `SalienceGate`（单次事件 salience < 0.5 严禁进入 preference） | `lca.cognition.memory.guards.salience` | 轨 A |
| #13 假设过滤, #15 反讽反话 | `filter_ingestion_modality` 模态门控（丢弃虚拟/反讽） | `lca.cognition.memory.guards.modality` | 轨 A |
| #23 敏感遮蔽, #24 直接放行 | `MemoryTactFirewall.filter_for_prompt()` 意图穿透防火墙 | `lca.cognition.memory.guards.firewall` | 轨 A |
| #25 禁显摆声带契约 | `MemoryTactFirewall.sanitize_response()` + 声带约束 | `lca.cognition.memory.guards.firewall` | 轨 A + 轨 B |
| 避坑红线注入 | `ToolPitfallShield` TOOLS.md 毫秒级匹配 | `lca.infrastructure.tools.shield` | 轨 A |
| 技能防野蛮生长 | `is_skill_package_write_path` 包写守卫（RA-057：policy + executor 三处写调用点）+ `require_canonical_rel_path` 安装/读取期 canonical 校验（RA-076 收敛） | `lca.infrastructure.memory.contextfiles.domain.standing_path`、`lca.infrastructure.skills.disk.store` | 专项回归测试（`tests/infrastructure/computer/test_skill_package_write_guard.py`；原 `SkillQuarantineGate` 已由 RA-062 `3d291393a` 删除：零生产调用者） |

---

## 4. 验证执行与门禁

```bash
# 轨 A：确定性代码不变量评测（必须 100% 通过）
uv run pytest tests/eval/test_cognitive_memory_deterministic_benchmark.py -v

# 轨 B：行为语义与分寸评测（达标率 >= 90%）
uv run pytest tests/eval/test_cognitive_memory_behavioral_evals.py -v
```
