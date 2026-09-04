# `traces/runs/<run_id>/` 可观察性收口与微调指南

**状态:** 草案 v1 — 评审通过后落代码
**作者:** coding agent / 2026-09-04
**基于:** run_00fd4a4ca23f 实证 + ADR-0185 全 6 PR 状态核对 + fold 模块实测
**本文档角色:** **P0 收口方向的实施入口**(不重新发明方案);**P1+ 微调的清单**(narrative / 字段 / 契约)
**核心 ADR:** ADR-0185(model-visible 走 ADR-0183 统一 event bus)— 6 PR 全部合并,PR-3 composer 改造未合

---

## 0. 第一性原理

### 0.1 三种读者,一种真值

| 读者 | 在看什么 | 想要的格式 | 数据来源 |
|---|---|---|---|
| **人(开发者/排障/UI)** | 这次跑了什么、为什么调工具、模型见的 prompt 长啥样 | Markdown 摘要 + 可点开的结构化树 | `journal.md`(由 StepNarrativeWriter 从 spine 派) |
| **agent(后续 LLM 调试/分析)** | 字段语义稳定、可程序读、字段名直白 | 结构化 JSON / JSONL | `journal.json`(由 StepTreeAccumulator 从 spine 派) |
| **调试器(doctor、CLI 重放)** | 一致性证据、跨文件 digest 校验、错误堆栈 | 单一权威源 + 索引 | `<run_id>.spine.jsonl` + `foldRequestHeader` 纯函数 |

**三种读者共用同一真值层**(`spine.jsonl`),通过不同 deriver 派生不同视图。**没有第二份真值**。

### 0.2 现状病灶 — 双轨运行未收口

| 机制 | 写入路径 | 真值层 | 状态 |
|---|---|---|---|
| **新(ADR-0185)** | `spine.llm.request.header` EP + `foldRequestHeader` | `spine.jsonl` 单一 SSOT | PR-0/1/2/3.1/4 已合,PR-3 composer 改造未合 |
| **旧(ADR-0169 D7 / 0175)** | `StdModelVisibleCapture` + `StdReasonerPromptCapture` | `<run_dir>/model_visible/` 旁路 + spine digest 留痕 | 5 文件被 2626603d 复活 |

**实测验证**(`uv run python`,从 `traces/runs/run_00fd4a4ca23f/`):

| 检查项 | 期望 | 实际 |
|---|---|---|
| spine 含 `spine.llm.request.header` | ≥1 | **0** |
| spine 含 `spine.llm.request.header.assistant` | ≥1 | **0** |
| `foldRequestHeader(spine, 'step-001')` 重建 system | 18908 chars | **None** |
| `foldRequestHeader(spine, 'step-001')` 重建 tools[22] | 22 | **None** |
| `<run_dir>/model_visible/step-001/` 是否被写 | 否 | **是**(8 件套) |

**根因**:`lca/plugins/composer/think/brain.py:40-63` 明确写 — PR-3 不切 composer,`instrument_llm` 签名未扩 ctx,`ModelVisibleHook` 未挂到 LLM 装饰链。新机制只在 viewer 层生效,真值层仍走旧 capture。

### 0.3 当前"好看但实际未生效"的具体表现

| 用户可见 | 现状 | 收口后 |
|---|---|---|
| `journal.md` 没 Skills/Tools 章节 | 因为 fold 落空,narrative 没数据源 | fold 出原文后 StepNarrativeWriter 自动生成 |
| `model_visible/step-XXX/` 8 件套 | 双轨写的同一事实,字段重复 3 份 | **不写** |
| `thinking_kind="final_response"` 但实际是 tool_call | 旧 capture 写死 | fold 重建时按 `SpineLlmRequestHeaderAssistantPayload.tool_calls` 自动分类 |
| SkillRouter 为什么没注入 | `activated_skill_ids=[]` 是真相,但 narrative 没解释 | fold 重建后 narrative 显式标注 `SkillRouter.{not_enabled, no_match, activated}` |

---

## 1. P0 — 收口双轨(从 ADR-0185 接入)

**本文档不重新描述方案;方案已在 [ADR-0185](/home/lichao/layered-cognitive-agent/docs/adr/0185-model-visible-event-bus-alignment.md) + 配套 Note (`docs/notes/implemented/seam/2026-09-04-model-visible-bus-alignment.md`)。**

### 1.1 待合 4 个 TODO(从代码里 grep 出来)

| TODO | 位置 | 影响 |
|---|---|---|
| **PR-3 composer 改造** | `lca/plugins/composer/think/brain.py:40-47` | LLM 调用未挂 `ModelVisibleHook`,新机制未真生效 |
| **PR-4 删 5 个旁路文件** | `_capture_io.py` / `model_visible_capture.py` / `reasoner_prompt_capture.py` / `model_visible_binding.py` / `adapters/model_visible_llm_adapter.py` | 双轨运行,字段重复 |
| **instrument_llm 签名扩 ctx** | `lca/plugins/composer/think/brain.py:25,46` | 接 TODO #1 |
| **SessionStore per-session 接线** | `lca/plugins/composer/think/brain.py:54-65` | `thinking.*` Session 双写残缺 |

### 1.2 P0 实施步骤(1 PR,半天)

```
Step 1: git worktree add ../-ad-0185-pr-3-composer feat/ad-0185-pr-3-composer
Step 2: 改 brain.py:instrument_llm(llm, *, ctx: PluginContext | None = None)
        - ctx 非 None: ctx.soft_get('llm.adapter.hook.model_visible')
        - ctx=None: 回退旧 wiring(测试 / 离 boot 路径)
Step 3: 删 5 个旁路文件(rg 验证 caller 归零):
        lca/infrastructure/observability/loop_cursor/_capture_io.py
        lca/infrastructure/observability/loop_cursor/model_visible_capture.py
        lca/infrastructure/observability/loop_cursor/reasoner_prompt_capture.py
        lca/infrastructure/observability/loop_cursor/model_visible_binding.py
        lca/infrastructure/observability/adapters/model_visible_llm_adapter.py
Step 4: 跑 4 条 I-MV 架构测试守门:
        tests/architecture/test_i_mv_1_producer_authorization.py
        tests/architecture/test_i_mv_3_no_sidecar.py
        tests/architecture/test_i_mv_4_no_brain_publish.py
        tests/architecture/test_i_mv_5_fold_byte_equality.py
Step 5: 跑 uv run pytest tests/ tests/integration tests/architecture tests/plugins/events
Step 6: rg 守门:
        rg "StdModelVisibleCapture|StdReasonerPromptCapture|ModelVisibleCapture|ModelVisibleLLMAdapter|CurrentReasonerPrompt" lca/ lca_kernel/ profiles/ tests/ = 0
        (白名单: docs/adr/0*.md 历史归档 + tests/architecture/test_i_mv_*.py 负向断言)
Step 7: 新跑一次 e2e,验证 foldRequestHeader 重建出原文,model_visible/ 不再被写
```

### 1.3 P0 验收

| 验收项 | 方法 | 期望 |
|---|---|---|
| fold 不再落空 | `uv run python`, `foldRequestHeader(spine, 'step-001')` | 返回 dict,`system_chars ≥ 1` |
| model_visible/ 不再被写 | `ls traces/runs/<new_run>/model_visible/` | **不存在** |
| 双轨字段重复消失 | `find traces/runs/<new_run>/ -type f \| wc -l` | **7 件**(`run.json / journal.json / journal.md / spine.jsonl / session.jsonl / exceptions.jsonl` + profile_snapshot) |
| I-MV 架构测试 | `uv run pytest tests/architecture/test_i_mv_*.py` | 0 失败 |

---

## 2. P1+ — 收口后的微调(本 spec 的真正内容)

**前提**:P0 已合,fold 真生效,model_visible/ 不写。

### 2.1 P1 — narrative 增强章节(改 `StepNarrativeWriter`)

| 章节 | 字段来源 | 价值 | 优先级 |
|---|---|---|---|
| **🧰 Tools sent to model(N)** | `foldRequestHeader.tools` 每个 tool.name + description 一句话 | 一眼看到「模型能不能调哪些工具」 | 高 |
| **🎯 Skills activated(N)** | `foldRequestHeader.activated_skill_ids` + `available_skills_count` | 解释为什么没走 skill | 高 |
| **📚 Sections in prompt(N)** | fold 重建的 sections 13 段 `{name, content_digest, preview}` | 看清 prompt 结构 | 中 |
| **💬 Context items(N)** | `foldRequestHeader.context_manifest.items` | 看清注入的 workspace / clock / skill_catalog | 中 |
| **🧠 Reasoning per step** | `SpineLlmRequestHeaderAssistantPayload` 原文 | 不再因 thinking.text 为空而看不到 | 高 |

**不重复实现**:`StepNarrativeWriter` 已有 step / 思考 / 工具调用 / 工具结果四章;在每章加 fold 重建的数据即可。

### 2.2 P2 — narrative 改名 + step 目录平铺

| 现状 | 目标 |
|---|---|
| `journal.narrative.md` | `journal.md` |
| `model_visible/step-XXX/`(P0 后不写) | `steps/step-XXX/readme.md`(P0 后由 StepNarrativeWriter 从 fold 派) |

**为什么分两步**:P2 在 P0 之后才能做 — 收口前 `model_visible/step-XXX/` 是双轨写的事实,P0 后 fold 是唯一来源,`readme.md` 才有 SSOT。

### 2.3 P3 — 字段瘦身

| 删 | 理由 | delete-when |
|---|---|---|
| `manifest.json.materializer_version='0.1.0'` | 长期无消费者 | `rg "materializer_version" lca/ lca_kernel/ = 0` |
| `manifest.json.evidence_integrity=[]` | 长期空数组 | `rg "evidence_integrity" lca/ lca_kernel/ = 0` |
| `profile_snapshot.json.plugins[]` 元数据膨胀 | 只需要 `{id, layer, kind, effects}` | `rg "plugins\[" profile_snapshot = 0`(但保留插件能力图) |
| `<run_id>.exceptions.jsonl` 空文件 | 0 异常时不该落盘 | `wc -l exceptions.jsonl = 0` → 不写 |

### 2.4 P4 — 契约闭集 fix

| 闭集 | 当前 | 修复 |
|---|---|---|
| `thinking_kind: Literal["reasoning", "final_response", "compaction"]` | 调工具步骤被打 `final_response` | 加 `tool_call_response` / `tool_use_response` 闭集值 |
| `available_skills_count=0` | 不可区分原因 | 加 `available_skills_reason: Literal["not_enabled", "no_match", "activated"]` |
| `activated_skill_ids: []` | 不可区分原因 | 同上 reason 字段统一 |

**注意**:P4 的修复必须在 P0 之后才能由 fold 派出来 — 因为 `thinking_kind` 实际值要等 `SpineLlmRequestHeaderAssistantPayload.tool_calls` 长度 > 0 才能分类。

### 2.5 P5 — 字段命名冻结 + deprecation

| 现状 | 目标 |
|---|---|
| `arguments` vs `arguments_summary` vs `arguments_digest` 三字段混用 | 保留主字段,其他标 `@deprecated` + delete-when |
| `system_digest == messages_digest`(别名) | 删 `system_digest` 字段,只留 `messages_digest` |
| `system_path == messages_path`(同指) | 删 `system_path`,只留 `messages_path` |

---

## 3. 优雅度评分(架构视角)

| 维度 | 现状(双轨) | P0 后 | P4 后(全部微调) |
|---|---|---|---|
| 单一职责 | 6/10 | 9/10 | 10/10 |
| 关注点分离 | 5/10 | 8/10 | 9/10 |
| 契约闭合 | 4/10 | 8/10 | 9/10 |
| 长期可维护 | 5/10 | 8/10 | 9/10 |
| 人可读性 | 5/10 | 7/10 | 9/10 |
| 调试效率 | 4/10 | 8/10 | 9/10 |
| **总评** | **29/60 (48%)** | **48/60 (80%)** | **55/60 (92%)** |

---

## 4. 验收

### 4.1 一句话目标

**「任何 run 的『模型所见』由 `<run_id>.spine.jsonl` + `foldRequestHeader` 纯函数唯一重建;`<run_dir>/model_visible/` 不再被写」**

### 4.2 量化验收(P0 后)

| 指标 | 现状 | P0 后 |
|---|---|---|
| `traces/runs/<run>/` 文件数 | 33 | **8**(`run.json` + `profile_snapshot.json` + `journal.json` + `journal.md` + `spine.jsonl` + `session.jsonl` + `exceptions.jsonl` + 一个 `manifest.json` 兼容层) |
| "模型所见 prompt" 副本数 | 3 | **1**(spine.system 字段) |
| 双 schema(spine) | 2(10 键 + 17 键) | **1**(纯 10 键) |
| 调试场景跳转数(10 题平均) | 35 文件 | **1 文件**(spine.jsonl)+ 纯函数 fold |
| I-MV 架构测试 | 4 条 | 4 条全绿 |

### 4.3 rg 白名单(I-MV-3 架构测试用)

```text
# rg "model_visible/" 历史归档允许命中:
docs/adr/0*.md                                    # 历史 ADR
docs/notes/implemented/seam/2026-09-03-*         # 历史 implemented note
tests/architecture/test_i_mv_*.py                 # 负向断言
```

---

## 5. 实施顺序 + 依赖

```
P0 (合 ADR-0185 composer + 删旁路文件) ← 本文档入口
    ↓
    ├─→ P1 (narrative 章节)
    ├─→ P2 (改名 + 平铺)
    ├─→ P3 (字段瘦身)
    └─→ P4 (契约闭集)
            ↓
            P5 (字段命名冻结)
```

- **P0** 必须先做(否则 P1+ 没有数据源)
- **P1 ~ P4** 可并行(互不依赖,均依赖 P0)
- **P5** 最后做(需要 P4 闭集稳定后才能冻结字段名)

### 5.1 每个 P 的"好实施"门槛

| P | "好实施"的判据 | 失败则返工 |
|---|---|---|
| **P0** | fold 实测返回原文;model_visible/ 不被写;572 测试通过 | 检查 composer wiring + 5 文件 rg 守门 |
| **P1** | `journal.md` 在 fold 数据后能写出 Tools/Skills/Sections 章节;doctor H-mv-journal 全绿 | 看 StepNarrativeWriter 测试覆盖率 |
| **P2** | `journal.md` 替换 `journal.narrative.md`;旧 viewer 报错信息明确 | 旧 viewer 引用全 grep |
| **P3** | 现有 572 测试通过 + `rg "materializer_version\|evidence_integrity" = 0` | 看测试是否依赖这些字段 |
| **P4** | `thinking_kind` 闭集 + `available_skills_reason` 字段测试通过 | fold 输出需含 assistant_content + tool_calls |
| **P5** | `@deprecated` 标注 + delete-when 文档 + 老 viewer 兼容 1 个 minor 版本 | deprecation warning 检查 |

---

## 6. 关键结论

1. **核心矛盾是「双轨运行未收口」**,不是「日志换行多」。**P0 是真问题,P1+ 是真问题解决后的微调**。
2. **方案已在 ADR-0185**,本文档只描述**怎么合 + 合完之后怎么微调**,不重新发明。
4. **好实施的判据已给**(§5.1),不是"主观打分",是"可执行的 rg / pytest / fold 实测"。
5. **不要先写 P1+ 的 spec,先动 P0**;P1+ 是 P0 后的产物,顺序反了会变成"纸上谈兵"。

---

## 7. Related

- [ADR-0185](/home/lichao/layered-cognitive-agent/docs/adr/0185-model-visible-event-bus-alignment.md) — Model-Visible 走 ADR-0183 统一 event bus
- [Note 2026-09-04-model-visible-bus-alignment](/home/lichao/layered-cognitive-agent/docs/notes/implemented/seam/2026-09-04-model-visible-bus-alignment.md) — 实施进度跟踪
- [lca_kernel/events/fold.py](/home/lichao/layered-cognitive-agent/lca_kernel/events/fold.py) — `canonicalHeader` / `headerEquals` / `foldRequestHeader` 纯函数
- [lca/plugins/events/publishers/model_visible/publisher.py](/home/lichao/layered-cognitive-agent/lca/plugins/events/publishers/model_visible/publisher.py) — `ModelVisiblePublisher` plugin marker
- [lca/plugins/composer/think/brain.py](/home/lichao/layered-cognitive-agent/lca/plugins/composer/think/brain.py) — TODO(PR-3) composer 改造入口
- [tests/architecture/test_i_mv_*.py](/home/lichao/layered-cognitive-agent/tests/architecture/) — 4 条 I-MV 架构测试

---

**生成于:** run_00fd4a4ca23f 验证流程 + ADR-0185 全 6 PR 状态核对 + fold 模块实测
**下次评审:** P0 实施后(预计 1 PR,半天)
**跟踪:** docs/notes/implemented/seam/2026-09-04-model-visible-bus-alignment.md(PR-3 composer 改造待合)