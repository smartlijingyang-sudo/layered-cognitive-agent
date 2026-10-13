# Raphy Assess — 2026-10-14 04:45 round

Branch: `raphy/arch-20261014-0448` (main tip `91c6e85be` at assess).
Assess ran as a fresh session; implementation untouched — only `raphy/` files change in this commit.

Related prior rounds: 2026-10-14 01:45 round (RA-131..RA-135, merged `91c6e85be`); its
areas A/B/C are closed — this round walks new ground. Since `31e7db97a` the only
new commits are RA-131..135 themselves, so hot spots = the areas those stories touched.

Environment: 252 repo `~/layered-cognitive-agent`, branch
`raphy/arch-20261014-0448` (= main tip `91c6e85be`, `status --porcelain` empty).
禁区遵守：ralph Round 2 未进、`lca/cognition/memory/` 未碰、`gate_chain_strategy.py`
未碰、preamble.py 未碰；webserver carrier 只读评估（lca-1000 领地说明见各 story 的
territory note）。

## Explore

1. **Hot spots → 3 friction-walk areas.** Areas D and E each delegated to a
   fresh-session subagent (read-only, zero writes). Area F's worker returned a
   confused completion with no report (treated as undelivered); the coordinator
   re-walked Area F directly, read-only.
   - D: webserver runs chain post-RA-131/135 (resume ingress seams).
   - E: model-identity private `_model` probes (RA-106 follow-up, explicitly deferred).
   - F: skills `_package_lookup` post-dedup (`991ff7ba3`) + RA-107 landing check.
2. **CONTEXT.md**: read (profile-launch-product / programmatic profile input /
   StopPolicy vocabulary). No new domain term needed by this round's stories.
3. **runtime-findings**: `hidden_files/runtime-findings-20261007.md`; its P0 (RA-023)
   re-verified this round — non-converging run returns `Result(status=failed)`,
   no exception. Holds.

## Friction walk

### Area D — webserver runs chain post-RA-131 (subagent, read-only)

Files read: `command_endpoints.py` (1–330: `_decode_resume_approval` :247–273,
`CreateRunRequest` :101–143; 560–882: `create_run`, `_dispatch_resume` :664–742,
`answer_run` :790–838), `terminal/registry/commands.py` (1–325 full:
`resume_approval` :148–158, record point :285–295), `terminal/port/port.py`
(:60–160, `RunPort.resume_approval` Protocol :100–111),
`session/session.py` (1–345 full), `carrier/runs/resume.py` (1–55 full),
`carrier/runs/execute/execute.py` (:130–170), `carrier/runs/lifecycle/lifecycle.py`
(:250–265), `runtime_plane/access/approved_tools.py` (1–55 full),
`routes_2/routes_runs_sessions.py` (:57), `carrier/runs/recovery.py` (1–30),
`tests/plugins/transport/webserver/test_resume_approval_rejection_not_recorded.py`.

- **Q1** （浅模块蔓延）: "拒绝"一概念横跨 8 模块（decode 的 dict 约定 →
  `CreateRunRequest` 字段 → `_dispatch_resume` fold+bool 导出 → `RunPort` kwarg →
  记录点守卫 → ContextVar → execute 注入 → authorize 读取）；编码/推导/守卫/
  注入/读取各住一处，概念无单一 home。Locality 差 → 候选 2/3。
- **Q2** （shallow）: `approved_tools.py` (55 行) shallow——interface 几乎与实现
  同等复杂；deletion test = 搬运复杂度，可被吸收（非 story，记录在此）。
  `carrier/runs/resume.py::resume_run` 的 deletion test 更强：零调用方，
  删了什么都不变 → **候选 RA-137 (Strong)**。
- **Q3** （无局部性 / bug 藏身处）: `canonical_tool_name` 是教科书纯函数；
  真风险在调用处组合：`_dispatch_resume` 的 `resume_tool_result or
  resume_approval` 真值折叠（双字段并存时静默选前者）、`content =
  get("content") or get("rejection_reason")`（拒绝理由文本被当作 resume 答案注入
  loop）、`is_rejection = bool(get("rejection_reason"))`（未来批准附 reason 即误判）。
  纯函数可测，seam 处组合不可测 → 候选 3 的动机。
- **Q4** （泄漏接缝）: ① `RunPort.resume_approval` 上拒绝语义双通道泄漏
  （`payload: str` 拒绝时装理由文本 + `is_rejection: bool` 默认 False）；
  两个 adapter（legacy `answer_run` + 新 `_dispatch_resume`）对同一命令持发散不变量；
  ② `CreateRunRequest.resume_approval: dict[str, Any] | None` 把未类型化 dict
  泄漏过 decode→dispatch 边界。→ 候选 2/3。
- **Q5** （可测试性）: ① RA-131 守卫的 pinning 测试绕过 `RunPort`/HTTP
  interface（经公共接口到不了 `is_rejection=True`）；② `_dispatch_resume` 的
  fold 只能 e2e 或调私有函数；③ execute 注入与 authorize 读取被 task 边界隔开，
  port/authorize 接口都不暴露 approved set。

**顺带证伪**: `approved_tool_names` 无无界增长担忧——per-session `set[str]`，
生命周期归 `RunRegistry`→`RunSessionIndex`（`max_terminal`+`terminal_ttl_s` TTL）
+ `RunTerminalizer.terminalize`→`session.close()`；"无清理代码"是不需要，不是缺失。
Legacy `resume_run`（`carrier/runs/resume.py:48`）零生产调用方——三个 import 点只拿
`resume_cache_ready`/`validate_durable_resume`（coordinator 独立复验确认）。

### Area E — model-identity private probes (subagent, read-only)

Files read: `driver_debug.py` (:150–240, probe :190),
`cli/commands/kernel/_shared.py` (:188 `emit_report`),
`lca/plugins/think/reasoner/credentials.py` (:60–141, probe :131 —
RA-106 记录的 `think/reasoner/credentials.py` 已搬迁至此),
`contracts/protocols/runtime/infra/infra.py` (:32–57, `LLMAdapter.model_name`
:51, default `return None`), `llm_adapter/openai_compat/__init__.py` (:51–92),
`llm_adapter/mock/llm.py` (:27–45), `llm_adapter/model_override.py` (:20–50),
`observability/adapters/adapters.py` (:59–67 `_model_label`, :135–182),
`llm/resolver.py` (:81–105), `plugins/events/hooks/model_visible/adapter.py`
(:66–84), `tests/unit/observability/adapters/test_model_label.py`.

- **Q1**: "模型身份"跨 5–6 模块（contracts 声明 → 3 覆写 + anthropic 内部字段 →
  observability `_model_label` → think credentials 探针 → model_visible unwrap 链 →
  cli driver_debug 探针）。
- **Q2**: 两处探针都是一行 getattr 链，shallow。Deletion test：删掉任一处，
  **零测试变红**（无任何断言钉住 `"adapter_model"` payload 或 driver_debug 的
  `"model"` 键；唯一相关测试 `test_model_label.py` 钉的是 interface）→ 无主死知识。
- **Q3**: `_model` 定义在 `infrastructure/llm_adapter/`，读者在
  `infrastructure/cli/commands/runs/` 和 `plugins/think/reasoner/`——三处分属
  不同 seam，owner 与 reader 零 locality。
- **Q4**: 是跨 seam 泄漏。且 `or getattr(adapter, "model", None)` 的"公共回退"
  读的是**不存在的属性**（`llm_adapter/` 下零 `self.model` 定义）——伪装成防御式
  读取的纯私有探针。interface 在"说"一套（`model_name`），探针在做另一套。
- **Q5**: 能。`getattr(adapter, "model_name", None)` 即 the interface is the test
  surface。行为实证：`MockLLMAdapter` 上探针返回 `None`，interface 返回
  `"mock-llm"`——interface 严格更优。

**核实**: `getattr(adapter, "_model"` 全仓恰好 2 命中；`def model_name` 恰好 4 处
（协议 + 3 覆写：openai_compat/mock/model_override）；anthropic 的 `_model` 是
内部 helper 自用字段（构造传入），非探针。**"two = real" 成立**：同一模式逐字
两次出现 → **候选 RA-136 (Strong)**。
注记（scope 外）: `model_visible/adapter.py:78` 的 unwrap 链读公共属性为主，
本轮不动，记在此。

### Area F — skills `_package_lookup` post-dedup (coordinator, read-only)

Files read: `lca/infrastructure/tools/skills/_package_lookup.py` (28 lines, full),
`git show 991ff7ba3 --stat`, scoped `rg list_installed` / `resolve_package` in
`lca/infrastructure/tools/skills/`, `git log --grep="RA-107"`.

- `resolve_package(store, raw)`: exact-id → case-insensitive-name fallback → None。
  3 调用方（activate/deactivate/retire）已全部收敛；`search/tool.py:158` 的
  `list_installed()` 是搜索列表用途，非同类探针。无"two = real"漏网。
- Deletion test: 删掉它只是把 10 行搬回 3 处（moves，非 concentrates）——但它已是
  既成收敛，无新故事。
- RA-107 已落地（`a0f547f91` + `4aee9b124`），无需跟进。
- **F 区 0 候选。**

## Runtime verification (mandatory, clean tree)

Branch `raphy/arch-20261014-0448` (= main tip `91c6e85be`, clean),
`LLM_API_KEY=dummy`, `ScriptedLLMAdapter` (`tests/harness/scripted_llm.py`),
`sys.path.insert(1, tests)`（防 `tests/lca_kernel` 桩包遮蔽真包——上轮教训重申）。

| # | Flow | Result |
|---|------|--------|
| 1 | Basic run → COMPLETED | ✅ PASS |
| 2 | Run with a tool call (NoopTool, namespace="probe") → COMPLETED | ✅ PASS |
| 3 | Two sequential runs on one agent → completed / completed | ✅ PASS |
| 4 | Non-converging run (always tool-call, max_steps=3) → `Result(status=failed)` | ✅ PASS — **no exception**, RA-023 holds |

**No P0 candidates.** (Side note: anomaly_detector cycle/stalled 日志警告仍在，P2，
既往轮已记录。)

## Duplication scan (secondary)

No new mechanical duplication clusters. Remaining hand-rolled
`getattr(runtime, ...)` probes in `lca/nodes/` match the 01:45 round's Area B
6 declined points (memory_extract `agent_state` ×2, route/shortcut fail-loud
`RuntimeError`, render brain probes, memory keys ×2, reducer keys ×2) — decline
reasons still stand. `lca/nodes/_resolve.py` remains the converged deep module.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-136 | `lca/infrastructure/cli/commands/runs/driver_debug.py:190`, `lca/plugins/think/reasoner/credentials.py:131` | 两处**逐字相同**的私有 `_model` 探针（`getattr(adapter, "_model", None) or getattr(adapter, "model", None)`），绕开 RA-106 落地的 `model_name` 协议；回退读的公共 `model` 属性在所有生产适配器上根本不存在；Mock 上探针返回 None 而 interface 返回 "mock-llm"。deletion test 通过（删掉零测试变红）。 | 两处统一换成 `getattr(adapter, "model_name", None)`——与 `_model_label` 完全一致的协议读取。 | Locality: 身份读取回到 `LLMAdapter` 协议 seam，adapter 内部可自由重命名 `_model`。Leverage: debug 输出、served 事件、telemetry 三方读到同一值。 | **Strong** |
| RA-137 | `lca/plugins/transport/webserver/carrier/runs/resume.py` (:47–55, `__all__`) | `resume_run` 零生产调用方（3 处 import 只拿 `resume_cache_ready`/`validate_durable_resume`，coordinator 独立复验）、零测试引用；且与 `execute.py:146` 的同名 `resume_run`（带 approved-tools 注入）形成同名双胞胎——未来调用方选错模块会静默丢失注入。footgun，不是备用代码。 | 删 `resume_run` 定义，`__all__` 缩为 `["resume_cache_ready", "validate_durable_resume"]`。 | Locality: resume 入口唯一化。Leverage: 以后 resume 改动不再需要先分辨"调的是哪个 resume_run"。 | **Strong** |
| RA-138 | `command_endpoints.py` (`answer_run` :790–838, `_dispatch_resume` :664–742), `terminal/port/port.py` (:100–111), `routes_2/routes_runs_sessions.py` (:57) | 同一 `RunPort.resume_approval` 有两个 adapter，不变量发散：legacy `POST /runs/{run_id}/answer` 纯字符串 payload 表达不了拒绝，而 Protocol 默认 `is_rejection=False` 把"表达不了"静默翻译成"已批准"——RA-131 的守卫在该路由上形同虚设。recovery.py docstring 证实 legacy `/answer` 仍是被考虑的路径。 | 先取证：LobeHub 前端是否还在调 `/answer`。(a) 已迁移 → 退役路由（deprecation 期后删）；(b) 仍在调 → 给 legacy payload 带内拒绝标记，在 `answer_run` 内显式导出 `is_rejection`。绝不能保持"默认 False"的沉默。 | Locality: "拒绝必须显式"的不变量收敛到 port seam 一处。Leverage: 记录点守卫对两条 ingress 同时可信。 | Worth exploring |
| (RA-139, deferred) | `command_endpoints.py` decode 层 + `RunPort` | approve/reject/tool_result 三态以 dict 键非空约定存在，`_dispatch_resume` 用 `or` 链重新推导——类型信息过早序列化成字符串、下游再解析。 | decode 层产出 frozen dataclass `ResumeAnswer(kind, ...)`；port 去掉 `is_rejection` 的 False 默认（逼 legacy adapter 显式表态）。 | — | Speculative → **本轮不写 story**（与 RA-138 同源，等 RA-138 取证结论再定形状，避免两次动 port 签名） |

### Self-grilling (per candidate)

**RA-136**
- Constraints: 不改 `model_name` 协议签名；`TelemetryLLMAdapter` 不覆写 `model_name`
  （默认 None），收敛后行为与探针一致（None），无回归；`model_visible/adapter.py:78`
  unwrap 链 scope 外。
- Dependencies: 依赖 RA-106 的 3 个 `model_name` 覆写（openai_compat/mock/
  model_override）；anthropic 内部 `_model` 是构造传入的自用字段，不受影响。
- Shape: 两行 getattr 替换，无结构变化。
- Test survival: `test_model_label.py` 继续绿；探针零测试钉住，替换不红。
- Deletion test verdict: **PASS**（删除探针零测试失败）→ 探针无主，应当收敛。
- Territory: 两文件近期提交全是用户侧 rounds（think-subgraph/ADR-0220、cli
  style/region），无 lca-1000 churn。

**RA-137**
- Constraints: 无——coordinator 独立复验：3 处生产 import 只拿
  `resume_cache_ready`/`validate_durable_resume`；测试里
  `monkeypatch.setattr(registry_commands, "resume_run", ...)` patch 的是
  `execute.execute` 版（`commands.py:20–24` 从 execute 导入），不是死代码。
- Dependencies: 无。
- Shape: 纯删除约 10 行（def + `__all__` 条目）。
- Test survival: 无测试引用死函数。
- Deletion test verdict: 删掉"无调用方的别名"= 净收益；消除同名双胞胎 footgun。
- Territory: webserver carrier 是 lca-1000 领地，但该文件近 8 个提交全是用户侧
  工作（runtime/types/import-sort/arch-discipline），lca-1000 无活跃 churn；
  且改动是纯删除，不碰任何行为。

**RA-138**
- Constraints: `payload: str` 是线契约；老前端可能仍发纯文本答案，不能 break。
- Dependencies: routes_2 注册、LobeHub deploy patch 的前端行为、幂等键语义。
- Shape: 小——一个调用点 + 可选 deprecation shim；或整条路由退役。
- Test survival: RA-131 测试只覆盖新路径；新测试（"经 `/answer` 的拒绝不被记录"）
  今天写不出来——这正是问题本身。
- Deletion test verdict: 若前端已无人调，删 `answer_run` 是纯删。
- Territory: 同 RA-137（webserver carrier，用户侧 runs 工作区，lca-1000 无 churn）。

### Top recommendation

先做 **RA-136**：两行改动、零风险、interface 在行为上已被实证更优（Mock 反例），
且测试已钉住 interface——这是"收敛"类 story 里风险收益比最高的一档。接着
**RA-137**：纯删除，消除同名双胞胎 footgun。**RA-138** 需要先取证（LobeHub 前端
是否还在调 `/answer`），取证结论决定它是"退役路由"还是"补拒绝标记"。

Diversity quota: 3 个 stories 全部来自 friction walk（shallow/无主探针、死代码、
发散 ingress），无 duplication-class。✅

Assessment complete: 3 stories written, top is RA-136.
