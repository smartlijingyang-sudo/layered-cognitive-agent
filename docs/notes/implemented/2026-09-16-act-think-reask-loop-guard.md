# act→think re-ask loop class — typed-port contract + hard cap + cycle exposure

- 类:contract + runbook
- 触发日期:2026-09-16
- 触发命令:`./scripts/lca-ops runs create --user-text "..."`(任何触发 tool 调用的 prompt)
- 触发 profile:profiles/web-standard.yaml
- 影响:tool-call 路径在 typed-port projection 落地后会进入 act→think re-ask 边;`decision` 是 typed port;空 NodeOutput 不清空 registry 时,上轮 stale Decision 会被 think.route.decide 当成本轮 shortcut 命中 → 死循环(~880 空 think turn 不再调 LLM)。

## 现象

| 观察 | 数据 |
|---|---|
| `think.shortcut` / `think.route.decide` / `think.gate` 重复次数 | ~3800 |
| `act.main` / `effect.execute` 重复次数 | ~879 |
| `llm.call.end` 实际次数 | 1 |
| 一次因果链中 emit 事件总数 | 49k+ |
| HTTP `/health` | TCP 通,响应永不返回 |
| MainThread 卡在栈 | `Session.append._snapshot_data` 的同步 `json.loads`(曾以为是这个);实测更深:spine hook 的 `causality_payload = json.dumps(...)` 也是同步,但 payload size 实际只 100 字节级。**真正饿死事件循环的是 ~880 次 emit 累计的 MainThread 同步开销,不是单次 payload 大小** |

## 根因(第一性原理)

`PortRegistry.merge_output` 是 last-write-wins(ADR-0217 §3.3.3 iron rule 5),但**只在 key 出现在 dict 里时**才写。`NodeOutput(port_values={})` 是合法输出(代表"本轮 nothing to say"),却被语义当成"什么都没发生"。`think.shortcut` 声明 `outputs=[decision]` 但当 SupportsShortcut 未 wire 时返回空 port_values → 上轮 stale Decision 留在 registry → `think.route.decide` 读到 → 当成 shortcut 命中 → emit 同一个 `use_tool` → act.search → 同样结果 → `should_terminate=False` → re-ask think → 无限空转。

`origin/main` 上 LLM 调用在 `llm.invoke` 抛 TypeError 失败(`d10ff6cea` 修了 adapter typed-port projection 才让 LLM 调通),所以这条 re-ask 路径**从未被走到**,死循环从未暴露。`a83b88458` 引入了 kernel-wide typed-port 投影,registry 在外层 plan 和 subgraph 之间共享;`e9b92d81e` 改了 act→think 边序让 re-ask 成为稳定路径。这三个 commit 拼起来才让 bug 出现。

## 修复(本 note 实现)

| Fix | 文件 | 性质 |
|---|---|---|
| 1. PlanInterpreter 清空 declared outputs | `lca/framework/graph/interpreter.py` | 契约正确:声明 output 必须每轮产出,空 update → None |
| 2. LoopObligationExceededError + 运行时强制 | `lca/contracts/protocols/graph/errors.py`、`lca/framework/graph/traversal.py`、`lca/framework/graph/interpreter.py` | 防御:edge loop.maxIterations 真正生效,LangGraph `recursion_limit` 类比 |
| 3. act→think re-ask 边挂 `loop.maxIterations=8` | `bundles/outer/phase_main.yaml` | 配置:不让 re-ask 永远 unbound |
| 4. Boot fail-loud 检查 | `lca_kernel/boot/plan_validation/checks/use_tool_reask_edge.py` | 编译时保证 3 不能被 silently 删除 |
| 5. cycle detector 带 consecutive_count | `lca/plugins/observability/spine/derivers/anomaly.py` | 暴露:单条 anomaly 记录就能定位"哪条 EP 在循环 + 循环密度",不再需要 cross-ref journal |

## 与业界对照

| 系统 | 状态隔离 | 循环硬上限 | 重复检测 | 暴露 |
|---|---|---|---|---|
| LangGraph | reducer `LastValue` — 空 update 显式清除 | `recursion_limit` 强 raise | retry policy | LangSmith trace |
| OpenAI Agents SDK | sub-agent `input_filter` 投影 | `max_turns` | `tool_use_behavior="stop_on_first_tool"` | Runner trace |
| LCA (本 note 落地后) | merge_output + declared-output clear | edge `loop.maxIterations` + LoopObligationExceededError | RepeatToolCallGate(warn) | anomaly `evidence.consecutive_count` |

LCA 的不同:`PortRegistry` 是 typed-port 显式 registry,而不是 reducer 列表;每条 edge 携带结构化 `EdgeLoopObligation` 而不是全局 max_turns 配置。这让"哪个边循环、循环密度多少"在 anomaly evidence 里能精确回答。

## 验证矩阵

修复后必须达成:

- [x] PlanInterpreter 在 declared outputs 缺失时显式 merge None(测试 `test_declared_output_clears_on_empty_node_output`)
- [x] EdgeLoopObligation 在 select_edge 跳过已超额边(`test_select_edge_skips_bounded_edge_when_quota_hit`)
- [x] 没有 fallback 时抛 LoopObligationExceededError 含 `source/target/max_iterations/taken`(`test_edge_loop_obligation_exceeded_raises`)
- [x] Boot 校验 unbounded re-ask edge 失败 loud(`test_unbounded_reask_fails_loud`)
- [x] cycle detector evidence 含 `consecutive_count`,不解析 payload 业务字段(`test_cycle_detector_trips_on_second_consecutive_repeat`)

## 已知遗留

- `_snapshot_data` 同步 JSON 路径仍是 emit 路径上的固定开销。本 note 不修它(超出本次根因范围)。`copy.deepcopy + size cap` 改动保留作为降本,不再依赖它解决循环 bug。
- RepeatToolCallGate 当前只 warn 不 block。Profile 可调;是否升级到 block 是单独决策。

## 引用证据

- `traces/locks/2026-09-16-session-append-stall/`(py-spy dump + spine journal)
- `traces/runs/run_9bd8f8f33e52/run_9bd8f8f33e52.spine.jsonl`(1.5GB)
- `traces/runs/run_c9f1af7def15/run_c9f1af7def15.spine.jsonl`(274MB, 复现现场)
- ADR-0217 §3.3.3 iron rule 5(last-write-wins)
- ADR-0241 typed-port projection(把 registry 共享暴露到 act/think 边界)
- commit `a83b88458 fix(runtime_plane)`、`d10ff6cea fix(runtime)`、`e9b92d81e fix(bundle)`
- commit `lca/framework/graph/interpreter.py`(Fix 1)、`lca/contracts/protocols/graph/errors.py`(`LoopObligationExceededError`)、`lca/plugins/observability/spine/derivers/anomaly.py`(Fix 5)
- `bundles/outer/phase_main.yaml`(`loop.maxIterations: 8` 在 act→think re-ask 边)
