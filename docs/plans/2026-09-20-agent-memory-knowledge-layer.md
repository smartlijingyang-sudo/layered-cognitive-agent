# Agent 记忆知识层实施计划

把 LCA 的 agent 记忆从"关键词触发的原文存档"升级为结构化知识层：LLM 蒸馏提取、typed `MemoryRecord`、受治理记忆工具、用户画像回填、预算内相关性检索、supersede/遗忘生命周期；修通 `assistant.bootstrap` 死代码，清理 `workspace_instructions` 污染与硬编码关键词机制。决策依据见 [ADR-0247](../adr/0247-agent-memory-knowledge-layer.md)。

PR 顺序：PR-1 → PR-2 → PR-3 → PR-4 → PR-5 → PR-6 → PR-7 → PR-8 → PR-9 → PR-10。PR-1/PR-2 是契约与测试基建，PR-3~PR-8 是图节点与工具接入，PR-9 清理垃圾逻辑，PR-10 端到端回归。

## How to read this

一个 PR 是一个可独立合并、独立验证的变更单元。每个 PR 的 Verify 分三档：unit（pytest）、live（`lca-ops` 真实 run + spine 断言）、perf（度量与预算）。live 是必须的：只有 `./scripts/lca-ops kernel-restart` 后跑真实 run，才能证明线上生效（prove-it-works）。

## PR 列表总览

| PR | 依赖 | 内容 | 主要文件 |
|---|---|---|---|
| PR-1 | 无 | 契约升级：`MemoryRecord`/`MemoryCategory`/`UserProfile`/`MemoryStore`/`MemoryRetrievalPolicy`/`MemoryTool` | `lca/contracts/models/core/conversation/memory.py`、`lca/contracts/protocols/memory/*` |
| PR-2 | PR-1 | 测试基建：memory 测试 harness、fake store、连续对话回归夹具 | `tests/support/`、`tests/integration/` |
| PR-3 | PR-2 | `reflect.memory.extract` LLM 蒸馏节点 + remember 子图改造 + 删除关键词表 | `lca/nodes/reflect/score/score.py`、`lca/nodes/remember/*`、`bundles/reflect/`、`bundles/remember/` |
| PR-4 | PR-3 | `memory_retrieve` 接入检索策略（预算/相关性） | `lca/nodes/perceive/memory_retrieve/`、`lca/cognition/memory/*` |
| PR-5 | PR-4 | `USER_PROFILE` prompt section + CONTEXT 结构化行 | `lca/plugins/prompts/sections.py`、`lca/cognition/brain/sections/*` |
| PR-6 | PR-5 | memory 工具族（search/add/update/remove） | `lca/infrastructure/tools/assistant/`、`lca/plugins/domain/assistant/` |
| PR-7 | PR-6 | `assistant.bootstrap` 接线 + 移除 `sensor.workspace-instructions` | `lca/plugins/assistant/bootstrap/`、`lca/plugins/sensors/`、`bundles/web-app.yaml` |
| PR-8 | PR-7 | 暂停 run 恢复补记记忆 | `lca/runtime/loop/`、`lca/plugins/runtime/resume_input/` |
| PR-9 | PR-8 | 迁移旧 `semantic.json`、清理小写 `user.md`、删死代码 | `lca/infrastructure/memory/assistant_memory.py`、迁移脚本 |
| PR-10 | PR-9 | 4 轮连续对话跨 run 记忆端到端回归 | `tests/e2e/` 或 `tests/scenario/` |

---

## PR-1 契约升级

**Depends on.** None.

**Files.**

- [ ] 改 `lca/contracts/models/core/conversation/memory.py`：`MemoryRecord` 增加 `category`、`confidence`、`source`、`source_trace_id`、`expires_at`、`supersedes`、`status`、`dedupe_key`。
- [ ] 新增 `MemoryCategory` 枚举（identity/preference/fact/episodic/procedural），登记到枚举闭集与 whitelist。
- [ ] 新增 `UserProfile` DTO（称呼/身份/偏好/上下文 + revision）。
- [ ] 扩展 `lca/contracts/protocols/memory/memory.py`：`MemoryStore` 增加 `upsert` / `supersede` / `query`；`MemoryRetrievalPolicy` 增加预算参数。
- [ ] 新增 `MemoryTool` Protocol（search/add/update/remove 的入参与效果声明）。

**Build.**

- 一个变更：把记忆从"无类型字符串"升级为"typed 知识记录"，全部字段 frozen + `extra="forbid"`。

**You see.**

- `MemoryRecord` 实例化时必须提供 `category`；旧字段默认值迁移。

**Verify, unit.** 测试单独可跑。

- [ ] `tests/contracts/test_memory_record_schema.py`：合法/非法字段、序列化兼容（旧记录缺新字段按默认值读）。
- [ ] `tests/contracts/test_memory_category_closed_set.py`：`MemoryCategory` 在闭集内，新增需同步 whitelist。
- [ ] `tests/contracts/test_memory_protocols.py`：`MemoryStore`/`MemoryRetrievalPolicy`/`MemoryTool` 契约测试。
- [ ] 运行 `uv run pytest tests/contracts/test_memory_* -q` + `uv run ruff check lca/contracts/models/core/conversation/memory.py`。

**Verify, live.** 本 PR 无运行时可观察行为，跳过真实 run；以契约测试通过为证。记入 PR 描述。

**Verify, perf.** 本 PR 不引入性能敏感路径。

**Review gate.** None。PR-1 不改变用户可见行为。

**Merge.** 单 PR squash merge，rebase 到当前 trunk。

---

## PR-2 测试基建

**Depends on.** PR-1。

**Files.**

- [ ] 新建 `tests/support/memory_harness.py`：内存版 `MemoryStore`、固定 `MemoryRetrievalPolicy`、可注入的 fake `extract`。
- [ ] 新建连续对话回归夹具：给定 4 轮用户消息序列，断言第二轮能引用第一轮产生的记忆。
- [ ] 在 `tests/integration/` 登记夹具使用方式。

**Build.**

- 一个变更：让记忆相关测试不依赖真实 LLM 与文件系统。

**You see.**

- 运行夹具测试，不调用外部 LLM，全部走 fake。

**Verify, unit.**

- [ ] `tests/integration/test_memory_harness_roundtrip.py`：写→检索→supersede 全流程在 harness 内通过。
- [ ] `tests/integration/test_conversation_memory_fixture.py`：4 轮夹具在 harness 内跑通。
- [ ] `uv run pytest tests/integration/test_memory_harness_roundtrip.py tests/integration/test_conversation_memory_fixture.py -q`。

**Verify, live.** 本 PR 纯测试基建，无运行时可观察行为。

**Verify, perf.** 不适用。

**Review gate.** None。

**Merge.** 单 PR squash merge。

---

## PR-3 记忆提取节点（LLM 蒸馏）与 remember 子图改造

**Depends on.** PR-2。

**Files.**

- [ ] 新建 `lca/nodes/reflect/memory_extract/memory_extract.py`：`phase.reflect.memory.extract`，schema 约束的 LLM 小调用，输出 `MemoryCandidate` 列表；普通回复快速路径不调 LLM。
- [ ] 删除 `lca/nodes/reflect/score/score.py` 中 `_SEMANTIC_DIRECTIVE_MARKERS` 与 `_extract_semantic_candidate`。
- [ ] 改 `bundles/reflect/reflect_subgraph.yaml` 与 `bundles/remember/remember_subgraph.yaml`：子图拓扑变为 `reflect.score → remember.extract → remember.admit → remember.write → remember.fold`。
- [ ] 改 `lca/nodes/remember/admit/admit.py`：按 `dedupe_key` 去重，权威度排序，过滤低置信度。
- [ ] 改 `lca/nodes/remember/write/write.py`：落盘 typed `MemoryRecord`，同 `dedupe_key` 新事实 supersede 旧记录。
- [ ] 新增 EP 注册（`phase.remember.extract` start/end）到 `EXECUTION_POINTS` 白名单 + SpineHandler + 测试。

**Build.**

- 一个变更：记忆提取从"关键词正则"换成"LLM 语义蒸馏"，提取结果从原文换成结构化候选。

**You see.**

- 用户说"我是架构师，我不喜欢啰嗦"，`reflect.memory.extract` 输出 `category=identity`、`content="用户身份：架构师"` 与 `category=preference`、`content="用户偏好：不喜欢啰嗦"`；`semantic.json` 不再出现原文整句。

**Verify, unit.**

- [ ] `tests/reflect/test_memory_extract_distills_identity.py`：中文自然陈述（无关键词）产出 identity/preference 候选。
- [ ] `tests/reflect/test_memory_extract_fast_path_no_llm.py`：普通回复不触发 LLM 调用。
- [ ] `tests/remember/test_admit_dedupe_supersede.py`：重复陈述去重、新事实 supersede 旧事实。
- [ ] `tests/observability/test_ep_whitelist.py`：新 EP 在白名单内。
- [ ] `uv run pytest tests/reflect/test_memory_extract_* tests/remember/test_admit_dedupe_supersede.py tests/observability/test_ep_whitelist.py -q`。

**Verify, live.**

- [ ] `./scripts/lca-ops kernel-restart --json` 后创建测试 run：`./scripts/lca-ops runs create --profile web-assistant --user-text "我是架构师，我不喜欢啰嗦，以后叫我老板"`。
- [ ] 断言 `<run_id>.spine.jsonl` 的 `phase.remember.extract` 输出含 `category=identity` 候选，且 `~/.lca/assistants/<id>/memory/semantic.json` 第一条是结构化事实（非原文整句）。

**Verify, perf.**

- [ ] Metric：提取节点 LLM 调用耗时（快速路径为 0）。
- [ ] Probe：`lca-ops journal trace <run_id> --json` 中 `llm.call.start` 到 `llm.call.end` 的增量。
- [ ] Baseline：普通回复（无记忆候选）快速路径 0ms。
- [ ] Rule：普通回复不产生新 LLM 调用；蒸馏调用延迟 < 5s。

**Review gate.** None。行为变化由集成测试覆盖。

**Merge.** 单 PR squash merge。删除关键词表必须在本 PR 内完成（ADR-0247 §7 迁移语义）。

---

## PR-4 检索策略接入

**Depends on.** PR-3。

**Files.**

- [ ] 实现 `lca/cognition/memory/layered/retrieval_policy.py` 升级：`relevance × recency × importance` 排序 + `token_budget` 截断 + 排除 superseded/过期。
- [ ] 改 `lca/nodes/perceive/memory_retrieve/memory_retrieve.py`：把预算参数传给 `memory.retrieve()`，不再全量返回。
- [ ] 为记忆检索增加 token 估算（字符级近似）。

**Build.**

- 一个变更：记忆注入从"全量最近记录"变成"预算内相关记录"。

**You see.**

- 记忆记录超过 `token_budget` 时，CONTEXT 只出现排序靠前的相关记录，不超预算。

**Verify, unit.**

- [ ] `tests/memory/test_retrieval_policy_budget.py`：预算截断、superseded 排除、过期排除。
- [ ] `tests/memory/test_retrieval_policy_ranking.py`：recency×importance 排序确定性强（同一输入两次结果一致）。
- [ ] `tests/integration/test_memory_retrieve_budget.py`：perceive 阶段注入不超过预算。
- [ ] `uv run pytest tests/memory/test_retrieval_policy_* tests/integration/test_memory_retrieve_budget.py -q`。

**Verify, live.**

- [ ] 创建含多条记忆的测试 agent，`runs create` 触发一轮对话，断言 `llm.request.header` 的 system `CONTEXT` 段记忆字符数 ≤ 配置预算。

**Verify, perf.**

- [ ] Metric：检索耗时。
- [ ] Probe：`lca-ops timeline` 中 `phase.perceive.memory_retrieve` 的 `elapsed_ms`。
- [ ] Baseline：记录当前全量返回的 `elapsed_ms`（PR-4 前）。
- [ ] Rule：PR-4 后检索耗时 ≤ 基线 + 10ms；注入字符数 ≤ 预算。

**Review gate.** None。

**Merge.** 单 PR squash merge。

---

## PR-5 用户画像回填与呈现

**Depends on.** PR-4。

**Files.**

- [ ] 新增 `lca/plugins/assistant/profile/` 插件：从 identity/preference 事实回填 `{home}/USER.md`，经 `effect_gateway`（capability `profile.update`），写 revision 快照。
- [ ] 新增 prompt section `USER_PROFILE`：渲染 `UserProfile` 结构化画像。
- [ ] 改 `lca/cognition/brain/sections/types.py` 的 `render_context_lines`：记忆行输出结构化事实（`- [identity] 用户：架构师`），不再是原文。

**Build.**

- 一个变更：用户画像从"空模板"变成"系统回填的当前态"，并在 prompt 中独立呈现。

**You see.**

- 新 agent 首次对话说"我是架构师"，下一轮 run 的 system prompt 出现 `USER_PROFILE` 段：`身份：架构师`；`USER.md` 文件被回填。

**Verify, unit.**

- [ ] `tests/assistant/test_profile_backfill.py`：identity 事实触发 `USER.md` 回填 + revision 快照。
- [ ] `tests/plugins/prompts/test_user_profile_section.py`：`USER_PROFILE` 段渲染正确。
- [ ] `tests/plugins/prompts/test_context_memory_line_structured.py`：CONTEXT 行是结构化事实。
- [ ] `uv run pytest tests/assistant/test_profile_backfill.py tests/plugins/prompts/test_user_profile_section.py tests/plugins/prompts/test_context_memory_line_structured.py -q`。

**Verify, live.**

- [ ] `kernel-restart` 后，对测试 agent 连续两轮 `runs create`（第一轮"我是架构师"，第二轮"你记得我是谁吗"），断言第二轮 system prompt 含 `USER_PROFILE` 且 agent 回复引用"架构师"。

**Verify, perf.**

- [ ] Metric：`USER_PROFILE` 段字符数。
- [ ] Probe：`llm.request.header` 的 system 长度。
- [ ] Baseline：PR-5 前无该段（0 字符）。
- [ ] Rule：`USER_PROFILE` 段 ≤ 500 字符（结构化画像有界）。

**Review gate.** 本 PR 改变用户可见的 agent 行为（回复会引用画像）。合并前在聊天中展示两轮对话的 agent 回复文本，等待 operator 确认。

**Merge.** operator 确认后单 PR squash merge。

---

## PR-6 受治理记忆工具族

**Depends on.** PR-5。

**Files.**

- [ ] 新增 `lca/infrastructure/tools/assistant/memory_tools.py`：`memory_search` / `memory_add` / `memory_update` / `memory_remove`。
- [ ] 在 `lca/plugins/domain/assistant/tools/` 注册工具，效果声明走 `CommandEnvelope`（C10 窄门，capability `memory.update` / `memory.read`）。
- [ ] 更新 `HomeSection` 提示语：模型可通过记忆工具读写，不再需要 writeFile。

**Build.**

- 一个变更：模型获得受治理的记忆读写工具，替代手动写文件。

**You see.**

- 模型说"我把你记成架构师"时调用 `memory_add`（而非 `writeFile`），spine 出现 `step.tool_call.record tool_name=memory_add`。

**Verify, unit.**

- [ ] `tests/assistant/test_memory_tools_contract.py`：四个工具入参 schema、效果声明、幂等键。
- [ ] `tests/assistant/test_memory_tools_gate.py`：未授权 capability 被拒。
- [ ] `tests/assistant/test_memory_tools_roundtrip.py`：add → search → update → remove 全流程。
- [ ] `uv run pytest tests/assistant/test_memory_tools_*.py -q`。

**Verify, live.**

- [ ] 创建 run 让模型主动使用 `memory_add` 记录一条偏好，断言 spine 中工具调用成功且 `semantic.json` 新增 typed 记录。

**Verify, perf.**

- [ ] Metric：工具调用延迟。
- [ ] Probe：`body.tool.execute.end` 的 `latency_ms`。
- [ ] Baseline：现有 `writeFile` 工具延迟。
- [ ] Rule：`memory_add` 延迟 ≤ 200ms（本地文件写）。

**Review gate.** None。

**Merge.** 单 PR squash merge。

---

## PR-7 bootstrap 接线与 workspace sensor 移除

**Depends on.** PR-6。

**Files.**

- [ ] 把 `assistant.bootstrap` 投影服务接入 `phase.perceive.observe`（作为 per-assistant sensor 合并），让 `workspace_instructions`/`workspace_artifacts` 来自 `{home}/`。
- [ ] 从 `bundles/web-app.yaml` 移除 `sensor.workspace-instructions`。
- [ ] 清理 `tests/support/scenario_harness.py` 中对全局 workspace sensor 的引用。

**Build.**

- 一个变更：`workspace_instructions` kind 只有一个生产者（assistant Home），项目根 AGENTS.md 不再注入 agent manifest。

**You see.**

- 新 run 的 `phase.perceive.observe` 输出 manifest 中不再出现项目 AGENTS.md 内容；`workspace_instructions` 的 provenance 是 `assistant.bootstrap.<id>`。

**Verify, unit.**

- [ ] `tests/plugins/assistant/test_bootstrap_consumer.py`：bootstrap 投影被 perceive 消费。
- [ ] `tests/scenario/plugin/test_plugin_wiring_e2e.py`：移除 sensor 后装配通过。
- [ ] `tests/architecture/test_p7_profile_regions_declare.py`：bundle 列表不变。
- [ ] `uv run pytest tests/plugins/assistant/test_bootstrap_consumer.py tests/scenario/plugin/test_plugin_wiring_e2e.py -q`。

**Verify, live.**

- [ ] `kernel-restart` 后创建 run，断言 `<run_id>.spine.jsonl` 的 manifest items 中 `workspace_instructions` provenance 是 `assistant.bootstrap.*`，且无 `workspace_instructions_sensor`。

**Verify, perf.** 不适用（无新增运行时开销）。

**Review gate.** None。

**Merge.** 单 PR squash merge。

---

## PR-8 暂停 run 恢复补记

**Depends on.** PR-7。

**Files.**

- [ ] 改 `lca/plugins/runtime/resume_input/`：run 从 `askUserQuestion` 暂停恢复时，先补跑 `reflect/remember` 捕获该轮用户陈述，再进入下一轮。

**Build.**

- 一个变更：交互暂停不再丢失该轮的记忆候选。

**You see.**

- `run_68ea0e5c76d4` 场景（用户说"我是架构师"后 askUserQuestion 暂停）恢复后，`semantic.json` 出现该轮身份候选。

**Verify, unit.**

- [ ] `tests/runtime/test_resume_input_memory_capture.py`：暂停→恢复→记忆候选落盘。
- [ ] `tests/runtime/test_resume_input_idempotent.py`：重复恢复不重复写入（幂等键）。

**Verify, live.**

- [ ] 构造带 askUserQuestion 的 run，回答后恢复，断言恢复后的 run 中该轮用户陈述被提炼为记忆。

**Verify, perf.** 不适用（补记在恢复路径上，无额外感知开销）。

**Review gate.** None。

**Merge.** 单 PR squash merge。

---

## PR-9 垃圾逻辑清理与数据迁移

**Depends on.** PR-8。

**Files.**

- [ ] 删除 `_SEMANTIC_DIRECTIVE_MARKERS` 相关死代码（若 PR-3 已删，此处确认无残留引用）。
- [ ] 一次性迁移脚本：把旧 `semantic.json` 原文记录标记 `status=superseded`，保留可审计，不再参与检索。
- [ ] 清理测试 agent home 中的小写 `user.md`，把有效身份信息回填到 `USER.md`。
- [ ] 清理 `docs/notes/proposed/primitive/2026-09-17-step-advance-writer-missing.md` 中已由本 ADR 覆盖的条目状态（如适用）。

**Build.**

- 一个变更：删除被替代的垃圾机制，迁移历史数据到 typed 格式。

**You see.**

- `git grep _SEMANTIC_DIRECTIVE_MARKERS` 无命中；旧 `semantic.json` 记录全部 `status=superseded`。

**Verify, unit.**

- [ ] `tests/migration/test_semantic_json_migration.py`：旧格式→typed 格式，旧记录标记 superseded。
- [ ] `tests/regression/test_no_keyword_markers.py`：静态断言 `reflect/` 下无硬编码意图关键词表。
- [ ] `uv run pytest tests/migration/test_semantic_json_migration.py tests/regression/test_no_keyword_markers.py -q`。

**Verify, live.**

- [ ] 对迁移后的测试 agent 跑一轮 run，断言 CONTEXT 不出现 `status=superseded` 的旧原文记录。

**Verify, perf.** 不适用。

**Review gate.** None。

**Merge.** 单 PR squash merge。

---

## PR-10 端到端连续对话回归

**Depends on.** PR-9。

**Files.**

- [ ] 新增 `tests/e2e/test_cross_run_memory.py`：4 轮连续对话（身份陈述 → 偏好陈述 → 隐式引用 → 冲突纠正），每轮独立 run，断言第二轮起 agent 能引用前文身份/偏好，且记忆无重复堆积。
- [ ] 接入 CI 可运行（`real_llm` 默认不跑，用 fake extract 或打标跳过）。

**Build.**

- 一个变更：把 ADR-0247 的验收谓词固化为可重复的端到端测试。

**You see.**

- 4 轮对话中：第 1 轮"我是架构师"，第 2 轮 agent 回复引用架构师身份，第 3 轮"我不喜欢啰嗦"后 agent 回复变简洁，第 4 轮纠正偏好后旧偏好被 supersede。

**Verify, unit.**

- [ ] `uv run pytest tests/e2e/test_cross_run_memory.py -q`（fake extract 模式）。
- [ ] 附带 `tests/e2e/test_cross_run_memory_live.py`（打标 `real_llm`，CI 默认跳过）。

**Verify, live.**

- [ ] 手动模式：对真实测试 agent 连续 4 轮 `runs create`，逐轮检查 `USER_PROFILE` 段与 CONTEXT 记忆行，确认身份/偏好/纠正全部生效。

**Verify, perf.**

- [ ] Metric：4 轮累计注入记忆字符数。
- [ ] Probe：每轮 `llm.request.header` system 中 CONTEXT+USER_PROFILE 长度。
- [ ] Baseline：PR-9 后同一场景（无 e2e 前）的注入量。
- [ ] Rule：4 轮累计注入 ≤ 基线 + 500 字符；无原文重复记录。

**Review gate.** 本 PR 是行为验收。合并前在聊天中展示 4 轮对话的 agent 回复，等待 operator 确认。

**Merge.** operator 确认后单 PR squash merge。

---

## 收尾

- [ ] 全部 PR 合并后，更新 ADR-0247 状态为 Accepted，并按 implemented 惯例补 Agent Note（`docs/notes/implemented/contract/2026-09-20-adr-0247-implemented.md`）。
- [ ] 跑 `uv run python scripts/verify_md_links.py` + `uv run python scripts/verify_doc_budgets.py` + `uv run python scripts/check_doc_layering.py --strict`。
- [ ] 把本次调研证据（run 时间线、现象、业界对照）归档到 `history/2026-09/memory-knowledge-layer/`。

## 附录 A 原型证据

无原型。所有设计决策基于真实 run 证据与四个 subagent 调研，证据索引：
- run spine：`traces/runs/run_68ea0e5c76d4/`、`run_a988646b19ad/`、`run_3a4dc075f0e4/`
- assistant home：`~/.lca/assistants/asst_382526fbf2bb/`
- 调研结论：ADR-0244、ADR-0242、`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`、`PLAN-dsh-obs-parity.md`、Hermes/Claude/ChatGPT/LobeHub/OpenClaw 官方文档（见各 PR 描述）

## 附录 B 备选方案

见 ADR-0247 §6。

## 附录 C 风险

| 风险 | 落在 | 关注 |
|---|---|---|
| LLM 蒸馏增加成本 | PR-3 | 快速路径必须零调用；蒸馏只在该轮有候选时触发 |
| 旧记忆迁移丢失 | PR-9 | 只标记 superseded，不删除 |
| 删除关键词表后中文表达覆盖 | PR-3 | 集成测试覆盖"记住我""叫我老板"等原关键词场景 |
| `USER_PROFILE` 段占用上下文 | PR-5 | 500 字符上限 |

## 附录 D 阅读清单

- 开工前读：ADR-0244、ADR-0242、`lca/nodes/reflect/score/score.py`、`lca/nodes/remember/*`、`lca/nodes/perceive/memory_retrieve/`、`lca/plugins/assistant/bootstrap/bootstrap.py`、`lca/plugins/prompts/sections.py`。
- PR-3 用 `how` 读记忆闭环现状；PR-5 用 `how` 读 prompt sections 注册。