# ADR-0221: concept.decision.classify — parse 节点合并,消解 fan-out 隐式假设

> **状态:** **Proposed — 2026-09-12**
>
> **一句话:** 把 ADR-0220 §3.3 设计的 3 节点图(`decision.parse.tool_calls` / `decision.parse.intent` / `decision.compose.action`)合并为 2 节点图(`decision.parse.response` / `decision.compose.action`),在单节点内对同一 `LLMResponse` 同步输出 `tool_calls` / `delegations` / `intent` 三端口,消解 graph driver 不支持 fan-out 的隐式假设。
>
> **触发:** `run_dfa3f8615ea6`(`user_text="列出当前目录文件"`,2026-09-12)在 `qwen3.7-plus` 首次让 LCA 走通 think → act 链路后,在 `act.validate` 抛 `TypeError("act.validate: 'decision' port must be a Decision instance, got NoneType")`。`lca-ops debug-run run_dfa3f8615ea6` 第 [5/8] 步指出 `decision.compose.action` 节点缺失;`lca-ops journal trace` 确认 `decision.parse.intent` 与 `decision.compose.action` 两个节点从未被调度,`decision` 端口在 subgraph 出口前未写入,close-out 投影(SSOT `CLOSE_OUT_FIELDS`)返回 `None`,沿 `think.main → act.main → act.validate` 链路冒泡成 TypeError。
>
> **Agent Note** (实施时): `docs/notes/implemented/seam/2026-09-12-concept-decision-classify-parse-merge.md`(同 PR 跃迁自 proposed/;pin 具体 run_id / commit / 验证命令)。
>
> **Review:** 待评审。
>
> **Accepted 闸门:**
>
> 1. `concept.decision.classify` 图节点数从 3 → 2;`decision.parse.intent` 节点删除,`decision.parse.tool_calls` 节点名收敛为 `decision.parse.response`
> 2. `lca/plugins/concept/decision_classify/parse_intent.py` 整个模块删除;`@plugin(id=...)` / `provides=` / `EvidenceContract.descriptors` 字符串唯一收敛到 `decision.parse.response`
> 3. `bundles/base.yaml` 该 manifest 块由 3 行收敛为 2 行;`bundles/concept/decision_classify.yaml` 由 3 nodes / 2 edges 收敛为 2 nodes / 1 edge
> 4. E2E:`./scripts/lca-ops runs create --user-text "列出当前目录文件"` 重跑,`debug-run` 报告 `broken_hop=None`;原 regression run `run_dfa3f8615ea6` 在 fix 后 path 上 `act.validate` 不再被触发
> 5. 新增 leak recovery + intent 提取顺序的单测(`tests/concept/decision_classify/test_decision_parse_response.py`)与 e2e 图测试(`tests/integration/test_decision_classify_e2e.py`)
> 6. Agent Note 在同 PR 内从 `proposed/seam/` 跃迁到 `implemented/seam/`
> 7. ADR-0220 §3.3 / §11 P6 / Appendix A 在新 ADR 升 Accepted 时由后续 meta-ADR 同步 amend;本 PR 不修改 ADR-0220(README 规则"老 ADR 一律不动")

**编号:** 0221

**关系:**
- **Refines**: ADR-0220 §3.3(三层图 concept.decision.classify 行)/ §11 P6 row / Appendix A topology · ADR-0219 §10.11.5(close-out 字段 SSOT 仍成立 —— 不变)
- **Builds on**: ADR-0217(Bundle Graph Schema v2 仍写更多图)/ ADR-0218(subgraph driver / sub_spec_ref 不变)/ ADR-0194(认知 Loop 架构收敛,plan execution driver 仍单 cursor)
- **Supersedes**: 无
- **Extends**: 无
- **Reject**:
  - 「改 yaml 边为串行 `parse.tool_calls → parse.intent → compose.action`」(选项 A)—— 把 fan-out 假设隐式转成"串行必须",但下次有人在图里加新并行入口会重复撞坑;不消解 fan-out 隐式假设
  - 「`PlanInterpreter` 加 fan-out / 并行分支调度」(选项 B)—— 改 v2 graph driver 违反 C1 闭集(认知闭集六个 phase 不能无 ADR 增加步骤或核心事件词表)+ C6 最小化 + ADR-0194 单一 cursor 决策;改动半径远超本 bug
  - 「三节点合并为单 `decision.compose`」(选项 C)—— 违反 G1 一张图 = 一个职责 + 模块一句话能说清"干嘛的";tool call 解析、delegation 过滤、intent 提取、Decision 合成责任糅在一个 node 里
  - 「保留 fan-out 让 `decision.parse.intent` 成为可选 skip 节点」(选项 E)—— 把单 cursor 的 `select_edge` 行为变得依赖副作用 skip 状态,违反 plan interpreter 局部性(ADR-0095)

## §0 触发:同一根因的两种形态

ADR-0220 §3.3 把"3 节点 typed parse/compose pipeline"作为概念图的范式(行 233)。其设计动机是**类型边界清晰**(typed `ToolCall` + `DelegationSpec` + `str` 三路入参分别计算后合成 `Decision`),而不是数据依赖 —— 两个 parse 节点读同一 `LLMResponse`,逻辑相互独立。

但 LCA v2 graph driver(`lca/framework/graph/interpreter.py::PlanInterpreter.run`,line 111–207;`PlanTraversal.advance`,line 67–75)是**单 cursor while 循环**:`select_edge` 只选第一条匹配 source 的出边,`advance` 单向前进,不支持 fan-out。`bundles/concept/decision_classify.yaml` 当前 edges 写法:

```yaml
edges:
  - source: decision.parse.tool_calls
    target: decision.compose.action
  - source: decision.parse.intent
    target: decision.compose.action
```

两条边都指向 `compose.action`,但**没有任何边把 entry 节点(`parse.tool_calls`)引到 `parse.intent`**。结果:

1. `parse.tool_calls` 执行后,`select_edge` 选第一条匹配(`parse.tool_calls → compose.action`),`advance` 直接到 `compose.action`
2. `parse.intent` **从未被访问**(没有入边从 entry 路径可触达)
3. `compose.action` 收到 `tool_calls` 但 `intent` 端口 `None`,仍可合成一个 `Decision`(compose_action.py:90–135 的 fallback:`(intent or "")` = "")—— 但 trace 显示 `compose.action` 也未运行,意味着 selector 在 `parse.tool_calls` 后 advance 到 `compose.action` 本身被某种 close-out 短路

第二种形态的根因更深:在 v2 graph driver 单 cursor 下,两个独立 parse 节点不可能都"按预期"执行。要么 A(改串行,牺牲并行性),要么 D(合并,消解假设)。D 选是因为:

- A 留下"两个 parse 互不依赖,但 graph driver 必须串行"的不一致假设 —— 任何后续加并行入口都会再次撞坑
- D 让"两个 parse 互不依赖"在**节点拓扑层显式**(节点内一个函数顺序解析),不再依赖 driver 调度能力

符合 AGENTS.md §1.5 §3"依赖单向,不通过兄弟绕公开 API" + "模块一句话能说清'干嘛的'"。

## §1 影响面与变更清单

### 1.1 删除

- `lca/plugins/concept/decision_classify/parse_intent.py`(整文件,AGENTS.md §5 一个 plugin 一个 .py)

### 1.2 修改

| 文件 | 改前 | 改后 |
|---|---|---|
| `lca/plugins/concept/decision_classify/parse_tool_calls.py`(文件名保留,内部 rename) | `DecisionParseToolCallsExecutor`;`semantic_name="decision.parse.tool_calls"`;`declared_outputs=("tool_calls","delegations")`;`provides=("concept::decision.parse.tool_calls",)`;descriptors `phase_concept_decision_classify_decision_parse_tool_calls.checked/.served` | `DecisionParseResponseExecutor`;`semantic_name="decision.parse.response"`;`declared_outputs=("tool_calls","delegations","intent")`;`provides=("concept::decision.parse.response",)`;descriptors `phase_concept_decision_classify_decision_parse_response.checked/.served` |
| `bundles/base.yaml` line 208–219 | 3 行 manifest(`decision_parse_tool_calls` / `decision_parse_intent` / `decision_compose_action`) | 2 行 manifest(`decision_parse_response` / `decision_compose_action`) |
| `bundles/concept/decision_classify.yaml` | 3 nodes + 2 edges(见 §0) | 2 nodes + 1 edge |
| `bundles/think.yaml` line 66 | `entry_node: decision.parse.tool_calls` | `entry_node: decision.parse.response` |
| `bundles/agent/reasoning_turn.yaml` line 131 | `entry_node: decision.parse.tool_calls` | `entry_node: decision.parse.response` |
| `lca/contracts/protocols/declarative/declarative_1/ports.py` line 18–21 D5 mapping | 含 `decision.parse.intent` 字面行 | 删除或合并 |

### 1.3 新增

- `tests/concept/decision_classify/test_decision_parse_response.py` — 单元测试
- `tests/integration/test_decision_classify_e2e.py` — 图执行 e2e 测试
- `docs/notes/implemented/seam/2026-09-12-concept-decision-classify-parse-merge.md` — 同 PR 跃迁

### 1.4 不修改

- `docs/adr/0220-three-tier-graph-and-boundary-typing.md`(README 规则"老 ADR 一律不动";升 Accepted 时由 meta-ADR 同步 amend §3.3 行)
- `lca/cognition/close_out.py::CLOSE_OUT_FIELDS`(close-out 字段 SSOT 不变,`decision` 仍是 boundary 输出)
- `lca/framework/graph/interpreter.py`(v2 driver 不动)

## §2 合并节点 `node_execute` 实现契约

```python
@dataclass(frozen=True, slots=True)
class DecisionParseResponseExecutor:
    semantic_name: str = "decision.parse.response"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("response",)
    declared_outputs: tuple[PortName, ...] = ("tool_calls", "delegations", "intent")

    async def node_execute(self, context, input):
        response = input.port_values.get("response")
        if not isinstance(response, LLMResponse):
            raise TypeError(...)
        # 顺序: leak recovery 必须先于 intent 提取,否则 leaked JSON 会被
        # 误读进 intent 文本。recover_leaked_tool_calls 返回新 tuple,
        # 不修改 response.text。
        leftover = (response.text or "").strip()
        native_calls = list(response.tool_calls or ())
        if not native_calls and leftover:
            leftover, recovered = recover_leaked_tool_calls(leftover)
            native_calls = recovered
        tool_calls, delegations = _project(native_calls)
        intent = leftover
        return NodeOutput(port_values={
            "tool_calls": tool_calls,
            "delegations": delegations,
            "intent": intent,
        })
```

`_project(native_calls)` 内部把 `delegate` 工具名过滤到 `delegations`,其余构造成 `ToolCall`。

## §3 验证矩阵(AGENTS.md §6)

| 变更类型 | 最低验证 | 必须追加 |
|---|---|---|
| Plugin 闭集变更(C1) | `ruff check` + `ruff format` + `pytest tests/concept/decision_classify/ tests/integration/test_decision_classify_e2e.py` | E2E `lca-ops runs create --user-text "列出当前目录文件"` 重跑 + `debug-run` `broken_hop=None` |
| Plugin 公开签名 | `./scripts/lca-ops audit-plugin-shape` | plugin shape 合法,manifest 行数 3 → 2 |
| bundles yaml 边 | 重编译 `concept.decision.classify` 后 `plan.edges` 含期望 `parse.response → compose.action` | `decision.parse.intent` 字符串 0 命中 |
| Agent Note 跃迁 | `./scripts/lca-ops notes-check` | proposed → implemented 头三行格式合规 |

`real_llm` 默认不跑;E2E 走 `./scripts/lca-ops runs create` 走真 LLM 是 regression 的最后一关。

## §4 delete-when

本 ADR 升 Accepted 的同步条件(任一):

1. `concept.decision.classify` 图节点数已收敛到 2,且 `lca/plugins/concept/decision_classify/parse_intent.py` 已物理删除
2. E2E `runs create --user-text "列出当前目录文件"` 在 fix 后 path 上 `act.validate` 不再被触发,且 `decision.compose.action` 节点事件出现
3. tests/concept/decision_classify/test_decision_parse_response.py + tests/integration/test_decision_classify_e2e.py 在 CI 绿

升 Accepted 后,ADR-0220 §3.3 / §11 P6 / Appendix A 由后续 meta-ADR 同步 amend(独立 PR,本 PR 不动 0220)。

## §5 与 ADR-0220 的衔接

ADR-0220 是 **Proposed** 状态。0221 在 0220 升 Accepted 之前落地,意味着 0220 升 Accepted 时必须把 §3.3 的"3 节点"行 amend 为 0221 的"2 节点"设计 —— 这是 0220 升 Accepted 的 delete-when 之一。

本 ADR 不修改 0220 文件本身(README 规则);0220 升 Accepted 的 meta-ADR 由后续独立 PR 发起。