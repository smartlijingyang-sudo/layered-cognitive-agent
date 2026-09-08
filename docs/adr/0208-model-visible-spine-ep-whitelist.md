# ADR-0208 — Model-Visible Spine EP 白名单收口：四 SSOT 一致 + 字节布局 fail-loud

## 状态

**Implemented — 2026-09-08。**

`SPINE_EXECUTION_POINTS` 与 `_SPINE_EP_TO_CATEGORY` 同时补齐 `llm.request.header` + `llm.request.header.assistant`；`SpineEventRecord.__post_init__` 加白名单校验；两处 `category_to_spine_ep(...) or "unknown"` 改为 fail-loud；`tests/architecture/test_spine_ep_yaml_registry.py` 新增"四 SSOT 一致 + publisher 落 EP ⊆ 白名单"断言。回归 run `run_d91b20e29c5a` 验证 step3 不再出现（修复前重复 2 次 `runCommand`，修复后只剩 1 次）。

**Builds on**：ADR-0185（model-visible fold、PR-1/PR-2/PR-3）、ADR-0186（Session SSOT）、ADR-0181（spine 闭集迁移）、ADR-0184（投递可达性：D7 落盘事件必须可按 EP 查询）。

**Fixes**：`run_d91b20e29c5a`（2026-09-08）step3 重复调 `runCommand`。根因：assistant 决策事件 `spine.llm.request.header.assistant` 落到 spine 时 `_SPINE_EP_TO_CATEGORY` 表反查失败，被 fallback 写成 `execution_point="unknown"` 字符串；`SpineEventRecord`（PR-5 新字节布局 SSOT）未保留 `EventRecord.__post_init__` 的白名单校验，导致 C11 闭集硬约束被悄悄绕过；fold 拿不到 assistant 事件，下一轮 LLM messages 只剩 `role=tool` 孤儿消息，qwen 协议层补一轮 tool call 来让 schema 合法。

## 0. 决策摘要

修复 `SPINE_EXECUTION_POINTS` 与 `_SPINE_EP_TO_CATEGORY` 闭集补齐 + `SpineEventRecord` 重新接入 fail-loud，让 spine 字节布局恢复 C11 硬约束。**不修改 fold 行为**：fold 仍按"assistant 事件落盘 → 取最新"路径走，依赖白名单已正确扩齐。

不动 `category_to_spine_ep(...) or "unknown"` 这一**语义**——保留字符串 `"unknown"` 用于"非 spine category 落盘"的兜底（如 typed payload 完全无 category 的极端情况）；但针对**反查失败**的两处调用点，改为抛 `UnknownExecutionPoint`，让 spine.* 的 EP 必须可解。

## 1. 根因（第一性原理）

spine EP 落盘有两个消费者在反查 EP 名：

| 调用点 | 代码 | 当前行为 | 应有行为 |
|---|---|---|---|
| `_build_event_record`（typed payload 反查 EP） | `category_to_spine_ep(...) or "unknown"` | 反查失败 → `"unknown"` 字符串落盘 | 反查失败 → `UnknownExecutionPoint` |
| `_map_session_event`（Session→spine envelope 映射） | `category_to_spine_ep(event.type) or "unknown"` | 同上 | 同上 |

两处共用同一白名单与翻译表。当前表：

| 表 | 内容 | 是否含 `llm.request.header.assistant` |
|---|---|---|
| `SPINE_EXECUTION_POINTS`（顶层 tuple） | 75 EP（ADR-0181 试点迁 1 个，余 74 个按 PR 切分逐个扩） | **否**——含 `llm.stream.token`、`llm.call.start/end`，**不含** `llm.request.header` / `llm.request.header.assistant` |
| `_SPINE_EP_TO_CATEGORY` | EP → category 反查表 | 同上 |
| `lca_kernel/events/config/observability/spine.yaml` | category→payload_class 字典 | **含** `spine.llm.request.header.assistant`（line 308） |
| `lca_kernel/events/config/observability/closure_catalog.yaml` | execution_point→layer/producer 字典 | **含** `execution_point: llm.request.header.assistant`（line 27） |
| `lca_kernel/events/config/projections/registry.yaml` | projection→input_include 字典 | **含**（line 26） |

**结论**：四份 YAML/SSOT 中**三份已登记**这条 EP；唯独 `SPINE_EXECUTION_POINTS`（Python 顶层闭集）+ `_SPINE_EP_TO_CATEGORY`（Python 顶层翻译表）**漏配**。这是 PR-2 当年（a334098e，2026-09-04）扩 spine.yaml 时**没同步扩 Python 闭集**的债。

## 2. 字节布局约束失效（PR-5 副作用）

PR-5（ADR-0183）把字节布局从 `EventRecord`（14 字段 dataclass + `__post_init__` 白名单校验）迁到 `SpineEventRecord`（10 字段 dataclass，**无** `__post_init__` 校验）。白名单校验在 `_build_event_record` 反查分支被静默 fallback 字符串 `"unknown"` 绕过——这把 C11 的"白名单扩"硬约束变成了**软约束**（仅在 `SpineEventPayload` 显式 `execution_point` 字段时被校验，typed 子类全靠反查）。

修复必须**同时**做两件事：
1. 把白名单补齐（恢复"有 → 解"的语义）
2. 把 `SpineEventRecord.__post_init__` 加回白名单校验（恢复"无 → fail"的硬约束）

## 3. 不变量

| 编号 | 提法 | 落点 |
|---|---|---|
| **C11'** | 四 SSOT 一致：`SPINE_EXECUTION_POINTS` ⊇ `_SPINE_EP_TO_CATEGORY.values()` ⊇ `closure_catalog.yaml[].execution_point` ⊇ `spine.yaml[].category` 的 category 前缀剥离集合 | `tests/architecture/test_spine_ep_yaml_registry.py` |
| **C11''** | `SpineEventRecord.__post_init__` 校验 `execution_point ∈ SPINE_EXECUTION_POINTS`；反查失败的 typed payload 必须抛 `UnknownExecutionPoint` | `lca_kernel/events/spine/runtime.py` |
| **C13'** | publisher 落 EP ⊆ `SPINE_EXECUTION_POINTS`；publisher 显式登记的 `event_publishes` 必须 ⊆ `_SPINE_EP_TO_CATEGORY` | 同一测试 |

## 4. 实施切片（一次到位）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `lca_kernel/events/payloads/spine.py` | `SPINE_EXECUTION_POINTS` tuple 加 `"llm.request.header"` + `"llm.request.header.assistant"`；`_SPINE_EP_TO_CATEGORY` 加对应条目 |
| 2 | `lca_kernel/events/spine/runtime.py` | `SpineEventRecord.__post_init__` 加 `execution_point ∈ SPINE_EXECUTION_POINTS` 校验；`_build_event_record` 反查失败改为抛 `UnknownExecutionPoint` |
| 3 | `lca_kernel/events/persistence/persistence.py` | `_map_session_event` 反查失败改为抛 `UnknownExecutionPoint`（保留 `data.execution_point` 显式传值的路径） |
| 4 | `lca_kernel/events/payloads/spine.py` | 新增 `UnknownExecutionPoint` 异常类（继承 `ValueError`，message 含 owner 指引：spine.yaml + ADR-0185 §3.3） |
| 5 | `tests/architecture/test_spine_ep_yaml_registry.py` | 新增 `test_four_ssot_consistent` + `test_publish_eps_under_whitelist` |
| 6 | `tests/integration/test_model_visible_e2e.py` | 新增一条端到端断言：assistant 事件落盘后 `execution_point` 必须等于 `llm.request.header.assistant`（不允许 `"unknown"`） |

## 5. 删除条件（delete-when）

- 当 **三层 SSOT 一致**不变量 + **SpineEventRecord fail-loud** 两条测试都进 CI 主分支并连续绿 1 个月后，本 ADR 可标 `Stable`，删除实施切片改动后的"修复"叙事文字。
- 当 ADR-0195 P1-18 manifest.py inline tuple 退役后，`SPINE_EXECUTION_POINTS` 不再硬编码于 `lca_kernel/events/payloads/spine.py` 而是从 yaml 加载——届时本 ADR 的实施切片 #1 需重写为"yaml 是 SSOT，Python tuple 是 cache"，校验从 yaml 出发。

## 6. 拒绝的反例

- **拒绝**：在 fold 层加 assistant 消息派生逻辑（从 `step.tool_call.record` 重建）。理由：fold 的输入条件是"已落盘"，不应在 fold 层兜底"未落盘"——那会让 fold 边界漂移到"事件层"，违反 C13 fold 信息血统；正确做法是事件层先保证落盘，fold 不变。
- **拒绝**：把 `category_to_spine_ep(...) or "unknown"` 整体替换为更宽松的 fallback。理由：保留 `"unknown"` 用于"非 spine category 落盘"语义（其它 typed payload），但**针对 spine.* category** 反查失败要 fail-loud。
- **拒绝**：把 `SpineEventRecord` 的字节布局迁回 `EventRecord`。理由：PR-5 的 10 字段字节布局是 SSOT，PR-5 的 trace_id 注入是合理演进；回退会损失 trace_id 字段。

## 7. 验证命令

```bash
# 单元/架构层
uv run pytest tests/architecture/test_spine_ep_yaml_registry.py -v
uv run pytest tests/integration/test_model_visible_e2e.py -v

# 端到端
./scripts/lca-ops kernel-restart   # 若失败回退手动
./scripts/lca-ops runs create --user-text "用 shell 工具执行 ls -la /tmp 并把结果原样复述给我" --wait --json
./scripts/lca-ops journal narrative <run_id>   # 应只有 1 个 perceive + 1 个 tool 调用；无 step3
./scripts/lca-ops journal steps <run_id> | head  # 总步数 = 2（think + perceive），无第三个 perceive
```

## 8. 风险与回滚

- 风险：白名单扩错，致合法 publisher 被拒。回滚：恢复 tuple 与 dict 内容即可。
- 风险：`SpineEventRecord.__post_init__` 引入 `RuntimeError` 阻塞正常 publish。回滚：移除新校验；保留白名单扩。
- 风险：第三方插件（vendored / vendored-pending）落 EP 名字不熟。回滚：先记录到 ADR-0208 风险段，再扩白名单。

## 9. 配套 Note

`docs/notes/implemented/seam/2026-09-08-model-visible-ep-whitelist.md`（落地后从 proposed 改 implemented）。