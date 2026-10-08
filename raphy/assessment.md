# Raphy Assessment — Round 9 (2026-10-08 09:20, branch `raphy/arch-20261008-0118`)

ASSESS ONLY. 本轮按硬化版 `raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`
→ git log 热点定域 → CONTEXT.md + 相关 ADR（ADR-0292 精读）→ 三区 friction walk（5 问必答，
端到端精读非 grep）→ mandatory runtime verification（mock LLM 真跑：basic / tool-call / 双 run）
→ duplication 副扫描 → self-grilling → stories 入 prd.json（`userStories` 键，RA-031 起编号）。

## Scope（YAGNI）

`git log --oneline -40/-60` 生产代码热点（排除已做故事领地 + 纯测试 + 禁区）：
- `lca/nodes/intervene/`（approve_gate.py + interrupt.py）— be4f52dd1 / ca9a07a63 两笔
  ADR-0292 授权语义 feature，新鲜热区；非 ralph Round 2 领地（Round 2 的 DecisionGates 是
  `brain/decision_gates/`，不是 `nodes/intervene/`）。可走。
- `lca/infrastructure/tool_defer/`（policy.py + session.py + tool_search.py）— Defer tool L1
  生产默认的深水区；×2 in -60；非禁区。可走。
- `lca/plugins/observability/cli/debug_trace_provider.py` — cf8d64a53 刚 pin 了
  debug-trace explain_failure 路由；`e51902b07/2bb3ceefc` 的 else 机械触碰区（已修复，
  不重审）。可走。
- 避开：model_visible（RA-024/025）、schedulers（RA-026）、fold（RA-027）、user_cli（RA-028）、
  simple_body/agent_state（RA-029）、anomaly（RA-030）、cognitive_agent/loop_budget（RA-023）、
  observability/adapters（iter-tests revert 战）、ralph Round 2 / lca-1000 / memory /
  gate_chain_strategy.py。

三区 friction walk 定域（精读文件，非 grep）：
- **Area A**：`lca/nodes/intervene/approve_gate.py`（380 行全文）+
  `lca/nodes/intervene/interrupt.py`（140 行全文）+
  `lca/nodes/act/authorize/authorize.py`（outputs/emit 段）+
  `bundles/act/act_subgraph.yaml`（gate 节点 inputs/outputs + 边）。
- **Area B**：`lca/infrastructure/tool_defer/policy.py`（150 行全文）+
  `lca/infrastructure/tool_defer/session.py`（~420 行全文）+
  `lca/infrastructure/tool_defer/tool_search.py`（230 行全文）。
- **Area C**：`lca/plugins/observability/cli/debug_trace_provider.py`（全文）+
  `lca/plugins/observability/cli/debug_seam.py`（全文）。

## Friction walk — 5 问必答

### Area A：nodes/intervene（approve 门）

1. **理解一个概念要在多少小模块间跳？** "审批门凭什么放行"要跳 4 处：`act.authorize`
   （发出 `approval_required` bool + `approval_requirement` 对象）→ `act_subgraph.yaml`
  （gate 的 yaml inputs 列的是 `approval_required`）→ `approve_gate.py` 的 executor
   （读的却是 `approval_requirement`）→ ADR-0292 §10（grant-absence 语义）。"要不要批"
   有三个名字（`approval_required` / `approval_requirement` / `decision.needs_approval`），
   分散在 policy engine / yaml / executor 三处——典型的 shallow-module sprawl。
2. **shallow module？** `_grant_absence_refusal(decision, req: object | None)`：接口几乎和实现
   一样复杂——`getattr(req, "required", False)` 的鸭子类型就是在用代码重复描述
   "有个 required 字段"。deletion test：现在删掉它只移动复杂度；但把它 typed 化
   （`req: ApprovalRequirement | None`，contracts 里现成的 frozen dataclass）之后，
   它才 earn 存在。`_route_refusal_to_evidence` 是薄的 adapter：删掉它，复杂度就散进
   `safe_executor` 的同款仪式——这正说明那份仪式该有自己的 module（→ RA-032）。
3. **为可测试抽出的纯函数藏 bug？** 没有抽取问题；但真正的语义藏法是：
   `_grant_absence_refusal` 里 `hasattr(req, "required")` 为 False 时**静默回退**到
   `decision.needs_approval`——而 ADR-0292 §10 恰恰说模型自报的 `needs_approval`
   不可信（幻觉可清）。一个"看起来像对象但缺 required"的 req 会无声降级到不可信信号。
   类型本该在 seam 上保证，却在调用点用 getattr 补——no locality。
4. **leaky seam？** **有，三处**：(a) executor 从 `port_values` 读 `approval_requirement`，
   但 `declared_inputs=(decision, command)` 没声明——违反 ADR-0235 "reads typed ports
   only"；(b) yaml 的 gate inputs 列的是另一个名字 `approval_required`（bool），executor
   根本不读它；(c) 两个输出分支都 echo `approval_requirement`，但 `declared_outputs`
   没声明。另外 executor 自称 "pure transform"，实际读 ambient TrustEnvelope
   （`get_current_trust_envelope()`）并写 evidence ledger——docstring 与实现对不上。
5. **不可测试/绕过接口测试？** grant-absence 路径的测试必须往 `port_values` 里"走私"
   `approval_requirement`——declared interface 测不到它（"the interface is the test
   surface"）。`hasattr` 降级分支生产永远传 `ApprovalRequirement`，不可达但无类型保证。

### Area B：infrastructure/tool_defer

1. **跳几处？** "本轮 model 看到哪些工具"要跳 6 处：policy（eager 集合）→
   `session.update_turn`（分组 + unknown 兜底）→ `session.render_turn`（wire + catalog）→
   `think.history.assemble`（model 可见切片）→ `tool_search`（loader）→
   `capability_bindings`（ContextVar 镜像）。有 sprawl，但每处职责清晰（policy=策略，
   session=状态，assemble=投影），locality 尚可——记为观察，不立案。
2. **shallow？** ContextVar 三件套（set/reset/current）薄，但属 run-entry ritual
   （与 `current_tools_service` 同构）；deletion test：删掉只是把 ContextVar 调用散到各处，
   不收敛——不适用。`_classify_args`/`_ArgShape` 已收敛（不立案）。
3. **testability 错位？** `update_turn` 的 fail-soft（unknown parking）是 2026-10-01
   真事故后的刻意 backstop，fail-fast（无描述的 declared namespace）是 ADR-0256 B2
   显式要求——逻辑内聚在 `update_turn` 里，有 locality。不适用。
4. **leaky seam？** `_tool_to_spec` 与 `think.history.assemble._tool_to_spec` 逐字相同，
   但注释写明是刻意层边（"infrastructure must not import L2 nodes"）——deliberate，
   不适用。`getattr(tool, "namespace", "")` 的鸭子类型是 wrapper 事故史后的刻意
   fail-soft，不适用。
5. **测试死角？** `tests/infrastructure/tool_defer/test_defer_catalog.py` 钉 catalog；
   `render_turn`/`load_namespaces` 有测试面。不适用。

### Area C：plugins/observability/cli（debug trace）

1. **跳几处？** 小——理解 "trace 命令"只需 `_DebugTraceCommand.run`（~60 行 flag dispatch）
   + `TraceInspector`。不适用。
2. **shallow？** `_render_event`（debug_trace_provider.py:99）**零调用者**——不是 shallow，
   是 dead code（journal.py 的同名函数是另一个、有调用者）。`Config(BaseModel)` 在
   debug_seam.py / debug_trace_provider.py 各一份——cosmetic duplicate，无杠杆。
   不立案。
3. **testability 错位？** `run()` 是 `kwargs.get` 的 flag-dispatch；
   `inspect_trace(focus=focus)` 上的 `# type: ignore[arg-type]` 是残留（focus 已是 str）。
   无隐藏 bug 证据。不适用。
4. **leaky seam？** 无。
5. **测试死角？** `tests/scenario/cli/test_cli_debug_trace.py` 钉注册 + explain_failure
   路由。不适用。

## Runtime verification（mandatory，MockLLMAdapter，LLM_API_KEY=dummy）

自写探针 `/tmp/raphy-round9-runtime.py`（`ssh252 'python3' < script` 走 stdin，
`PYTHONPATH=/home/lichao/layered-cognitive-agent`）：
- A basic run（"1+1等于几?"）→ **completed** ✅
- B tool-call run（NoopTool + 首轮 tool_call mock）→ **completed** ✅
- C 同一 agent 连续两次 run → **completed / completed** ✅
- 无 crash/hang/静默失败。10-07 P0（RA-023）本轮未复现——Round 8（05:15）已复测
  "非收敛 run 返回 failed Result 无抛错"，本分支含 RA-023 merge（6324b2aad），不再重跑。

## Duplication 副扫描（friction walk 之后）

- `current_bound()` 全仓 4 处：`runs/tools.py:368`（fail-loud + typer.Exit）、
  `fact_gateway.py:198`（journal 镜像）、`safe_executor:162` + `approve_gate:125`
  （"ambient → evidence_binding().store → 无绑定 no-ref" 逐字同形）。前两者是不同形状，
  不收编；后两者 two = real（→ RA-032）。
- `getattr(req, ...)` 全仓仅 approve_gate 一处（→ RA-031 的一部分）。
- 其余：`_render_event` dead（上文，不立案）、`Config` ×2 cosmetic（不立案）、
  `_classify_args` 已收敛（不立案）、`_tool_to_spec` 刻意层边（不立案）。

## Candidate table

| ID | Files | Problem | Solution | Benefits（locality+leverage） | Strength |
|----|-------|---------|----------|------------------------------|----------|
| RA-031 | `lca/nodes/intervene/approve_gate.py`, `bundles/act/act_subgraph.yaml` | 门的 declared interface 说谎两处：`declared_inputs` 不含 executor 实际读的 `approval_requirement`（yaml 列的却是另一个名字 `approval_required`，executor 根本不读）；`req: object \| None` + `getattr/hasattr` 鸭子类型，而 contracts 里有现成的 frozen `ApprovalRequirement`；"看起来像对象但缺 required" 会静默降级到 ADR-0292 §10 明言不可信的 `decision.needs_approval` | `declared_inputs`/`declared_outputs` 补上 `approval_requirement`（yaml inputs/outputs 同步）；`_grant_absence_refusal` 签名改为 `req: ApprovalRequirement \| None`，删鸭子类型，`req is None → decision.needs_approval` 的回退显式化；class docstring 去掉 stale 的 "pure transform"，写清 ambient TrustEnvelope 读 + evidence ledger 写 | locality：门"需要政策信号什么"收进 declared interface，测试可经 interface 驱动 grant 门（"the interface is the test surface"）；leverage：§10 是安全关键路径，类型即文档，后续改 grant 语义不再靠读实现猜形状 | **Strong** |
| RA-032 | `lca/nodes/intervene/approve_gate.py`, `lca/cognition/body/executor/safe_executor/executor.py`, `lca/infrastructure/observability/`（新 seam 落点） | "从 ambient observability 解析 evidence store，无绑定走 no-ref" 的仪式在两处逐字重复（safe_executor._resolve_evidence_pair / approve_gate._route_refusal_to_evidence 内联版）；two = real seam | 在 `lca/infrastructure/observability` 立 `resolve_evidence_store()` seam（deferred import 保留，无绑定/无 store → None，fail-soft 契约不变）；两处调用方收敛到它；safe_executor 保留 `(store, policy)` 元组形状（store 走新 seam）；落点选 observability 而非 safe_executor——nodes（L2）不得 import cognition/body，层向论证 | locality："怎么从 ambient 拿到 evidence store" 成为一个 module 的知识；leverage：第三个消费者出现时直接复用，不再手写第三份仪式 | Worth exploring |

## Top recommendation

**先做 RA-031**。理由：① 它违反的是项目明文规则（ADR-0235 "reads typed ports only"），
不是审美分歧；② §10 grant 检查是安全关键路径，fail-closed 语义现在靠 `object` +
`getattr` 承载——类型系统本可免费提供的保证，被鸭子类型主动放弃了；
③ deletion test 最脆：declared interface 删掉（或保持说谎），复杂度不收敛，
测试永远要"走私"端口值。RA-032 是干净的 "two = real" 收敛，排第二。

## Self-grilling

### RA-031 — 门的 approval_requirement 端口：声明 + 定型

- **Constraints**：ADR-0292 §10 语义零变更（fail-closed grant 检查；`content_origin`
  仅审计元数据；拒绝走 `terminal.commit` + evidence ledger）。ADR-0237 的 PortRegistry
  避碰：`approval_requirement` 的 echo 值与 `act.authorize` 发出的同一对象，
  last-write-wins 下无害；声明它不改变运行时接线（spike 须先确认：runtime 把边输出
  送进 `port_values` 时不校验 `declared_inputs`——若校验，则声明是修复而非装饰）。
  yaml 的 gate inputs 当前列 `approval_required`（bool，executor 不读）——spike 定它是
  历史残留还是另有消费者，再决定删/留。
- **Dependencies**：上游 `act.authorize`（发两个端口）；下游 `act.envelope`（收 decision；
  gate 的 echo 是否被下游消费——当前 `declared_outputs` 不声明 echo，若下游真在读，
  声明是补洞）。调用链：`_grant_absence_refusal` 仅 gate 内用；`ApprovalRequirement`
  在 contracts，gate 已 import 同包的 `Decision`，无新层边。
- **Shape of the deepened module**：`declared_inputs += (PortName("approval_requirement"),)`，
  `declared_outputs += (PortName("approval_requirement"),)`；yaml 同步；
  `_grant_absence_refusal(decision: Decision, req: ApprovalRequirement | None)`；
  `needs_approval = req.required if req is not None else decision.needs_approval`；
  docstring：删 "pure transform"，写清 ambient TrustEnvelope 读 + evidence ledger 写。
- **Test survival**：`tests/contracts/test_adr0292_authorization_semantic_isolation.py`
  钉 §10 语义；`test_act_subgraph_yaml_e2e.py` / `test_hitl_e2e_loop.py` 钉接线。
  新测试：typed `ApprovalRequirement(required=True)` + 未授权 tool + 无 TrustEnvelope
  → `terminal.commit` + echo 保留；`(required=False)` → `decision.needs_approval` 主导。
- **Deletion test verdict**：concentrates——"门需要什么政策信号"从实现+走私收进
  declared interface。

### RA-032 — ambient evidence-store 解析收进一个 seam

- **Constraints**：零行为变更；两处都保留"无绑定 → no-ref" 的 fail-soft 契约
  （tests/offline 路径依赖它）；approve_gate 的 deferred import 纪律保留
  （load 期不对 observability 取硬依赖）。
- **Dependencies**：调用方 = safe_executor（2 处）+ approve_gate（1 处）。
  seam 落点必须是 `lca/infrastructure/observability`（两处已从它 import
  `current_bound`；nodes 绝不能 import `cognition/body`——层向论证）。
  `runs/tools.py` / `fact_gateway.py` 的 `current_bound()` 是不同形状，out of scope。
- **Shape**：`resolve_evidence_store() -> EvidenceStore | None`；
  safe_executor 的 `_resolve_evidence_pair` 改为调它取 store（policy 另取，
  元组形状不变）；approve_gate 的 `_route_refusal_to_evidence` 内联仪式删掉改调它。
- **Test survival**：safe_executor 的 no-ref 测试；ADR-0292 测试。
  新测试：unbound → None；fake bound 有/无 store → store/None。
- **Deletion test verdict**：concentrates——"怎么从 ambient 拿到 evidence store"
  成为 observability 包自己的知识。

## 丢弃（有证据）

- `interrupt.py` 的 `spine_seq` 缺席时回退 `SpineContext.current_sequence()`：
  读了全文；declared-but-optional 带 ambient fallback，与 RA-031 同类但属可选端口的
  显式语义（`del context` + 明确 TypeError），无说谎成分——不立案，记观察。
- `debug_trace_provider.py:99` `_render_event`：全仓零调用者，dead code——但属
  机械清理，无杠杆，不立案（若顺手删，单行 diff 即可）。
- `tool_defer.session._tool_to_spec` 与 `think.history.assemble` 的重复：注释写明
  刻意层边（"infrastructure must not import L2 nodes"）——deliberate，不立案。
- `tool_defer` 的 ContextVar 三件套 / `_classify_args` / fail-soft unknown parking：
  读完全文；薄但 load-bearing ritual / 已收敛 / 事故后的刻意 backstop——不立案。
- debug 双 `Config(BaseModel)`：cosmetic，不立案。
- Area B 的 "6 处跳才看清本轮工具视图"：每处职责清晰（policy/session/assemble），
  locality 尚可——观察中，未到立案阈值。
- 10-07 P2（`run(None)` / `NativeToolCall.arguments` str）：仍 defer 给 iter-quality，
  本轮未重立案（patterns 已有记录）。

## Round 10 — assess (2026-10-08 12:06, branch `raphy/arch-20261008-1206`)

ASSESS ONLY。按硬化版 `raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`
（codebase-design/grilling/domain-modeling 不存在，用 deepening 词汇表 + grilling 纪律代替）→
`git log --oneline -45` 定热点 → CONTEXT.md + `docs/adr/` 目录 → 三区 friction walk 拆给
3 个全新会话子任务（5 问必答、端到端精读非 grep）→ mandatory runtime verification（mock LLM
真跑）→ duplication 副扫描 → self-grilling → stories 入 prd.json（`userStories` 键，RA-033 起编号）。

### Scope（YAGNI）

`git log --oneline -45` 生产代码热点（排除已做故事领地 + 纯测试 + 禁区）：
- `78034deea`（fix(sandbox): bind the per-run assistant workspace at session creation）+
  `3619ca1e5`（feat(computer): project workspace-relative display paths at the single
  model-visible seam）— sandbox/workspace 热区；非禁区。可走。
- `cf8d64a53`（pin debug-trace explain_failure routing）、`b802ac3ae`（pin stack_heal
  skip-spawn）— CLI 诊断热区；RA-028 已收敛 daemon status/heal 归 DaemonService（不重审）。可走。
- `d06d6f64f`（refactor(act): enumerate tool_calls in envelope minting loop）、
  `8deaef5d4`（refactor(graph): zip parallel output tuples in translate_outputs）—
  act/graph 热区；RA-013 已收敛 SimpleBody 的 EffectReceipt（不重审）。可走。
- 避开：ralph Round 2 领地（DecisionGates/Ingest/ContextFiles shims/Read Runs micro-dirs/
  `infrastructure/tools/assistant/`/`lca/cognition/memory/`）、lca-1000 迁移领地、
  `gate_chain_strategy.py`、CLI surface→contracts 刻意规则。

**评估中途的 HEAD 移动**：12:11:45 并发 lane 在本分支主 checkout 上直接提交
`f21cd0af2`（fix(sandbox): point guest script ROOT at the session root on the Local plane，
`preamble.py` 的 ROOT 烘焙→`LCA_GUEST_ROOT` env 读取 + `local/adapter._exec_shell` 导出该 env +
`_rewrite_command(command)`→`(command, root)`）。子任务 A 一度被误判为写树者；reflog 证实为
并发提交（作者栏 `lichao <lichao@local>` 为 252 通用身份，不能单独作为归属依据，但 A 的
read-only 命令记录与 reflog 时间线一致）。A 区结论以 f21cd0af2 之后为准；流程教训记入
progress.txt（长评估中用 `git show <sha>:` 锁定版本读文件；并发 lane 绕过了 AGENTS.md 的
worktree 纪律——直接写了本分支的主 checkout）。

### Friction walk 摘要（三子任务，5 问必答）

**Area A（sandbox workspace 绑定 + computer display paths）**：读 `78034deea`/`3619ca1e5`/
`f21cd0af2` diff、`session/projections/display_paths.py` 全文、`observation_surface.py` 全文、
`local/adapter.py`（HEAD：`__init__`/`_rewrite_command`/`_exec_shell`/`_run_code`/
`create_session`/`run_in_session`）、`locator.py::assistant_workspace_root`、`assistant_scope.py`、
`tool_journal.py`（commit_body_tool_execute_end）、`run_session_writer.py`（append_tool_result）。
- Q1 sprawl："模型最终看到什么"横跨 6 模块（contracts Observation→observation_surface→
  project_display_paths→fence_external_content→build_openai_tool_result_message→RunSessionWriter→
  derive_messages）；且 `observation_surface` docstring 声称消费者只有 2 个，实际
  `tool_journal` 是第 3 个——文档本身加剧跳转。
- Q3 无 locality：`project_display_paths` 的 7 个单测全绿，但两个真实风险在调用侧——
  str payload 永不经过投影（调用处语义决策）、allowlist 覆盖度取决于各 tool 的 key 命名习惯；
  `_rewrite_command` 纯函数正确，但 f21cd0af2 之前的 bug 藏在调用方传参（隐式 `self._host_root`）。
- Q4 泄漏：cognition 层的 `observation_surface` 直接 import infrastructure 层的 display_paths
  （SANDBOX_MOUNT_ROOT 经它渗入 cognition）；guest ROOT 三视图（preamble 烘焙/adapter env/
  rewrite 文本）知识分散。
- Q5 未测试：Onlyboxes adapter 的 workspace_root 忽略分支零覆盖；`run_terminal` 的
  stateless 回落（`session_id=""` → boot 默认根）WSOT-08/09 未覆盖；`_rewrite_command` 的
  全文替换误伤边界无 pin；没有任何测试 pin 住"journal 存投影还是原文"。

**Area B（CLI doctor / stack_heal / debug-trace explain_failure）**：读
`debug_trace_provider.py`/`debug_seam.py`/`trace_inspector.py`（327 行）/`trace_tool_runner.py`/
`helpers/_helpers.py`/`diagnosis/failure_explainer/plugin.py`（202 行）/`run_explain.py`/
`runs/tools.py`/`serve.py`/`steps.py`（stack_heal 段）/`doctor/facade.py` + 4 个 pass 头部。
- Q1 sprawl："explain_failure" 散在 10 个小模块 + 一个同名异构体
  （`diagnosis/failure_explainer/plugin.py::explain_failure` 纯函数，完全不同的算法）。
- Q3 无 locality：本域历史上所有真实事故都在调用/路由层（`e51902b07` 误删 else 致
  explain_failure 报告被覆盖、stack_heal 健康 kernel 重复 spawn），而测试火力集中在纯算法上——
  测试与 bug 的 locality 错位。
- Q4 泄漏：`_helpers._inspector_events` 用 `getattr(inspector, "_events", ())` 穿透
  `TraceInspector` 私有属性；loader↔inspector 的失败判定靠 `data` 字典的隐式约定
  （`_event_from_payload` 的 setdefault 注入）；`stack_heal` 对具体类做 isinstance
  fail-loud（daemon 侧用的是 runtime-checkable Protocol）。
- Q5 未测试：PrivilegeDoctor/ResourceDoctor/TrustDoctor 生产零消费者（facade 只编排 4 个）；
  `debug_trace_provider._render_event` 零调用零测试（死代码，未立案，机械清理）；
  `MinimalReproductionPackage.evidence_refs` 恒为空元组（字段级小洞，未立案）。

**Area C（act envelope minting + graph translate_outputs）**：读 `envelope.py`（act 铸造循环）/
`contracts/protocols/act/command/envelope.py`（`mint_envelope`，356 行全文）/
`subgraph_run.py`（`translate_outputs`/`translate_inputs`/PortRegistry 播种）/
`nodes/think/llm/invoke.py`（247 行，step_id 关系）/`ids.py`（`step_id_for`）/
`effect/execute.py::_owed_rows`（§170–240）/`pipeline_safe_executor.py`（§230–340，第二铸造点）/
`cognition/wire/envelope.py`（第三铸造点）/`remember/write.py`（第四铸造点）/
`effect_receipt.py`（RA-013 领地，只读）/`graph_spec.py`（inner_io_schema lift）。
- Q1 sprawl："铸造一个合法 envelope 需要什么"要跳 6 模块×3 层；`mint_envelope` 只管非空
  校验不管 metadata 语义，metadata 语义由 concept 层的 `_owed_rows` 用字符串 key + raise 定义——
  生产者与消费者隔着一个 phase，seam 是 `Mapping[str, Any]`。
- Q2 浅模块：`outer_declared_outputs_of`（6 行，具名函数+`__all__`+monkeypatch 别名的仪式
  远大于实现）；`translate_inputs`（dict comprehension 配 25 行 docstring）；
  `PipelineSafeExecutor.execute` 里的 dummy `mint_envelope(...)` 调用纯为骗过
  `check_command_envelope_required.py` AST gate（注释自承；RA-013 邻域，只记录不立案）；
  `warn_deprecated_envelope_constructor` 全仓零调用者（死代码，未立案）。
- Q3 无 locality：`translate_outputs` 纯函数有 60 行测试，但风险在调用者——
  `DefaultSubgraphRun.run` 的 PortRegistry 播种舞（outer snapshot→set_outer_input 分层→
  iron rule 1 setdefault→kernel 私有 key）零单元测试；消费者测试手写 `_mint` 副本逐字复制
  act.envelope 的 metadata 契约——契约漂移时测试照样绿。
- Q4 泄漏：metadata 塞活对象（`state`/`decision`/observation）穿过 envelope seam，
  `command_envelope_to_dict` 自称 JSON 友好只是浅 `dict()`；kernel 经
  `node_config["_port_registry"]` 字符串后门绕过 frozen 的 StrategyContext seam。
- Q5 未测试：act.envelope 的 delegations 分支零覆盖（metadata 无 `tool_call_id` 形状
  unpinned）；attribution 链从未被真实生产者执行过；`translate_outputs` 的 tier 1/4 无
  直接测试；`_model_visible_identity` 的 cursor 回退语义（回退到 `state.step` 得
  `step-000`）与 `step_id_from_cursor`（`step-unknown-{template_id}`）不一致，
  invoke.py docstring 的 "same degradation as primitive.llm.call" 声称不准确——
  RA-025 未竟之地，只记录不立案。

### Runtime verification（强制，MockLLMAdapter，本分支实测）

`~/workspace/raphy-runtime-check-20261008-1206.py`，`LLM_API_KEY=dummy`：
- basic run → `completed` ✅
- 带 tool call 的 run（OneToolMock：首轮发 noop tool_call，次轮文本作答）→ `completed` ✅
- 同一 agent 连续两 run → `completed/completed` ✅
- RA-023 回归（InfiniteMock + max_steps=5）：返回 `failed` Result，**无抛错** ✅——
  修复在本分支生效（progress.txt 基线 05:15 的结论保持）。
- **无新 P0**。10-07 P2（`run(None)` TypeError、`NativeToolCall.arguments` 传 str 晦涩报错）
  仍 defer 给 iter-quality，本轮未重立案。

### Candidate table

| ID | Files | Problem | Solution | Benefits（locality+leverage） | Strength |
|---|---|---|---|---|---|
| RA-033 | `lca/nodes/act/envelope/envelope.py`；`lca/contracts/protocols/act/command/envelope.py`；`lca/nodes/concept/effect/execute.py`；`tests/plugins/concept/test_effect_execute_tool_result_surface.py` | 生产者（act.envelope）与消费者（`_owed_rows`）对 `metadata["tool_call_id"]`/`metadata["effect_class"]` 的约定靠无类型字符串 key + 运行时 raise 维系；消费者测试把铸造逻辑手抄一份（`_mint`），契约漂移时测试照样绿；另两处铸造点往 metadata 塞 `state`/`decision`/observation 活对象，破坏"JSON 友好"宣称 | (a) 在 envelope.py 旁定义 frozen dataclass（如 ToolsEnvelopeMeta）为唯一 seam，act.envelope 构造它、`_owed_rows` 经访问器读它；(b) 测试的 `_mint` 改调真实 `ActEnvelopeExecutor`（或共用 helper）；(c) metadata 只放 id/ref，不放活对象 | locality——metadata schema 归一个模块，生产者与消费者无法静默漂移；leverage——加 effect_class（如 delegations 要 attribution）只改一处 seam。测试 locality：attribution 链第一次被真实生产者 pin 住 | **Strong**（逐字复制可测量；`_owed_rows` 的 fail-loud raise 本身就是 load-bearing 证据） |
| RA-034 | `lca/cognition/body/emit/observation_surface.py`；`lca/loop/commit/tool_journal.py`；`lca/runtime/session/run_session_writer.py` | docstring/commit message 声称"只在一处构建、由两个消费者共享"且"receipts and the journal keep absolute process paths"；实际 `tool_journal.commit_body_tool_execute_end` 是第 3 个调用者，而 journal 持久化的正是投影后的文本——不存在绝对路径副本 | 二选一：(a) 承认 journal 存的就是 display 投影，修正 docstring/ADR 表述；(b) 拆 `observation_content` 为 display/process 双视图，journal 写 process 视图 | locality——"谁存什么"与投影策略收敛到一处；leverage——display 规则变更语义可信，不会有人误查 journal 里的绝对路径 | **Strong**（第 3 调用者与 journal 存储内容逐行验证） |
| RA-035 | `lca/plugins/diagnosis/failure_explainer/plugin.py`；`tests/observation/test_explainer_algorithm.py` | docstring 宣称"模板方法 + 数据驱动规则表"，但 `ROOT_CAUSE_TEMPLATES`（6 条）从未被 `explain_failure()` 引用——算法是 3 个硬编码循环；唯一引用者是断言 kinds 的单测 | 删 `ROOT_CAUSE_TEMPLATES` + `_Template` + docstring 规则表段落；改写测试断言真实 3 循环分支；顺手可把 diagnosis 侧 `explain_failure` 重命名为 `explain_from_diff` | locality——单模块 + 一个测试；leverage——消除"读文档以为是规则引擎、读代码发现是硬编码"的误导 | **Strong** |
| RA-036 | `lca/contracts/protocols/act/command/envelope.py`（新增 helper）；`lca/nodes/act/envelope/envelope.py`；`lca/nodes/remember/write/write.py`；`lca/cognition/wire/envelope.py`；`lca/cognition/body/executor/pipeline_safe_executor.py` | 四个铸造点的 idempotency_key 公式各自发明（`{plan}:{node}:{decision}:{index}` / `{inv}:{tool}` / `{op}:{ref}:{target}` / `{plan}:{node}:{decision}`），不变量只写在 docstring | 在 `mint_envelope` 旁加 `idempotency_key_for(*, plan_ref, scope_ref, decision_id, discriminator)`，各点只传自己的 discriminator | locality——key 语法归一个模块；leverage——key 要加成分（如 args hash）只改一处 | **Worth exploring**（当前公式各自成立，价值预防性） |
| RA-037 | `lca/infrastructure/sandbox/local/adapter.py`（`run_in_session` 回落分支） | `create_session` 把 per-run 根只记内存 dict；`run_in_session` 对未知 sid 用 boot-time `_host_root` 静默重建目录继续执行——静默错目录；同家族：stateless 回落 `session_id=""` 回到 boot 默认根 | 未知 session_id 直接抛错，强制先 `create_session`；stateless 路径显式标注降级语义 | locality——session 根真相只在 `create_session` 一处；leverage——绑定规则变更只改一处 | **Worth exploring** |
| RA-038 | `lca/infrastructure/observability/stream/trace_inspector.py`；`lca/plugins/tools/diagnostics/helpers/_helpers.py`；`lca/plugins/tools/diagnostics/diff/{context,run/diff}.py` | `_helpers._inspector_events` 用 `getattr(inspector, "_events", ())` 穿透私有属性；两个 diff adapter 依赖后门拿事件 | 给 `TraceInspector` 加只读访问器（如 `events_for(run_id)`/events property），两 adapter 改走访问器，删 `_inspector_events` | locality——4 文件；leverage——seam 恢复封装，后续重构 inspector 内部零连带 | **Worth exploring** |
| RA-039 | `lca/harness/diagnostics/doctor/facade.py`；`lca/harness/diagnostics/doctor/{privilege,trust,resource_pass}.py`；`lca/infrastructure/cli/commands/doctor/profile.py` | 9 个 pass 里 Privilege/Trust/Resource 在 facade 的 SINGLE entry point 之外——`doctor profile --ci` 自称 fail-closed 却永远跑不到 DOC-PRIV-*/DOC-TRUST-*/DOC-RES-* | facade 用已解析 contracts 顺手跑 PrivilegeDoctor + TrustDoctor（加 include 开关）；ResourceDoctor 要么找 registry 接入点，要么 docstring 明确标注"CI-only/未接入" | locality——facade + 2~3 个 pass；leverage——"单入口"承诺变真，3 个已有单测的 pass 第一次被生产路径执行 | **Worth exploring**（resource 偏 Speculative） |
| RA-040 | `lca/infrastructure/sandbox/local/adapter.py`（`_rewrite_command`/`_exec_shell`）；`lca/infrastructure/session/projections/display_paths.py` | `_rewrite_command` 的 `command.replace(mount, root)` 全文替换把 host 会话根写进命令文本；输出中的 host 路径以自由文本进入 Observation，而 display 投影永不改写自由文本（有测试 pin 住豁免）→ 模型看到宿主绝对路径 | `_exec_shell` 出口对 stdout/stderr 逆向投影（`work` 前缀换回 guest 视角），与 display_paths 共用 root 常量；或收窄 rewrite 只重写词法路径 token | locality——display/process split 的"process 侧不泄漏 host 真相"收敛到 adapter 出口一处；leverage——投影规则与重写规则用同一常量 | **Worth exploring** |
| RA-041 | `lca/contracts/protocols/graph/strategy.py`；`lca/framework/graph/interpreter.py`；`lca/framework/graph/strategies/subgraph_run.py` | kernel 经 `node_config["_port_registry"]` 字符串后门把外层 PortRegistry 塞给 subgraph strategy，注释自承 "no Protocol change required"；StrategyContext 明明是 frozen + extra=forbid 的正式 seam | StrategyContext 加正式可选字段（如 `outer_ports`），interpreter 填它，subgraph_run 读它 | locality——seam 回到正式契约；leverage——任何 strategy/测试不再能被同名 key 静默踩踏 | **Speculative**（今天能工作，风险假设性） |

### Top recommendation

先做 **RA-033**（envelope metadata 类型化 seam）。理由：它是本轮唯一同时命中"泄漏的 seam + 测试与 bug 的 locality 错位"两个维度的候选——`_owed_rows` 的 fail-loud raise 证明契约是 load-bearing 的，而守护它的测试恰恰是契约漂移时测不出来的那个；且活对象塞进号称 JSON 友好的 metadata 是真实的架构腐坏，不只是文档问题。RA-034（journal 叙事）紧随其后——它的 option (a) 是纯文档修正、(b) 才是 deepening，optimize 轮需先拍板方向。RA-035 是低风险的开胃菜（单模块 + 一个测试），可与 RA-033 同轮顺手做。

### Self-grilling（逐候选）

**RA-033** — Constraints：`mint_envelope` 的非空校验语义不变；`_owed_rows` 的 fail-loud 行为不变（只是读取方式变）；`command_envelope_to_dict` 的输出形状不变。Dependencies：上游 4 个铸造点；下游 `effect/execute.py::_owed_rows`、journal 写入路径、测试。Shape：`ToolsEnvelopeMeta` frozen dataclass 放在 `envelope.py` 旁（或 `contracts/protocols/act/command/envelope.py` 内），字段 `tool_call_id: str` / `tool_call_index: int` / `effect_class: str` / `operation: str`；`mint_envelope` 接受它或从它派生 metadata；`_owed_rows` 经访问器读。Test survival：`test_unattributable_result_fails_loud` 必须保持红→绿语义（删构造即红）；`test_envelope_n_to_n.py` 四测试全绿。Deletion test verdict：删掉 `tool_call_id` 构造→该测试变红（concentrates，契约真实）；删掉测试的 `_mint` 副本→全绿（副本多余）。

**RA-034** — Constraints：`observation_content` 的投影语义本身不变；`derive_messages` 重放路径不变。Dependencies：3 个调用者（dispatch_tool_call、effect.execute、tool_journal）+ `RunSessionWriter`。Shape：option (a) 纯文档修正；option (b) `observation_content(..., view="display"|"process")` 或拆双函数。Test survival：`test_observation_surface_display_paths.py`；若选 (b) 需新测试 pin 住 journal 绝对路径。Deletion test verdict：删掉"journal 保留绝对路径"叙事零复杂度变化——证明是叙事债务。

**RA-035** — Constraints：`explain_failure(run_id, diff, control_traces)` 的纯函数签名与返回语义不变。Dependencies：唯一生产调用者 `commands/observation/run_explain.py`；测试 `test_explainer_algorithm.py`。Shape：删表 + dataclass + docstring 段落；测试改断言 3 个真实分支。Test survival：改写后的测试。Deletion test verdict：删后除该测试外全绿——死抽象。

**RA-036** — Constraints：4 个公式的输出 key 必须逐字不变（case 表证明）。Dependencies：4 个铸造点 + 依赖 key 去重的 retry/cache 逻辑。Shape：`idempotency_key_for` helper。Test survival：现有 envelope 测试。Deletion test verdict：诚实结论——内联回原公式全绿，今天不是 load-bearing，价值纯属约定。

**RA-037** — Constraints：正常路径（create_session→run_in_session）行为不变。Dependencies：capability registry 的 create_session 转发、run_terminal、`_session_root("")` 回落。Shape：`run_in_session` 开头显式查 `_sessions`，缺席抛 `KeyError`/明确异常。Test survival：现有 WSOT-08/09 + 新测试（未知 sid→抛错）。Deletion test verdict：删回落分支→复杂度集中到调用方，消除静默错目录。

**RA-038** — Constraints：`TraceInspector` 的事件语义不变。Dependencies：`diff/context.py`、`run/diff.py`、测试。Shape：只读 `events` property 或 `events_for(run_id)`。Test survival：`test_explain_failure_ledger.py`。Deletion test verdict：加访问器后删 helper 只需改调用处——seam 真实。

**RA-039** — Constraints：现有 4 个 pass 的默认行为不变（include 开关控制新增）。Dependencies：facade 的 `_optional_resolve_contracts`、profile 命令。Shape：facade 内对已解析 contracts 跑 Privilege/Trust（resource 待 registry 来源决策）。Test survival：各 pass 现有单测 + facade 测试。Deletion test verdict：测的是承诺——"删掉 SINGLE-entry 宣称"也是诚实解。

**RA-040** — Constraints：`display_paths` 的自由文本豁免保留；`_rewrite_command` 的重写语义不变。Dependencies：`_exec_shell` 的 stdout/stderr 出口、observation 投影链。Shape：出口逆向投影（`work` 前缀→guest 视角）或收窄 rewrite 为词法 token。Test survival：现有 display 豁免测试 + 新测试。Deletion test verdict：豁免是刻意的（删它会误伤文件内容），缺口在 rewrite 引入新 host 路径一侧。

**RA-041** — Constraints：subgraph 的 kernel-seeded ports 行为不变。Dependencies：interpreter 的播种处、所有 strategy 实现。Shape：`StrategyContext.outer_ports: Mapping | None`。Test survival：`tests/unit/framework/graph/`。Deletion test verdict：删注入→集成挂（机制 load-bearing），但字符串后门是 smell。

### 与 ADR 的冲突检查

- RA-034 的 option (b) 若实施，需同步修正 ADR-0121（journal 绝对路径相关表述）——已在 acceptanceCriteria 要求。
- RA-039 的 facade docstring 若改"CI-only/未接入"，与 ADR-0199 §5.3 的 SINGLE entry point 宣称冲突——已在故事内要求显式决策。
- `ModelVisibleHook.before_publish`/`after_dispatch` 占位（progress.txt 已记录）：仍按 YAGNI 不动，ADR-0185 PR-3 落地或流产时再议。
- 其余候选与现行 ADR 无冲突。

### 丢弃（有证据）

- `assistant_scope.py` 的 ContextVar 换皮：命名与意图封装，删掉调用方易错——只搬移复杂度，不立案。
- `display_paths.py` 删模块：复杂度不增（还少一次跨层 import），但"未来 plane 加 root 常量"是保留理由——浅但无害，不立案；其跨层 import 问题已并入 RA-034 的观察。
- `PipelineSafeExecutor.execute` 的 dummy `mint_envelope()` 调用（骗 AST gate）：在 RA-013 邻域，按禁区未立案，判给 body/executor lane。
- `_model_visible_identity` 的 cursor 回退语义与 `step_id_from_cursor` 不一致：RA-025 未竟之地，只记录不立案。
- `warn_deprecated_envelope_constructor` 零调用者：死代码，机械清理未立案。
- `debug_trace_provider._render_event` 零调用：死代码，机械清理未立案。
- 10-07 P2（`run(None)` / `NativeToolCall.arguments` str）：仍 defer 给 iter-quality。
