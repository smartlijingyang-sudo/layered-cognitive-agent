# ADR-0042: 角色库与自动组队（一句话 → 自动选角 → 既有 Team 执行）

## 状态
Accepted

## 背景

产品端的目标体验是「用户问一句话，系统自动组队去做」。现状（2026-08 核实）：

1. `gateway/mode_catalog.py` 只有 5 个硬编码 `AgentRoleTemplate`，10 个固定
   mode 靠这 5 个角色排列组合；用户必须手动理解 routing/board/pipeline 等
   协作词汇才能选对模式。
2. 契约层已具备承接能力：`TeamSpec = members + Governance(LeadSpec |
   Coordination)`（ADR-0034）是团队形态的单一事实来源；`ExecutionGraph` /
   `GraphStrategy` 已实现 DAG 执行；`Agent(role, goal, backstory, ...)`
   三段式门面足以承载外部角色卡内容。
3. 参考实现 agency-orchestrator 验证了「角色库（纯数据内容包）+ 受约束的
   LLM 选角 + 确定性校验修复」模式的可行性；其引擎与角色内容分仓的切法
   与本仓库「声明式 spec 贯穿组合根、契约与实现分离」的哲学同构。

## 决策

### 1. 自动组队是 TeamSpec 的另一个生产者，不是新运行时机制

`TeamCaster.cast(objective, library, llm) -> CastingPlan` 是唯一的异步、
不确定步骤；`build_from_casting_plan(plan, library, llm, ...)` 是纯同步
翻译，与手写 `Agent(...)` + `Team(...)` 走完全相同的路径。TeamComposer /
L0~L3 全程不感知角色是人选的还是 LLM 选的。**L0~L3 零改动。**

### 2. 治理方式复用既有封闭词表，不发明新拓扑

casting 的 `governance.kind` 只能取九个既有值：LeadMandate 的
routing/consult/board 与 Coordination 策略键 pipeline/fan_out/peer_relay/
peer_swarm/debate（graph 留待 Phase 2）。这是对 ADR-0030「一元领域语言」
的复用验证。kind → Coordination 实例用注册表分发
（`lca/application/casting.py::_COORDINATION_FACTORY`），不复制
`gateway/team_factory.py::_coordination_for` 的 if 链形态。

### 3. 内容与机制分离：角色内容不进 `lca` 包

- 契约：`lca/contracts/protocols/casting.py`（RoleLibrary / TeamCaster
  Protocol + RoleCard / CastingPlan 等 frozen dataclass）。
- 默认实现：`lca/application/casting.py`（LLMTeamCaster +
  build_from_casting_plan，L4 组合根）。
- 内容：仓库根 `roles/`（16 张中文产品角色卡，Markdown + YAML
  frontmatter），`gateway/role_library.py::FileRoleLibrary` 扫描解析；
  `AGENCY_ROLES_DIR` 环境变量可整体替换（命名对齐 agency-orchestrator 的
  `AO_AGENTS_DIR`，降低迁移认知成本）。
- gateway 的 `FileRoleLibrary` 不进术语表现役区（反向校验只认 lca 包内
  类名，见 `tests/test_code_conventions.py`）。

### 4. 白名单校验是安全边界，也是可靠性边界

LLM 输出逐项校验：role_id 必须在角色库索引内、kind 必须在封闭词表内、
lead 类必须给出 selected 内的 lead_role_id、角色数 2-6。校验失败带错误
原因重试一次，再失败抛 `CastingError`，经 `execute_run` 既有 try/except
落为 session FAILED（SSE/jsonl 正常收尾，零新增错误管道）。objective 是
用户输入，白名单同时构成 prompt injection 防线：LLM 被诱导输出越界
role_id / 治理方式时一律拒绝。

### 5. `auto` 是独立入口，不进 `MODE_DEFINITIONS`

ADR-0040 的 `MODE_DEFINITIONS` 生成管线以「固定角色的静态目录」为单一
事实源假设；`auto` 是动态机制，硬塞会破坏该前提。`AUTO_MODE_KEY` 为独立
常量，契约生成脚本把它作为独立导出发射给前端，ModePicker 以独立卡片
（「推荐」徽标）呈现，前端默认模式改为 `auto`。API 层默认 mode 保持
`board` 不变（向后兼容直接调用方）。

### 6. 组队提示词走既有模板机制，但渲染方式为精确替换

模板 `lca/cognition/brain/prompts/casting_prompt.md`，经
`load_builtin_prompt` 加载——遵守「Prompt 模板迭代不碰 Python」约定。
因模板内嵌 JSON 示例花括号，与 `str.format` 冲突，占位符
`{role_catalog}` / `{objective}` 用精确替换渲染（模板头部有注释警告）。
模板含 `ROLE: caster` 标记行，与 `tests/harness/scripted_llm.py` 的角色
提取约定对齐，保证金测可脚本化。JSON 提取复用
`decision_parser.extract_json_block`（从私有方法提升为公共函数，两处共用
一份逻辑）。

## 已知妥协（显式登记，非遗忘）

1. **`run_executor.execute_run` 有一个 `if mode == AUTO_MODE_KEY` 分支**：
   这是二元异步分界（casting 必须 await，同步查表路径装不下），不是类型
   分发链，全仓库仅此一处。若未来出现第二个特殊入口，重构为 runner
   注册表而非加分支（代码内有注释说明）。
2. **`build_from_casting_plan` 与 `_build_agent` 约 8 行 kwarg 组装重叠**：
   两者收敛在同一公共门面 `Agent(...)`。提取判据：出现第三个调用方，或
   两侧 kwargs 开始分叉时再抽共享 helper，不做提前提取。
3. **casting 无可观测 journal 事件**：Phase 3 在 `JOURNAL_CATALOG` 登记
   `CastingCompleted`（唯一发射模块 + AST 守卫），自动流入 Run Card。
   现阶段 casting 决策经 structlog 记录，不预埋半成品事件。
4. **每 auto run 多一次 LLM 调用**：延迟与成本换「零选模式门槛」。基于
   objective 哈希的结果缓存是后续优化项，Phase 1 不做。

## 分阶段路线

- **Phase 1（本 ADR 落地范围）**：角色库 + 固定协作模式选角（八词表，
  graph 除外）+ 网关接线 + 前端 auto 入口。
- **Phase 2**：解锁 `graph` 治理。`GraphNode.config` 增加可选
  `task_template` 键（`GraphStrategy._build_task_for_node` 优先渲染，缺省
  回退现行为，向后兼容），CastingPlan 增加图边描述，实现自动 DAG 编排。
- **Phase 3**：`CastingCompleted` journal 事件（选角可回放）；可选的
  objective 哈希缓存。

## 后果

- 用户一句话即可获得针对性组队，不再需要理解协作词汇表；固定 mode 保留
  为显式选择，行为不变。
- `lca` 新增两个文件（contracts/protocols/casting.py、
  application/casting.py）+ 一个提示词模板 + `decision_parser` 提取函数
  公开化；gateway 新增 role_library.py、三处小改；前端默认体验变更。
- 角色库是可插拔内容包：换领域只需换目录，框架代码不动。
- Alice/Bob 仅存在于 `tests/harness`（确定性探针，ADR-0040 豁免区），
  产品路径无任何临时角色痕迹。
