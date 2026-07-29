
这是我在上面已经做的分析，直接给出完整重构方案（基于对代码实际内容的核对，不是单纯根据文件名猜测）：

## 总体判断
框架的分层纪律很好——大部分"名字相同/相似"的文件（如两处 `loop_judge.py`、两处 `team_progress.py`、`memory.py` 在 contracts 和 layer1 都出现）都是刻意的 **"contracts 放 Protocol/数据，对应层放实现"** 模式（ADR-0015 明确要求"contracts 不放行为类"），**这些不是冗余，不要合并**。真正该清理的是下面 7 处。

---

### 1️⃣ 最严重：L4 组合根"双头 + 循环依赖 + 兼容包袱"
`layer4_app/assembly.py`（新组合根）和 `layer4_app/defaults.py`（旧组合根）**互相**懒加载对方：
- `assembly.assemble_base_agent()` 内部 `from lca.layer4_app.defaults import ...`
- `defaults.build_body()` 内部又 `from lca.layer4_app.assembly import build_body_from_shared`
- `defaults.py` 尾部还挂着 `_DEPRECATED_BUILDERS` + `__getattr__` 做废弃符号兼容（`_build_brain`、`_build_hooks`、`build_runtime`）

**方案**：
- `defaults.py` 改名为 `component_defaults.py`，只保留纯注册职责（`register_defaults`/`ensure_defaults`/`build_default_transport_registry`/`build_team_transport`），不再依赖 `assembly.py`。
- `build_body()` 兼容 shim + `_DEPRECATED_BUILDERS`/`__getattr__` 整体挪到独立的 `layer4_app/_legacy.py`，标注下个大版本删除。
- `assembly.py` 只保留装配逻辑，不反向 import 注册逻辑。

### 2️⃣ `hook_registry.py` 违反 SRP
`SimpleHookRegistry`（注册/触发钩子）之外，混入了约 70 行的**可观测性字段提取 + 密钥脱敏**逻辑（`_extract_span_attributes`/`_sanitize`/`_truncate`/`_safe_repr`，含正则 `_SECRET_PATTERN`）。

**方案**：拆到 `layer0_infra/observability/redaction.py`，`SimpleHookRegistry` 只做"注册+触发"，脱敏逻辑作为独立可复用单元注入。

### 3️⃣ `MemorySystem` Protocol 的"语义别名"冗余
`perceive_and_retrieve`/`perceive`、`update_multi_level`/`update` 互为别名，`SimpleMemorySystem` 两套都实现了一遍，容易让人不知道该调用哪个。

**方案**：二选一作为唯一 API（建议留短名 `perceive`/`update`），另一套标记 deprecated 或直接删除。

### 4️⃣ Brain 目录散文件与 `map_modules/` 边界模糊
`brain/guarded_coordinator.py`（装饰 `TaskCoordinator`）单独放顶层，而被装饰的 `task_coordinator.py` 在 `brain/map_modules/` 里；`brain/skill_router.py` 翻遍 `assembly.py` 未见接入组合根，疑似孤儿代码。

**方案**：`guarded_coordinator.py` 移入 `map_modules/`；`skill_router.py` 要么补接入点要么删除/挪 examples；`reasoner.py`/`critic.py`/`decision_parser.py`/`synthesizer.py`/`candidate_evaluation_pipeline.py` 可归入新建的 `brain/react_pipeline/` 子包，让 `brain/` 顶层只剩装配入口 `modular_brain.py`。

### 5️⃣ `prompt_manager.py` 放错层级
在 `layer1_cognitive/` 顶层和横切基础设施 `event_bus.py`/`hook_registry.py` 并列，但实际只被 Brain 的 `Reasoner` 使用。

**方案**：移入 `brain/prompts/`，与 `_loader.py` 合并成一个子包，"prompt 相关的都在一处"。

### 6️⃣ `SharedMemoryTool` 位置与同类 Tool 不一致
其他 Tool 实现都在 `layer0_infra/tools/`，唯独它在 `layer3_agent/shared_memory/`。

**方案**：至少在 `layer0_infra/tools/__init__.py` 加指引说明；更彻底则把 `TeamSharedMemoryStore` + `SharedMemoryTool` 一起挪进新建的 `layer1_cognitive/shared_memory/`。

### 7️⃣ 待确认：`SkillRecord`/`KGTriple` 疑似超前设计
`contracts/memory.py` 定义了这两个 dataclass，但 `SimpleMemorySystem` 未见任何消费逻辑，疑似 YAGNI。

**方案**：确认无实现引用后删除，或写占位 ADR 说明"为未来技能库/知识图谱预留"。

---

### 优先级
1. #1（组合根去循环）—— 唯一涉及真正架构违规，风险最高，优先做。
2. #3、#2 —— 改动小、收益大，不影响外部 API，可以和 #1 一起做。
3. #4、#5、#6 —— 纯目录搬家，建议留到专门的"整理 sprint"做，别和功能改动混在一个 PR。
4. #7 —— 需要你跑一次全仓库引用搜索确认后再决定删留。
