# Agent Note: ADR-0247 Agent 记忆知识层落地

Status: implemented

## Problem

新创建的产品经理 agent 在连续对话中记不住用户身份：「我是架构师」跨 3 个 run 约 74 秒后才被写入；记忆文件存的是用户抱怨原文；`USER.md` 模板从未被回填；模型没有受治理的记忆工具，只能手动 `writeFile` 写错文件名（小写 `user.md` 不在 `CONFIG_FACE_FILES`，永不加载）。`reflect.score` 用硬编码关键词表（`_SEMANTIC_DIRECTIVE_MARKERS`）触发原文存档，违反 ADR-0244 P4；`assistant.bootstrap` 投影服务无运行时代码消费，项目根 `AGENTS.md` 反而经 `WorkspaceInstructionsSensor` 注入 `workspace_instructions` kind。

## Decision

按 ADR-0247 十个 PR 落地：

1. **契约升级**：新增 `MemoryCategory` 闭集（identity/preference/fact/episodic/procedural）；`MemoryRecord` 增加 `category` / `dedupe_key`，supersede/过期复用既有 `revision_of` / `valid_until_ms` / `retired_at_ms`；新增 `MemoryStore`（upsert/supersede/query）与 `MemoryTool` 协议。
2. **测试基建**：`tests/support/memory_harness.py` 提供内存 store、固定检索策略、fake extractor 与 4 轮对话夹具。
3. **LLM 蒸馏**：删除 `_SEMANTIC_DIRECTIVE_MARKERS` 与 `_extract_semantic_candidate`；新增 `phase.reflect.memory.extract` 节点，schema 约束的小 LLM 调用，仅自我指涉陈述触发（快速路径零调用）；`remember.admit` 按权威度过滤候选列表；`AssistantMemory` 落盘 typed 记录并按 `dedupe_key` supersede。
4. **预算检索**：`LayeredRetrievalPolicy` 升级为 `relevance × recency × importance` 排序 + 字符级 token 预算截断，排除 superseded/过期；`memory_retrieve` 节点把 query/token_budget 传给 `MemorySystem.retrieve`。
5. **画像呈现与回填**：CONTEXT 记忆行改为结构化事实（`- [identity] 用户：架构师`）；新增 `USER_PROFILE` prompt section；`assistant.profile.backfill` 服务经 `revise_profile` 回填 `USER.md` 并产生 revision 快照。
6. **受治理记忆工具**：`memory_search` / `memory_add` / `memory_update` / `memory_remove` 注册进 assistant 工具工厂，写操作走 typed store（幂等 + supersede），删除需用户确认。
7. **bootstrap 接线**：`phase.perceive.observe` 合并 `assistant.bootstrap` 投影（runtime 携带 `assistant_bootstrap` + `assistant_id` 时），替换全局 `workspace_instructions`；`bundles/web-app.yaml` 移除 `sensor.workspace-instructions`（sensor 本体保留）。
8. **恢复补记**：`askUserQuestion` 暂停恢复时，`capture_resume_memory` 对人工回答补跑蒸馏并写入记忆。
9. **迁移清理**：`scripts/migrate_semantic_memory.py` 把旧 `semantic.json` 原文记录标记 superseded（保留审计），清理小写 `user.md`。
10. **端到端回归**：`tests/e2e/test_cross_run_memory.py` 用 fake extractor 验证 4 轮跨 run 记忆（身份/偏好/纠正/无堆积）。

## Alternatives considered

### 保持原文存档（do nothing）

被拒。原文是噪音，长期累积导致检索退化与上下文膨胀，且用户身份无法被模型正确引用。

### 纯向量库记忆

被拒。先落地确定性的结构化知识层（schema + 蒸馏 + supersede），向量检索作为后续可插拔插件，避免一步引入外部依赖。

### 纯 LLM 自主记忆（无图节点）

被拒。模型直接写文件不可审计、不可幂等，违反 C10 窄门与 Reducer 单写纪律。

### 新增 `memory.retrieved` ItemKind

被拒。`kind="memory"` 已是闭集且渲染器已消费。

## Consequences

- 新 run 中「我是架构师」经 `phase.reflect.memory.extract` 蒸馏为 `category=identity` 结构化事实并落盘；`USER_PROFILE` 段与结构化 CONTEXT 行让模型正确引用身份/偏好。
- 关键词表已删除；`tests/regression/test_no_keyword_markers.py` 静态防回归。
- 模型经 `memory_add` 等工具读写记忆，不再需要 `writeFile` 补救；`USER.md` 回填是系统行为。
- `workspace_instructions` 唯一生产者变为助理 Home 的 `assistant.bootstrap` 投影；项目根 `AGENTS.md` 不再注入 agent manifest。
- 已知后续项：`assistant_bootstrap` / `assistant_id` 已作为可选字段接入 runtime 投影 seam，但 assistant 组合根尚未在构建 `ProductionRuntimeDeps` 时注入具体值（web-assistant 生产装配点待接）。