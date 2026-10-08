# source_verify —— 来源感知校验

“Getting the Source Right, Not Just the Fact.”（ProvenanceGuard，Multiverse Computing）

## 1. 职责

本包为工具输出建立 run-scoped `SourceRef`，将来源身份保留到模型可见的工具结果，并对最终回答中显式引用的来源做逐断言字面校验。它识别不存在的来源（`UNRESOLVABLE`）、来源不支持的字面依据（`UNSUPPORTED`）及引用错来源（`CONFLATED`）。

## 2. 不负责

- 不判断没有引用来源的普通断言，也不进行语义蕴含/NLI 检验。
- 不将 WARN 结果改写成用户答案；当前生产接入不启用 ENFORCE，也不代替人工复核或兜底链路。
- 不登记长期记忆、检索或系统提示来源；这些 `SourceKind` 仍是后续扩展。

## 3. 核心数据与行为

1. `SourceRegistry` 保存本轮证据原文；工具来源 ID 稳定为 `tool:<call_id>`。它是 run-scoped runtime capability，不属于 reducer-owned `AgentState`。
2. `source_marker` 将 `[source:tool:<call_id>]` 放在模型可见工具结果首行。
3. `SourceVerifier` 对可识别引用给出 `SUPPORTED`、`UNSUPPORTED`、`CONFLATED` 或 `UNRESOLVABLE` 裁决。
4. `VerifyPolicy` 支持 `OFF`、`WARN`、`ENFORCE`。生产默认是 `WARN`：异常引用返回 `needs_review` 并记录 warning，不阻断或修改答案。

## 4. 最终答案接入

- `convergence.policy.default` 在 `Scope.RUN` 创建一个 `SourceRegistry`，并把同一实例提供给 `ConvergenceRuntime`。`effect.execute` 显式声明 `source_registry` 依赖；runtime composition 从已编译的 provider binding 解析它，再投影到只读 `RuntimePhaseCapabilities`。
- `lca/nodes/concept/effect/execute.py::_append_tool_result_surface` 在工具结果进入模型上下文时登记 `SourceRef` 并写入来源标记；它与 `ConvergenceRuntime` 共享上述 run-scoped capability，不修改 `AgentState.extra`。
- `lca/cognition/brain/decision_gates/delivery.py::DeliverySatisfiedGate` 在最终 `RESPOND` 决策前调用 `ConvergenceRuntime.verify_final_answer`。
- `lca/cognition/convergence/runtime.py::ConvergenceRuntime.synthesize` 也会校验其合成的最终响应，覆盖交付门控生成答案的路径。
- 两处都固定使用默认 `WARN` 策略；没有登记表时仍会检查显式 `[source:…]` 标记，并把不存在的 ID 报为 `UNRESOLVABLE`。答案文本保持原样。
- 正式 plan 缺少 `source_registry` provider 时，plan-declared capability closure 会失败；无 capability 的只读 legacy harness 仅获得临时空登记表，不会写入 AgentState。

## 5. 输入与输出

输入是最终回答文本、当前 run 的 `SourceRegistry`（无登记时使用空表）和 `VerifyPolicy`。`verify_final_answer` 返回 `VerifyDecision`，其中包含 `pass` / `needs_review` / `block`、模式及逐断言裁决。生产门控目前使用 WARN，因此只产生 `pass` 或 `needs_review`。

## 6. 错误与降级语义

- 显式引用的来源 ID 不存在时，裁决为 `UNRESOLVABLE`，而不是把空注册表当作自动通过。
- 没有任何可识别引用的回答通过校验；这符合保守策略，不是全面事实核验。
- WARN 记录 `lca.source_verify` warning 并让原答案继续；ENFORCE 的 `block` 仅供独立调用方使用，待生产复核/兜底闭环建成后再接入。

## 7. 副作用

工具登记仅存在于本轮 run 状态，并在回答校验时读取；校验记录 Python logger warning，不写文件、不发网络请求、不更改答案。

## Muse 对齐

- ADR-0255 §4.4：工具证据保留来源身份（`SourceRef` 的来源、时间与原文）。
- ADR-0255 §4.7：`captured_at` 区分证据采集时间。
- ADR-0255 §4.8：点名而不存在即为指称幻觉，由 `UNRESOLVABLE` 表示。
