# Agent Note: concept.decision.classify — parse 节点合并,消解 fan-out 隐式假设

Status: implemented
ADR: docs/adr/0221-concept-decision-classify-parse-merge.md
Applied: 同 PR 落地,本 commit 即应用;具体 run_id 是 fan-out 修复后的首次回归测试触发的后续未覆盖 issue(详见 Testing § Known gap)。

## Problem

`run_dfa3f8615ea6`(2026-09-12, `user_text="列出当前目录文件"`)在 `qwen3.7-plus` 首次让 LCA 走通 think → act 链路后,在 `act.validate` 抛 `TypeError("act.validate: 'decision' port must be a Decision instance, got NoneType")`。`lca-ops debug-run run_dfa3f8615ea6` 第 [5/8] 步指出 `decision.compose.action` 节点缺失;`journal trace` 确认 `decision.parse.intent` 与 `decision.compose.action` 两个节点从未被调度。

`bundles/concept/decision_classify.yaml` 当前拓扑是 3 节点(`decision.parse.tool_calls` / `decision.parse.intent` / `decision.compose.action`)配 2 条边:

```yaml
edges:
  - source: decision.parse.tool_calls
    target: decision.compose.action
  - source: decision.parse.intent
    target: decision.compose.action
```

两条边都指向 `compose.action`,但**没有任何边把 entry 节点(`parse.tool_calls`)引到 `parse.intent`**。LCA v2 graph driver(`lca/framework/graph/interpreter.py::PlanInterpreter.run`)是单 cursor while 循环,不支持 fan-out。`PlanTraversal.select_edge` 只选第一条匹配 source 的出边,`advance` 单向前进。结果:`parse.tool_calls` 执行后直接 advance 到 `compose.action`,`parse.intent` 永远没机会跑。

`compose.action` 自己没运行是更深的现象 —— 在单 cursor 下,两个独立 parse 节点不可能都按预期执行。trace `traces/runs/run_dfa3f8615ea6/run_dfa3f8615ea6.spine.jsonl` 显示只有 `decision.parse.tool_calls` 一个节点事件,后续 `decision.parse.intent` / `decision.compose.action` 全部缺失。close-out 投影(SSOT `lca/cognition/close_out.py::CLOSE_OUT_FIELDS`)只扫描 5 个字段名,因 `compose.action` 没运行,`decision` 端口从未被写入,close-out 自然转发 `None`,沿 `think.main → act.main → act.validate` 链路冒泡成 TypeError。

ADR-0220 §3.3 把这张图列为"3 节点 typed parse/compose pipeline"。两个 parse 节点的实现读同一 `LLMResponse`,逻辑相互独立 —— 分裂的动机是**类型边界清晰**(typed `ToolCall` + `DelegationSpec` + `str` 三路入参分别计算后合成 `Decision`),不是数据依赖。但分裂需要 fan-out 调度器,而 v2 driver 只有单 cursor。这是闭集设计假设与实现驱动能力的脱节。

## Decision

现状(本 commit 落地后):

- `concept.decision.classify` 是 2 节点 / 1 edge 图。`decision.parse.response` 单 pass 对 `LLMResponse` 解析,产出 `tool_calls` / `delegations` / `intent` 三端口;`decision.compose.action` 接受三路入参合成 `Decision`(优先级 DELEGATE > USE_TOOL > RESPOND)。
- `lca/plugins/concept/decision_classify/parse_tool_calls.py` 文件名保留(避免大规模 rename),内部为 `DecisionParseResponseExecutor`(`semantic_name="decision.parse.response"`,`provides=("concept::decision.parse.response",)`,`EvidenceContract.descriptors="phase_concept_decision_classify_decision_parse_response.{checked,served}"`)。
- `parse_intent.py` 模块物理删除,无 compat shim(AGENTS.md §4 "无 delete-when 的兼容分支 = 红灯")。
- `bundles/base.yaml` manifest 行收敛到 2 行(`decision_parse_response` + `decision_compose_action`)。
- `bundles/think.yaml` + `bundles/agent/reasoning_turn.yaml` 的 `sub_spec_ref.entry_node` 同步为 `decision.parse.response`。
- `lca/contracts/protocols/declarative/declarative_1/ports.py` D5 mapping 把 `decision.parse.tool_calls` / `decision.parse.intent` 字面行收敛为 `decision.parse.response`。

## Topology

改前(3 节点 / 2 edge,fail-loud 隐式 fan-out):
```yaml
nodes:
  - decision.parse.tool_calls  → outputs: [tool_calls, delegations]
  - decision.parse.intent      → outputs: [intent]
  - decision.compose.action    → outputs: [decision]
edges:
  - parse.tool_calls → compose.action
  - parse.intent     → compose.action   # parse.intent 没有入边!
```

改后(2 节点 / 1 edge,driver 友好):
```yaml
nodes:
  - decision.parse.response    → outputs: [tool_calls, delegations, intent]
  - decision.compose.action    → outputs: [decision]
edges:
  - parse.response → compose.action
```

## Alternatives considered

### Why not A(改 yaml 边为串行 `parse.tool_calls → parse.intent → compose.action`)?

把 fan-out 假设隐式转成"串行必须",但下次有人在 graph driver 加新并行入口会重复撞坑;不消解 fan-out 假设。`intent` 依赖 `tool_calls`(因为 leak recovery 修改了 `leftover` 文本,需要 `intent` 在 leak recovery 之后提取),但串行写法隐式耦合了"两个 parse 必须按这个顺序执行" —— 实际意图是它们互不依赖只是 leak recovery 是同一道预处理。串行写法把单步泄漏 recovery 强加到意图层。

### Why not B(`PlanInterpreter` 加 fan-out / 并行分支调度)?

改 v2 graph driver 违反 C1 闭集(认知闭集六个 phase 不能无 ADR 增加步骤或核心事件词表)+ C6 最小化 + ADR-0194 §0 单一 cursor 决策。改动半径远超本 bug;`PlanTraversal` 数据模型(`current_id: str`)、`advance` 语义、`select_edge` 全部要重新设计 —— 这是独立 ADR,本 PR 不应承担。

### Why not C(三节点合并为单 `decision.compose`)?

违反 G1 一张图 = 一个职责 + AGENTS.md §1.5 §4 模块一句话能说清"干嘛的";tool call 解析、delegation 过滤、intent 提取、Decision 合成责任糅在一个 node 里。`compose` 节点的输入是 typed `tuple[ToolCall]` + `tuple[DelegationSpec]` + `str` 三路入参,正是 split 设计的**类型边界清晰**价值;把 parse + compose 合一会让 Decision 合成的"分支"逻辑看不到清晰的入参来源。

### Why not E(保留 fan-out,让 `decision.parse.intent` 成为可选 skip 节点)?

把单 cursor 的 `select_edge` 行为变得依赖副作用 skip 状态,违反 ADR-0095 plan interpreter 局部性 + ADR-0194 §0 单一 cursor。`skip` 节点让 plan 拓扑不可静态分析,observability 折叠逻辑也变复杂(`PlanTraversal.select_edge` line 84 的 when DSL 本来只跑 bool,引入 skip 会让闭集膨胀)。

## Testing

(本 commit 落地的测试 + 验证)

- `tests/concept/decision_classify/test_decision_parse_response.py` 7/7 通过:happy path(tools + intent)/ 仅 tool_calls / 仅 intent / 仅 delegate 过滤 / leak recovery 顺序(intent 不含 leaked JSON 重复提取)/ response 端口类型校验 / executor metadata
- `tests/integration/test_decision_classify_e2e.py` 6/6 通过:拓扑契约(2 节点 / 1 edge)+ 完整图执行产出 USE_TOOL / DELEGATE / RESPOND / 空响应 fallback 四态 + leak recovery 通过图执行不污染 intent
- `ruff check` + `ruff format`:0 violation
- `plugin shape audit`:baseline 与 current 仅差一个新增 `decision_parse_response` 行,与既有的 `import 失败 ModuleNotFoundError` 模式一致(venv 外 audit 限制;不在本 PR scope)
- Kernel 重启 + regression run `run_fdb14528eeb3`:`decision.parse.response` 节点事件出现且 `outcome=success`(详见 Known gap)

## Consequences

(已落地 trade-off)

- 合并节点让单步 NodeEnter/NodeExit 事件少一次,observability 体积变小;无 consumer 匹配具体 `decision_parse_intent` 字符串,无回归
- `parse_tool_calls.py` 文件名保留 + `semantic_name` 改名可能让搜索结果混淆;commit message 显式说明 semantic_name 收敛到 `decision.parse.response`
- ADR-0220 仍是 Proposed,0221 与 0220 并行期间若有人基于 0220 §3.3 写新图,会再次撞坑;0220 升 Accepted 时 0221 是闸门之一
- 不再支持 fan-out 假设的 graph driver;PlanInterpreter 仍单 cursor,fan-out 必须由 caller 用合并节点表达

## Known gap

**本 commit 修完 fan-out 假设后,`run_fdb14528eeb3` 触发了下一个独立 contract bug**:

`Decision.created_at: datetime = field(default_factory=utc_now)`(`lca/contracts/models/core/execution/decision.py:87`)与 `lca/session/append.py::_to_jsonable` 不识别 `datetime` 类型冲突。spine emit `phase_graph.node.end` 时:`_snapshot_data → _to_jsonable(asdict(decision))` 递归到 `created_at` 抛 `TypeError("session event data 包含不可无损 JSON 序列化的值: datetime")`。emit 失败仅 WARNING 级(`lca/harness/declarative/compile/instrument/wrap.py:229` `wrap_instrument: spine emit failed`),不 fail-loud → `decision.compose.action` 的 `node.end` 事件落盘失败 → close-out 投影拿不到 `decision` 端口值 → `act.validate` 仍报 `decision=None` TypeError。

这与 fan-out 修复独立 —— 在 fan-out bug 让 `compose.action` 永远不运行,所以这条 datetime 序列化路径从未被走过。一旦 fan-out 修了,这一路径立即暴露。

修复路径不在本 PR scope(触跨边界契约:`Decision` boundary DTO + spine `_to_jsonable` converter)。下一 PR + ADR 处理:① `_to_jsonable` 加 `datetime → isoformat` 兜底(影响面小)② 同时加 `Decision` 序列化单测 ③ 可能 ADR-0222 文档化 boundary 序列化契约。

`run_fdb14528eeb3` 当前的 `act.validate: 'decision' port must be a Decision instance, got NoneType` 即为这条已知 gap 的症状,**不是 fan-out 修复的回归**。

## Related

- docs/adr/0221-concept-decision-classify-parse-merge.md (Proposed,本文档 pin 的 ADR)
- docs/adr/0220-three-tier-graph-and-boundary-typing.md (Proposed; §3.3 / §11 P6 / Appendix A 由 0221 在升 Accepted 时一并 amend)
- docs/notes/implemented/seam/2026-09-11-act-subgraph-seam-cutover.md (邻近主题)
- docs/notes/implemented/seam/2026-09-11-close-out-ssot.md (邻近主题)
- docs/notes/implemented/seam/2026-09-11-kernel-native-phase-runner.md (kernel-native runner 不变)
- bundles/concept/decision_classify.yaml
- bundles/concept/decision_enforce.yaml (下游消费者,inputs 仍走 decision port,无影响)
- bundles/think.yaml (think.classify sub_spec_ref entry_node 同步)
- bundles/agent/reasoning_turn.yaml (reason.classify.response sub_spec_ref entry_node 同步)
- lca/framework/graph/interpreter.py::PlanInterpreter.run (单 cursor 不变)
- lca/framework/graph/traversal.py::select_edge (不 fan-out 不变)
- lca/cognition/close_out.py::CLOSE_OUT_FIELDS (字段名 SSOT 不变)
- lca/plugins/concept/decision_classify/{parse_tool_calls,compose_action}.py
- lca/contracts/protocols/declarative/declarative_1/ports.py (D5 mapping 同步)
- traces/runs/run_dfa3f8615ea6/ (regression run,fan-out bug触发)
- traces/runs/run_fdb14528eeb3/ (Known gap 的 regression run,datetime 序列化 bug 触发)