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
