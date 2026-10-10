# 并行工具调用打通与运行机制稳定化实施方案

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于第一性原理打通 `act.subgraph` 并行工具调用全链路（支持 `fanout_ntom`），保持 Tool Defer 机制与上下文经济性，补全会话历史协议自愈与模型声带净化防线，最终通过自动化不变量断言与真实端到端 Run 验收。

**Architecture:** 
1. 拓扑与分发：`act_subgraph.yaml` 将 `fanout_ntom` 路由至 `pre_dispatch_envelope_check`；
2. 原子检查：`pre_dispatch_envelope_check` 升级支持 `envelopes` 批量原子 5-Gate 体检；
3. 事实落盘：`effect.execute` 遍历 batch 确保每个并发 `call_id` 均写入独立的 `surface/tool_result`；
4. 历史自愈：`_history.py` 清洗悬挂未闭环的 `tool_call_id`，保证发往 LLM 的对话轮次严格符合规范；
5. 声带净化：`decision.parse` 增加 `guard_leaked_prompt` 拦截泄露特征。

**Tech Stack:** Python 3.12, Pytest, Pydantic, YAML (PlanInterpreter), LCA Spine Ledger.

---

### Task 1: [拓扑接通] `bundles/act/act_subgraph.yaml` 闭环 `fanout_ntom` 出边

**Files:**
- Modify: `bundles/act/act_subgraph.yaml:255-263`
- Test: `tests/scenario/test_parallel_tool_subgraph_execution.py`
- Does NOT own: `lca/infrastructure/tool_defer/`（严禁动 DeferPolicy）, `bundles/think/`
- Invariants to test: INV-PARALLEL-01（`act.fanout` 产出 `fanout_ntom` 时成功流向 `pre_dispatch_envelope_check`，不触发 terminal 退出）

**Step 1: 编写失败测试**
```python
def test_act_subgraph_routes_fanout_ntom():
    ...
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/scenario/test_parallel_tool_subgraph_execution.py -v`

**Step 3: 最小实现**
在 `bundles/act/act_subgraph.yaml` 中将 `value: fanout_1to1` 改为 `value: [fanout_1to1, fanout_ntom]`，并将 `kind: eq` 改为 `kind: in`。

**Step 4: 运行测试验证通过**
Run: `pytest tests/scenario/test_parallel_tool_subgraph_execution.py -v`

**Step 5: Commit**
```bash
git add bundles/act/act_subgraph.yaml tests/scenario/test_parallel_tool_subgraph_execution.py
git commit -m "fix(act): wire fanout_ntom edge to pre_dispatch_envelope_check"
```

---

### Task 2: [原子校验] `pre_dispatch_envelope_check` 升级多 Envelopes 批量原子校验

**Files:**
- Modify: `lca/nodes/effect/pre_dispatch_envelope_check.py:77-145`
- Test: `tests/nodes/test_pre_dispatch_envelope_check.py`
- Does NOT own: `lca/contracts/protocols/act/command/envelope.py`
- Invariants to test: INV-PARALLEL-01（批量 envelopes 输入时逐个执行 5-Gate 检查，任一失败 fail-loud，全部通过输出 verdict_refs）

**Step 1: 编写失败测试**
```python
def test_pre_dispatch_envelope_check_supports_batch_envelopes():
    ...
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/nodes/test_pre_dispatch_envelope_check.py -v`

**Step 3: 最小实现**
在 `EffectPreDispatchEnvelopeCheckExecutor` 中，支持读取 `envelopes` typed-port（若存在则逐项检查），并正确传递 `envelope`（首项）与 `envelopes`（全量）。

**Step 4: 运行测试验证通过**
Run: `pytest tests/nodes/test_pre_dispatch_envelope_check.py -v`

**Step 5: Commit**
```bash
git add lca/nodes/effect/pre_dispatch_envelope_check.py tests/nodes/test_pre_dispatch_envelope_check.py
git commit -m "feat(effect): add batch envelopes atomic verification to pre_dispatch_envelope_check"
```

---

### Task 3: [事实闭环] `effect.execute` 确保并发工具调用每个 `call_id` 均有对应回执落盘

**Files:**
- Modify: `lca/nodes/concept/effect/execute.py:160-205`
- Test: `tests/nodes/test_effect_execute_batch_attribution.py`
- Does NOT own: `lca/infrastructure/sandbox/`
- Invariants to test: INV-PARALLEL-02（并发工具调用的每一个 `call_id` 在 Session 中产生独立 `surface/tool_result`，100% 对应）

**Step 1: 编写失败测试**
```python
def test_effect_execute_attributions_all_batch_call_ids():
    ...
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/nodes/test_effect_execute_batch_attribution.py -v`

**Step 3: 最小实现**
加固 `_append_tool_result_surface` 与 `_batch_rows`，确保从 batch observation 的 `extra[OBS_TOOL_RESULTS]` 逐项写入事实流，若缺少 batch rows 则为每个 declared call_id 生成对应回执。

**Step 4: 运行测试验证通过**
Run: `pytest tests/nodes/test_effect_execute_batch_attribution.py -v`

**Step 5: Commit**
```bash
git add lca/nodes/concept/effect/execute.py tests/nodes/test_effect_execute_batch_attribution.py
git commit -m "fix(effect): ensure 100% tool result attribution for parallel tool calls"
```

---

### Task 4: [协议合规] `_history.py` 悬挂 tool_calls 协议自愈与合规守护

**Files:**
- Modify: `lca/infrastructure/llm_adapter/openai_compat/history/_history.py:27-72`
- Test: `tests/infrastructure/llm_adapter/test_history_hanging_tool_calls_guard.py`
- Does NOT own: `lca/infrastructure/llm_adapter/openai_compat/chat/`
- Invariants to test: INV-HISTORY-01（当会话历史中存在未收到 tool 响应的 assistant tool_calls 时，自动合成应答或清洗，绝不向模型发送非法消息序列）

**Step 1: 编写失败测试**
```python
def test_openai_messages_with_history_sanitizes_hanging_tool_calls():
    ...
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/infrastructure/llm_adapter/test_history_hanging_tool_calls_guard.py -v`

**Step 3: 最小实现**
在 `openai_messages_with_history` 中扫描所有 `role="tool"` 的 `tool_call_id`，对于任何缺少对应 tool 响应的 assistant `tool_calls`，合成安全占位 tool 响应，保证交替合法性。

**Step 4: 运行测试验证通过**
Run: `pytest tests/infrastructure/llm_adapter/test_history_hanging_tool_calls_guard.py -v`

**Step 5: Commit**
```bash
git add lca/infrastructure/llm_adapter/openai_compat/history/_history.py tests/infrastructure/llm_adapter/test_history_hanging_tool_calls_guard.py
git commit -m "fix(history): sanitize hanging tool calls to enforce OpenAI wire protocol"
```

---

### Task 5: [声带净化] `decision/parse.py` Prompt 泄露与反刍条文净化门禁

**Files:**
- Modify: `lca/nodes/think/decision/parse.py:110-130`
- Test: `tests/nodes/test_decision_parse_prompt_leak_guard.py`
- Does NOT own: `lca/cognition/brain/prompt/`
- Invariants to test: INV-OUTPUT-01（识别并阻断 System Prompt 条文、Deferred Catalog 等内部信息流出至终端消息）

**Step 1: 编写失败测试**
```python
def test_guard_leaked_prompt_strips_system_prompt_regurgitation():
    ...
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/nodes/test_decision_parse_prompt_leak_guard.py -v`

**Step 3: 最小实现**
实现 `_guard_leaked_prompt`，识别系统规则条文（如 `## 记忆写入与写盘铁律`、`Deferred tool namespaces` 等），清洗或拦截，返回洁净响应。

**Step 4: 运行测试验证通过**
Run: `pytest tests/nodes/test_decision_parse_prompt_leak_guard.py -v`

**Step 5: Commit**
```bash
git add lca/nodes/think/decision/parse.py tests/nodes/test_decision_parse_prompt_leak_guard.py
git commit -m "feat(decision): add output hygiene guard against system prompt leakage"
```

---

### Task 6: [回归验收] 服务重启与真实端到端并发与创建助理复测

**Files:**
- Test: `tests/scenario/test_parallel_tool_e2e_regression.py`
- Verification: `./scripts/lca-ops kernel-restart` + live run creation
- Does NOT own: 任何宿主机配置

**Step 1: 运行全量关联测试套件**
Run: `pytest tests/scenario/ tests/nodes/ tests/infrastructure/ -k "parallel or envelope or history or parse" -v`

**Step 2: 执行代码门禁检查**
Run: `ruff check lca/ bundles/ && ruff format --check lca/ bundles/ && git diff --check`

**Step 3: 平滑重启内核并验证健康**
Run: `./scripts/lca-ops kernel-restart && ./scripts/lca-ops status --json`

**Step 4: 触发真实端到端创建助理测试并观测 Timeline**
Run: 真实对话触发创建助理意图，验证首轮正常 Defer 发现、次轮正常并发检索角色卡、向导顺畅推进、零 Prompt 泄漏。

**Step 5: Commit & 归档看板**
```bash
git commit -m "chore: complete parallel tool execution and run stability verification"
```
