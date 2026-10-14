# raphy assess — 2026-10-14 07:45 round (branch `raphy/arch-20261014-0745`)

ASSESS ONLY. No code outside `raphy/` was touched. Main tree was dirty
(`tests/scenario/openai/test_openai_compat_gateway.py`, someone else's
uncommitted work) — all reads happened in the isolated worktree at
`/home/lichao/.lca-worktrees/raphy-20261014-0745` (main tip `4e34c2d54`).

## Scope (YAGNI)

`git log --oneline -45` hotspots since 2026-10-13: raphy seam-convergence
work (RA-129/130 resolve_* seams, RA-136 `_model` probe convergence,
RA-137/138 approval + legacy ingress), approval-gate machinery
(`canonical_tool_name`, `approved_tool_names`, `lca-ops runs answer`,
`2e8264fb4` authorize fix), run binding via lobehub mapping
(`ee48d1d2e`, `4f67f10d7`, RA-129, RA-135 lazy import), LLM adapter
history projection (RA-117 anthropic closure).

Avoided: `tests/scenario/openai/` (dirty — someone else working there),
`ralph/` Round 2 areas, `lca/cognition/memory/` (standing 禁区).

Read first: `CONTEXT.md` (Profile 启动产物 / 程序化 Profile 输入 /
StopPolicy), `skills/improve-codebase-architecture/SKILL.md`,
`raphy/prd.json` (138 stories, 0 open), `raphy/progress.txt` top
(`## Codebase Patterns` + RA-115..138 learnings), ADRs 0292/0293.

Prior runtime findings: `runtime-findings-20261007.md` (P0
LoopObligationExceededError → fixed per RA-023; P2 None-input crash,
str-arguments cryptic error, anomaly_detector noise). The 01:45 round's
`raphy-runtime-verify-20261014.py` was reused verbatim against this
round's clean worktree (see Runtime verification below).

## Friction walk — Area A: 授权门机 (approval / grant gates)

Files read end-to-end: `lca/nodes/act/authorize/authorize.py` (348 lines),
`lca/infrastructure/runtime_plane/access/approved_tools.py` (78 lines),
`lca/infrastructure/cli/commands/runs/answer.py` (136 lines),
`lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py`
(325 lines), `lca/infrastructure/tools/assistant/filter.py` (grant filter).
Framework chain verified: `lca/framework/graph/interpreter.py`
(`_port_registry_seed_from_runtime_plane`, `build_input(schema.required_inputs())`),
`lca/framework/graph/port_registry.py::build_input`,
`lca/contracts/protocols/graph/node_io.py::required_inputs`,
`lca/framework/graph/strategies/node_executor_strategy.py`,
`lca/framework/graph/adapter.py` (kernel seed),
`lca/framework/graph/lift/parsers.py::to_port_specs`,
`bundles/act/act_subgraph.yaml`, `bundles/primitive/llm_call.yaml`.

1. **浅模块扩张**: "tool grant authorization" forces bouncing across
   `filter.py` (`_required_grant`, tools.yaml filtering),
   `authorize.py` (`_required_grant_of` + `_grant_refusal_routing`),
   `approval_engine.py` (`evaluate`), `contracts/runtime/trust.py`
   (`TrustEnvelope`). One concept, four modules.
2. **浅模块**: `approved_tools.py` — ContextVar + `canonical_tool_name`
   heuristic; interface ≈ implementation in size, but the canonical
   heuristic is real depth (RA-132 proved its edge cases). Deletion test:
   deleting it moves the ContextVar into execute.py and the heuristic
   into two call sites — complexity moves, doesn't concentrate.
   Verdict: earns existence, barely.
3. **无 locality 的纯函数**: `canonical_tool_name` is pure; the real defect
   class (RA-132: `"tool_fs.read"` → `"toolFs.read"` mangling, verified by
   direct call in commit `a1c41360d`) hides in how the writer
   (`commands.py:294`, canonicalizes) and the passthrough
   (`execute.py:157`, does NOT canonicalize) pair up — not in the
   function body. Classic no-locality: unit tests of the function are
   green while the writer/reader contract is held only by discipline.
4. **渗漏 seam**: (a) `act.authorize` reads `PortName("tools")` from typed
   ports but never declares it — `bundles/act/act_subgraph.yaml:61`
   declares `inputs: [decision, state]` only, and
   `PortRegistry.build_input(schema.required_inputs())` projects only
   declared required inputs, so the read is **provably always None**;
   production silently falls back to the global
   `current_tools_service()` probe. The typed seam leaks into a global.
   (b) three safe-boundary implementations: `authorize.py`'s inline
   `startswith(("self_destruct", "rm_rf_root"))`, the
   `pre_dispatch_envelope_check` `safe-boundary:valid` verdict (RA-115:
   never actually runs), `ControlSlot.ACT_SAFE_BOUNDARY` plugin.
5. **可测试性**: the `tools`-port path of `act.authorize` cannot be
   exercised through the graph at all — only the ContextVar fallback is
   reachable. "The interface is the test surface": a test seeding the
   kernel `tools` port per the documented seam ("visible to every node
   that declares them", `adapter.py`) cannot reach this node.
   → **RA-140**.

Duplication found in this area (verbatim, byte-identical):
`filter.py:151-158::_required_grant` vs `authorize.py:59-66::_required_grant_of`
(`return str(getattr(tool, "required_grant", "") or "").strip()`).
The authorize copy's docstring admits it: "与
`lca.infrastructure.tools.assistant.filter._required_grant` 同语义".
Two verbatim occurrences = real seam (RA-136 precedent).
→ **RA-139 (Strong)**.

## Friction walk — Area B: LLM adapter 历史投影

Files read end-to-end: `lca/infrastructure/llm_adapter/openai_compat/history/_history.py`
(282 lines), callers: `chat/_chat_completions.py:212`,
`responses/_responses.py:104`, `anthropic/_anthropic_messages.py:140`,
`plugins/events/hooks/model_visible/adapter.py:109`.

1. **浅模块扩张**: "history → wire messages" bounces across `_history.py`
   (projection + sanitizers) and 4 callers. Moderate; the callers are
   thin (one call each), so locality is acceptable.
2. **浅模块**: the two sanitizers (`_sanitize_hanging_tool_calls` /
   `_sanitize_hanging_tool_use`) are ~60 lines each with a
   `list → list` interface — depth (closure algorithm) exceeds
   interface complexity. Not shallow. Deletion test: deleting either
   re-opens the 400-shape hole it closed (RA-117) — concentrates.
3. **无 locality 的纯函数**: the closure-window semantics differ —
   OpenAI closes hanging calls only before user / tool-calling-assistant
   / end-of-list (NOT before a text-only assistant message);
   Anthropic always closes when ids are missing. Both pure functions are
   unit-green; the divergence (is a text-only assistant message after
   hanging tool_calls legal on the OpenAI wire?) lives in neither —
   documented as "Choice" in the Anthropic docstring only. Noted, not
   storied: speculative without a failing wire case.
4. **渗漏 seam**: journal-neutral dicts are dispatched by hand-rolled
   `item.get("role")` string switches in both functions — the "neutral
   history" contract is not a typed seam, so a new role string must be
   taught to two places. Also asymmetric tolerance: OpenAI passes
   `arguments: str` through, Anthropic `json.loads` it. Noted, not
   storied (stable code, no failing case).
5. **可测试性**: good — pure functions pinned by RA-117 tests. The
   `_model` private-probe residuals from RA-106 (`credentials.py:131`,
   `driver_debug.py:190`) were re-checked: `credentials.py:131` now
   reads `getattr(adapter, "model_name", None)`; `driver_debug.py` has no
   adapter `_model` probe left. Remaining `_model` reads are
   `self._model` (own field, not a cross-object probe). No story.

Area B verdict: no new story. The two sanitizers are the "two = real"
shape, but both are stable, tested, and provider shapes genuinely
differ — converging them now is speculative.

## Friction walk — Area C: run 绑定 / assistant 身份

Files read end-to-end: `lca/infrastructure/persistence/lobehub_agents.py`
(46 lines), `command_endpoints.py` (relevant: 55-100, 160-240, 400-460),
`lca/infrastructure/persistence/user_store.py` (both
`assistant_id_for_agent` impls), `lca/contracts/protocols/assistant/ownership.py:96`.

1. **浅模块扩张**: "agt_* → asst_*" forces bouncing across
   `command_endpoints.py` (hand-written chain), the ownership protocol +
   two `user_store.py` impls (sqlite/postgres), and
   `lobehub_agents.agent_assistant_id_from_lobehub` (lobehub fallback).
   One question, three answerers, precedence in a comment.
2. **浅模块**: `lobehub_agents.py` (46 lines, one function) — deletion
   moves the SQL into the caller, but concentrates the fail-soft
   contract ("Never raises into the run-creation path", RA-135 lazy
   import). Earns existence. The `command_endpoints.py:63` lazy proxy
   (12 lines) exists only to keep the monkeypatch seam name stable for
   tests — shallow, but its deletion test concentrates test-seam
   stability; keep.
3. **无 locality 的纯函数**: n/a — the fail-soft logic is I/O-bound
   try/except, not extracted pure functions. Read the files; the question
   doesn't apply here.
4. **渗漏 seam**: `standing_files.py:97` and `avatar/routes.py:109`
   hand-probe `getattr(ownership, "assistant_id_for_agent", None)`
   instead of a typed accessor; `command_endpoints` mixes body parsing,
   ownership lookup, lobehub fallback, and mode resolution in one
   function — transport and identity concerns leak across the seam.
5. **可测试性**: the precedence chain (ownership → lobehub fallback) is
   only testable through the HTTP endpoint, never through a seam —
   "the interface is the test surface" fails. A
   `resolve_assistant_binding(agent_id)` seam owning the precedence
   would be unit-testable (ownership hit / lobehub hit / unbound).
   → **RA-141**.

## Runtime verification (mandatory)

Method: reused the 01:45 round's `raphy-runtime-verify-20261014.py`
verbatim, repointed at this round's clean worktree
(`/home/lichao/.lca-worktrees/raphy-20261014-0745`), `LLM_API_KEY=dummy`,
run on 252. Scenarios: (a) basic run → COMPLETED; (b) tool-call run;
(c) two sequential runs on one agent; (d) non-converging run →
`Result(status=failed)`, no exception (RA-023 regression).

Result (2026-10-14 08:07 CST, 252, clean worktree, `LLM_API_KEY=dummy`):

- (a) basic run → `status=completed` → PASS
- (b) tool-call run (NoopTool) → `status=completed` → PASS
- (c) two sequential runs on one agent → `completed / completed` → PASS
- (d) non-converging run (always tool-calls, max_steps=3) →
  `Result(status=failed)`, no exception → PASS (RA-023 regression holds)
- `DONE failures=0`

No P0 found. Note: two operator errors on my side during setup (script first
ran locally by mistake → FileNotFoundError; then the stdin pipe through
ssh252 delivered an empty file → silent exit 0; then forgot `LLM_API_KEY`
in the relaunch → kernel refused boot). None of these touch the repo.
Lesson for future rounds: after transferring a script via ssh252, always
`wc -l` the remote copy before launching; use the stdin-redirect form
(`ssh252 'cat > path' < localfile`), not a pipe.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-139 | `lca/infrastructure/tools/assistant/filter.py:151`, `lca/nodes/act/authorize/authorize.py:59` | 两处逐字相同的 `_required_grant` 探针；authorize 版 docstring 自认"同语义"却手抄一份 | 收敛到 `lca/infrastructure/runtime_plane/access/` 的公共 `required_grant_of(tool)` seam，两处调用方共用，删掉两个私有版 | locality: "如何读工具的 grant 声明"只存在一处；leverage: 声明机制变更（typed 字段）只改一处 | **Strong** |
| RA-140 | `lca/nodes/act/authorize/authorize.py:208`, `bundles/act/act_subgraph.yaml:61`, `lca/framework/graph/port_registry.py:98` | `act.authorize` 读 `tools` typed 端口但 yaml `inputs: [decision, state]` 从未声明；`build_input(required_inputs)` 只投影已声明端口 → 该读数恒为 None，静默回退到全局 `current_tools_service()` | 二选一：(a) 在 yaml + `declared_inputs` 声明 `tools`（如 `llm.invoke`），让 kernel-owned typed seam 真正流通；(b) 删掉死读，只走 `current_tools_service()` 并写明 | locality: tools 来源选择收进 seam；leverage: 端口路径可测试（"the interface is the test surface"）；消除"删 fallback 即静默绕过 grant 检查"的隐患 | Worth exploring |
| RA-141 | `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py:179-188`, `lca/infrastructure/persistence/lobehub_agents.py`, `lca/infrastructure/persistence/user_store.py:217,406` | "agt_* → asst_*" 有三个回答者（ownership store ×2 实现 + lobehub fallback），优先级靠 endpoint 注释手写链；`standing_files.py:97`、`avatar/routes.py:109` 还有手写 getattr 探针 | 新建 `resolve_assistant_binding(agent_id)` seam，内聚优先级（ownership → lobehub fallback，保留 RA-135 的 lazy-import fail-soft 边界），endpoint 只调 seam | locality: 绑定优先级只存在一处；leverage: 新调用方不再手写链；seam 可单元测试（hit/miss/unbound） | Worth exploring |

## Self-grilling

### RA-139 — 收敛 `_required_grant` 双胞胎
- **Constraints**: 行为零变更（同一 body）；ADR-0292 §10 的 grant 语义不动；
  `filter.py` 的调用方（tools.yaml 过滤）与 `authorize.py` 的调用方
  （`_grant_refusal_routing`）行为一致。
- **Dependencies**: 调用方 2 处（`filter.py:92`、`authorize.py:145`）；
  被调用方无（纯 getattr 探针）。移动 seam 不影响任何其他模块。
- **Shape**: `lca/infrastructure/runtime_plane/access/` 新增公共函数
  `required_grant_of(tool: object) -> str`（命名对齐既有的
  `canonical_tool_name` 公共导出风格）；两处改 import + 删私有函数。
  不从 `filter.py` 反向 import（filter 是 assistant 域，access 是策略域，
  方向应为两者都依赖 access）。
- **Test survival**: 现有 grant 相关测试（filter 的 tools.yaml 过滤测试、
  grant-refusal 路由测试）必须全绿；新增测试钉住"同一 tool 对象两处读数一致"。
- **Deletion test verdict**: concentrates — "读 grant 声明"的方式只存在一处；
  删掉任一私有版不丢信息。

### RA-140 — `act.authorize` 的 `tools` 端口死读
- **Constraints**: 生产行为零变更（今天恒走 fallback）；ADR-0241 §2 的
  kernel-owned 端口语义不动；`grant_routing` 输出端口不动。
- **Dependencies**: 读方 1 处（`authorize.py:208-214`）；seed 方
  （`interpreter.py:96` + `adapter.py:60`）是全图共享机制；yaml
  `act_subgraph.yaml:61` 是声明方。改声明不影响其他节点（投影按节点
  各自 schema 过滤）。
- **Shape**: (a) yaml `inputs: [decision, state]` → 加 `tools`（bare string
  即 required，如 `llm_call.yaml:18` 的 `[render, tools, state]`），
  executor `declared_inputs` 同步加 `PortName("tools")`，保留
  `current_tools_service()` 作为 fail-soft 回退；(b) 或删死读。
  推荐 (a)——注释本意就是读端口（"tools 是 kernel-owned 端口"），让意图成真。
- **Test survival**: 现有 act.authorize / grant 测试全绿；新增测试：
  经真实 interpreter seed `tools` 端口，断言 `act.authorize` 的
  `node_execute` 收到的是 seed 的 ToolsService 而非 fallback
  （今天该测试失败——端口恒为 None）。
- **Deletion test verdict**: (a) concentrates — tools 来源从"端口读数+
  全局回退"的双路径收进"端口优先、回退兜底"的单一语义；(b) moves —
  删读数只是把意图藏得更深。选 (a)。

### RA-141 — `resolve_assistant_binding` seam
- **Constraints**: 优先级不变（ownership store → lobehub fallback）；
  fail-soft 边界不变（无 DB / 无映射 → unbound，不 raise 进 run 创建）；
  RA-135 的 lazy-import 边界保留（import 期失败不炸 endpoint 模块）；
  ADR-0187 §3 D7 的 mapping 真值（`agency_config->>'lcaAssistantId'`）不动。
- **Dependencies**: 调用方：`command_endpoints.py:179-188`（主链）、
  `standing_files.py:97`、`avatar/routes.py:109`（手写探针，可选收敛）；
  被调用方：ownership 协议（sqlite/postgres 双实现）、`lobehub_agents`。
- **Shape**: 新 seam（如 `lca/infrastructure/persistence/assistant_binding.py`
  或归入 ownership 协议实现）`resolve_assistant_binding(agent_id,
  ownership) -> str | None`，内部先 ownership 后 lobehub，lazy import
  保持；endpoint 删手写链只调 seam。
- **Test survival**: `4f67f10d7` 的 lobehub fallback 测试、`ee48d1d2e` 的
  binding 测试全绿；新增 seam 级测试：ownership 命中 / lobehub 命中 /
  双 miss → None（今天只能经 HTTP endpoint 测）。
- **Deletion test verdict**: concentrates — 优先级逻辑从 endpoint 注释
  收进可测试的 seam；删掉任一数据源分支会丢行为（fail-soft 需要两者）。

## Diversity quota

最终 3 个 story：RA-139（duplication，逐字两次=Strong，RA-136 实证过的类）、
RA-140（friction walk：可测试性缺口 + 渗漏 seam）、RA-141（friction walk：
浅模块扩张 + 渗漏 seam）。不全是 duplication；两个来自 friction walk。✓

## Noted but not storied (deliberate)

- `canonical_tool_name` 的 dotted 名 mangling（RA-132 已用 direct call 验证
  `"tool_fs.read"` → `"toolFs.read"`）：生产链自洽（commands.py:294 写时
  canonical → execute.py:157 透传 → authorize.py:281 读时 canonical），无
  bypass。RA-132 证明"把规范化搬进 setter"的三约束不可兼得；leaf-only
  修复对 wire 形态（namespace 是否 camelCase）是推测 —— Speculative，不入。
- sanitizer 闭包窗口语义差异（OpenAI vs Anthropic）：无失败 wire case，Speculative。
- journal-neutral history 的手写 role switch：稳定代码，无失败 case。
- RA-106/136 的 `_model` 残留已收敛（`credentials.py:131` 现读
  `model_name`；`driver_debug.py` 无 adapter 探针；剩余为 `self._model`）。

## Top recommendation

**先做 RA-139**。它是三者中证据最硬的（逐字相同 body + 作者自认同语义，
RA-136 的"two = real"判据直接适用），改动最小（一个新公共函数 + 两处
import），行为零变更，deletion test 通过。RA-140 次之（接口诚实性，
但今天生产行为正确，属预防性）。RA-141 解决的是真实存在的"优先级只
活在注释里"问题，但涉及 transport 层，面比前两者大。

Assessment complete: 3 stories written, top is RA-139.
