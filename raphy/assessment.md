# Raphy Assessment — Round 8 (2026-10-08 05:06, branch `raphy/arch-20261008-0506`)

ASSESS ONLY. 本轮按硬化版 `raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`
→ git log 热点定域 → CONTEXT.md + 相关 ADR → 三区 friction walk（5 问必答，端到端精读非 grep）
→ mandatory runtime verification（mock LLM 真跑：basic / tool-call / 双 run / 非收敛复现）
→ duplication 副扫描 → self-grilling → stories 入 prd.json（`userStories` 键，RA-028 起编号）。

## Scope（YAGNI）

`git log --oneline -40` 生产代码热点（排除已做故事领地 + 纯测试 + 禁区）：
- `lca/infrastructure/host_runtime/providers/user_cli.py` ×3 → 其中 2 笔是 RA-014/015 自己的
  converge，第 3 笔是其后续 fix（`7aa5a7202` unlink tempfile in finally）。Round 7 评估曾整体避开，
  但本轮 friction walk 只走**观察路径**（status/heal），RA-014/015 的 scope 是 start/stop
  lifecycle——不重审已收敛部分，只看 RA-014 声明 seam 后**仍绕行**的 status/heal。
- `lca/infrastructure/observability/adapters/policy.py` ×2 → 含 iter-tests 的 revert 战
  （`3a7bc323a` 恢复 `e51902b07` 删掉的 else），iter lane 刚动过，避开。
- `tests/integration/test_persist_before_execute.py` ×2 → persist-before-execute 是活跃 seam，
  其生产侧 `lca/cognition/body/executor/simple_body.py` 无 raphy 故事覆盖，可走。
- 其余热点（model_visible hook、schedulers、fold_source、tool_search）均为 RA-023~027 领地，避开。
- 禁区遵守：ralph Round 2（DecisionGates / Ingest / ContextFiles shims / Read Runs micro-dirs /
  `lca/cognition/memory/`）、lca-1000 迁移领地（`plugins/transport/webserver/`、`contracts/event.py`）、
  `gate_chain_strategy.py`（他人工作）、`brain/decision_gates/`（Round 2 领地）。

三区 friction walk 定域（精读文件，非 grep）：
- **Area A**：host_runtime providers（`providers/user_cli.py` 225 行 / `shared.py` 258 行 /
  `user_workspace.py` 57 行 / `user_account.py` 67 行 / `providers/__init__.py` 128 行全文）
  + 对比 `lca/infrastructure/cli/services/daemon/daemon.py` 的 `state()`/`restart()`（200-262 / 85-164 行）。
- **Area B**：`lca/cognition/brain/llm_turn/`（`executor.py` 195 行 / `mode.py` 18 行 / `policy.py` 37 行 /
  `response_projection.py` 134 行 / `__init__.py` 18 行全文）+ `NativeToolCall` 类型定义
  （`contracts/models/core/conversation/llm.py` 24-46 行）。
- **Area C**：`lca/cognition/body/executor/simple_body.py`（399 行，dispatch_tool_calls 全路径精读）
  + `state.extra["current_turn"]` 的写方（`harness/projection/agent_state.py:70`）与另一读方
  （`nodes/think/llm/invoke.py:104`）。

## Friction walk — 5 问必答

### Area A：host_runtime providers（daemon 观察路径）

1. **理解一个概念要在多少小模块间跳？** "daemon 当前状态"要跳 4 处：`CLIProvider.status()`
   → `_report_daemon_status`（直读 pid 文件）→ `DaemonService.state()`（另一套状态计算）
   → `ServiceState`（`cli/service/service.py`）。同一个 daemon，两套状态推导。
2. **shallow module？** `_daemon_service_for`（模块级函数，接口 `(config, user)` vs 实现 6 字段映射）
   偏薄但 load-bearing（RA-014 的映射契约）；`_report_daemon_status` / `_report_kernel_serve_status`
   是薄的重复推导——deletion test：删掉它们、改从 `DaemonService.state()` 投影，复杂度**收敛**
   （少一套 pid 文件路径推导 + 少一次 gateway 探测）。
3. **为可测试抽出的纯函数藏 bug？** `_stage_privileged_file`（RA-015）抽出后真正的 bug
   （sudo 失败残留 tempfile）藏在**仪式内部**，`7aa5a7202` 事后才补 finally unlink——"抽出"没有
   让 bug 更早暴露。不适用为新 story（已修复），记为教训。
4. **leaky seam？** **有，RA-028 的核心**：RA-014 宣布 DaemonService 是"唯一 daemon-lifecycle owner"
   并委托了 start/stop，但**观察路径仍绕行**：(a) `_report_daemon_status` 直读
   `Path(self.user.state_dir) / "connect.pid"` + `pid_alive`，而 DaemonService 经 sudo 读
   `/home/<user>/.lca/connect.pid`——"pid 文件在哪"是两套独立推导，home 定制时可分歧；
   直读 vs sudo 读还有特权不对称。(b) `_report_kernel_serve_status` 用 `http_ready(health_url)`
   再探一次 gateway，而 `DaemonService.state()` 已算好 gateway check——同一端点两次探测。
   (c) `heal()` 手写 `stop_daemon(); start_daemon()`，而 DaemonService 有 `restart()`（= stop+start，
   含 RA-006 的 single-instance 语义）——形状重复。(d) 全仓 `pid_alive` 的非 owner 直调只剩
   user_cli.py:207 一处（daemon.py / lobehub.py 是各自 lifecycle owner，合法）。
5. **不可测试/绕过接口测试？** `CLIProvider.status()` 的 daemon 分支今天只能靠磁盘上真实 pid
   文件测（`test_private_pid_alive_replica_is_gone` 只钉"私有 replica 已删"，没钉"改走 seam"）；
   若改从注入的 DaemonService 投影，fake DaemonService 可直接断言——"interface is the test surface"
   在此成立。

### Area B：brain/llm_turn

1. **跳模块？** "一次 LLM turn"要跳：`execute_llm_turn` → `resolve_llm_turn_mode`（policy.py）→
   `_stream_turn` / `_summarize_after_search` → `_handle_output_text_chunk`（内联 import
   capability_bindings）→ `project_llm_response`。kwargs 袋（cursor/reasoner_prompt/history）
   是约定式 seam，但那是 ADR spec section H 的显式设计（ContextVar 删除），属刻意，不立案。
2. **shallow module？** `mode.py`（18 行，一个 StrEnum）+ `policy.py`（37 行，两个函数）——薄，
   但 deletion test：删掉 → 模式判定逻辑散回 executor，**发散**，留着 earned。不立案。
3. **纯函数藏 bug？** `project_llm_response` 内的 `getattr(call, "wire_status", None) or "ok"`
   三处防御式读取——但 `NativeToolCall` 是 frozen dataclass，`wire_status/wire_reason/wire_raw_preview`
   是**具名字段**（llm.py:24-46）。类型已保证，getattr 是死防御；更糟的是它暗示"字段可能不存在"，
   而类型说"一定存在"——接口撒谎。小杠杆，不单独立案，记入本轮 learnings（诚实化候选）。
4. **leaky seam？** `_handle_output_text_chunk` 每 chunk 一次函数内 import + `current_bindings_view()`
   重解析 vocal_mode——capability_bindings 的 seam 形状可疑（per-chunk 重查），但 import 有缓存、
   语义可能是"bindings 可热变"的刻意设计。无失败证据，不立案（记入观察）。
5. **不可测试？** `_summarize_after_search` 与 `_stream_turn` 的"空响应恢复"是**两套不同形状**
   （前者重 stream 3 次 `_POST_SEARCH_COMPLETE_RETRIES`，后者转 `llm.complete` 2 次
   `_EMPTY_STREAM_COMPLETE_RETRIES`）——同一概念"LLM 空响应怎么办"两种恢复策略，分散在同一模块。
   有收敛形状（统一恢复策略），但两处语义确有差异（summarize 本就是 non-stream），speculative
   偏大，不立案；duplication 扫描亦只得 4 处语义各异的 retry loop（stream_event_manager /
   casting），不成簇。

### Area C：body dispatch（persist-before-execute）

1. **跳模块？** "journal 行上的 turn 是哪一轮"要跳：`simple_body.py:230`（读）→
   `nodes/think/llm/invoke.py:104`（另一读）→ `harness/projection/agent_state.py:70`（唯一写方）
   → `state.py:117`（`extra: dict[str, Any]` 无类型袋）。四跳才答得上来。
2. **shallow module？** 两处读方各一行 `int(state.extra.get("current_turn", 0))`——接口（魔法字符串）
   与实现一样复杂，deletion test：删掉任一处只是搬走约定，不收敛；**收敛点在给 turn 一个具名 seam**。
3. **纯函数藏 bug？** 不适用（无为此抽出的纯函数）。
4. **leaky seam？** **有，RA-029 的核心**：同一 `AgentState` 对象上，`step` 是具名字段
   （`state.step`），`turn` 却是 `extra` 袋里的魔法字符串——同一 journal 行的两个维度，
   一个 typed 一个 stringly，不对称 seam。写方（harness projection）与读方（cognition/body、
   nodes/think）跨层靠字符串约定；`.get(..., 0)` 静默默认使"projection 没跑"变成 turn=0 的
   脏行而非 fail-loud。`query.py` 里对袋内值做 `isinstance(value, int) and not isinstance(value, bool)`
   防御，说明无类型袋以前咬过人。
5. **不可测试？** "projection 缺席时 turn 回退到 0"今天只能靠"不跑 projection"测到——
   接口上无 seam 可钉；具名化后可直接断言 seam 行为。

## Runtime verification（mandatory，MockLLMAdapter，LLM_API_KEY=dummy）

沿用 `hidden_files/runtime-findings-20261007.md` 的配方（`Agent` + `ensure_default_ctx`）：

| # | 场景 | 结果 |
|---|------|------|
| A | basic run（`1+1等于几？`） | ✅ completed |
| B | tool-call run（CalcTool，首轮 tool_call 次轮作答） | ✅ completed，工具执行 |
| C | 同一 agent 两轮连续 run | ✅ completed / completed |
| D | 非收敛 run（InfiniteMock + max_steps=5） | ✅ **failed Result，无抛错**——RA-023 修复生效（`LoopObligationExceededError` 被翻译进 `result.error`，日志 `status=failed max_steps=5`）|

**新发现（运行时，非静态）：** 健康 run 的 `anomaly_detector` 噪音比 10-07 记录的更严重——
单轮 healthy run 数十条 `stalled`（sequence 只要跳号>1 就报，但 spine 多生产者/过滤本就跳号）、
`collision`（span_id 如 `lca-seq-00000007` 在关联事件间复用，并非"同一 span 开两次"）、
`cycle`（`runtime.reducer.apply` 连续出现 2 次就报，但它每事件必跑一次，consecutive_count=2
是构造性误报）。检测器的事件/span/序列模型与 spine 实际语义对不上→ RA-030。

## Duplication 副扫描

- `for attempt in range(_*_RETRIES)` 4 处：语义各异（publish 重试 / post-search 重流 /
  空流转 complete / casting），各有独立常量与 body——不成"同一仪式"簇，不立案。
- `pid_alive` 非 owner 直调：全仓只剩 user_cli.py:207 一处——反向佐证 RA-028（leak 是孤例）。
- `int(state.extra.get("current_turn", 0))` 2 处：是 RA-029 本体，不另立案。
- 本轮 duplication  story：0（quota 要求至少一个 friction 非 duplication 故事——满足，三个全是 friction）。

## Candidate table

| id | Files | Problem | Solution | Benefits（locality + leverage） | Strength |
|----|-------|---------|----------|-------------------------------|----------|
| RA-028 | `lca/infrastructure/host_runtime/providers/user_cli.py`, `lca/infrastructure/cli/services/daemon/daemon.py` | RA-014 把 DaemonService 立为 daemon-lifecycle 唯一 owner 并委托了 start/stop，但**观察路径仍绕行**：`_report_daemon_status` 直读 pid 文件（自家路径推导 `user.state_dir/connect.pid` vs DaemonService 的 sudo 读 `/home/<user>/.lca/connect.pid`——两套推导可分歧 + 特权不对称）；`_report_kernel_serve_status` 对 `DaemonService.state()` 已算好的 gateway check 再做一次 `http_ready` 探测；`heal()` 手写 stop+start 而 DaemonService 有 `restart()` | `status()` 的 daemon/gateway 部分改从 `self._daemon_service().state()` 投影（CLI-deployed 检查留 provider）；删 `_report_daemon_status`/`_report_kernel_serve_status` 私有推导与 `pid_alive` import；`heal()` 走 seam 的 restart 形状 | **locality**：daemon 状态计算只剩 lifecycle owner 手里一处；**leverage**：未来 daemon 健康信号（source drift、`next_action`）免费流进 provider status；status 可经注入的 fake DaemonService 测试（"interface is the test surface"） | **Worth exploring** |
| RA-029 | `lca/harness/projection/agent_state.py`, `lca/cognition/body/executor/simple_body.py`, `lca/nodes/think/llm/invoke.py`, `lca/contracts/models/core/state/state.py` | journal 维度 `turn` 靠魔法字符串 `"current_turn"` 在无类型 `AgentState.extra` 袋里流转：1 写方 + 2 读方，各带静默 `.get(..., 0)`；而同一对象上的兄弟维度 `state.step` 是具名字段——不对称 seam；写方改键名/漏写时 journal 静默写 turn=0 脏行 | 给 turn 具名 seam（`AgentState.current_turn` 由 projection 填充，或 contracts 层 `turn_of(state)`，对标 RA-025 的 `step_id_for`）；两读方改走 seam；静默 0 默认收进 seam 做显式决策（session-bound 缺席则 fail-loud，unbound 单测才 0） | **locality**："turn 从哪来"一处定义；**leverage**：拼写错误变类型错误；turn 传播可端到端钉测试；`extra` 袋的其余 key 不动（scope 外） | **Worth exploring** |
| RA-030 | `lca/plugins/observability/spine/derivers/anomaly.py` | 检测器的模型与 spine 实际语义对不上，健康 run 数十条误报：`_check_stalled` 见跳号就报（多生产者本就跳号）；`_check_collision` 见 span_id 重复就报（关联事件复用 span_id 是正常）；`_check_cycle` 在 `runtime.reducer.apply` 连续 2 次就报（它每事件必跑，构造性误报）。操作员被训练成无视 detector，真异常会被淹没 | 按实际语义重调模型：stalled 按生产者分别追踪序列或显式允许跳号；collision 只在"同一 span_id 并发 open 两次"时报（复用 `_check_stuck` 的 open-span 表）；cycle 区分 per-event EP 与 per-turn EP（per-EP 基线）；阈值保持公开具名 | **locality**："何为异常"的定义与现实在一处对齐；**leverage**：detector 从噪音变可信信号；"健康 run 零告警"可写成回归测试 | **Worth exploring** |

## Top recommendation

**先做 RA-028**。它是三者中最干净的 leaky seam：RA-014 已经把"谁拥有 daemon 生命周期"
的组织结论写好了（DaemonService），只是观察路径漏网——"删掉私有推导，复杂度收敛进 owner"
的 deletion test 是三者中最脆的。且它有具体的分歧 hazard（两套 pid 路径推导 + 直读/sudo
读特权不对称），不是纯美学。RA-029 第二：不对称 seam 的证据确凿（`state.step` typed vs
`turn` stringly 并排两行），修法小而明确。RA-030 第三：证据最生动（运行时亲眼所见的数十条
误报），但 detector 阈值是行为变更，需要先定"何为正常"的基线，spike 成分稍大。

## Self-grilling

### RA-028 — CLIProvider daemon 观察路径改走 DaemonService seam

- **Constraints**：`Provider.status() -> StatusReport` / `heal(CheckResult) -> bool` 契约不变；
  `user=None` 时 status 跳过 daemon 检查的行为不变；`test_private_pid_alive_replica_is_gone` 与
  `test_kernel_serve_status_converges_on_http_ready` 的 pin 语义不违背（后者钉的是"不用 bespoke
  curl 探针"，改走 `state()` 是更进一步的收敛，不开倒车）；RA-014 的"lifecycle owner"结论不重审。
- **Dependencies**：上游 `DaemonService.state() -> ServiceState`（checks 含 daemon/gateway/cli/cli_sync，
  读 pid 经 sudo）；下游 `CLIProvider.status()` 的调用方（HostEnvironment / doctor 链）——seam 移动后
  它们拿到的 StatusReport 条目名可能变化（"daemon"/"kernel_serve" → state 的 check 名），需同步。
  `heal` 的 bool 返回要从 ServiceState 映射（`is_running`）。
- **Shape of the deepened module**：`status()` 内 `if self.user:` 分支改调
  `self._daemon_service().state()`，把其 `daemon`/`gateway` check 投影成 StatusReport 条目；
  `CLI-deployed` 检查保留（provider 属主）；`heal()` 调 `self._daemon_service().restart()` 并映射
  bool。seam 后面是 pid 文件/sudo/探测细节，前面是 Provider 契约。
- **Test survival**：现有 `test_cli_provider_daemon_delegation.py` 全绿（start/stop 委托测试不受影响）；
  新测试：注入 fake DaemonService（`state()` 返回 canned ServiceState），磁盘无 pid 文件时
  `status()` 仍正确报告——这是今天写不出来的测试（testability gap 的钉子）。
- **Deletion test verdict**：**concentrates**。删掉 `_report_daemon_status`/`_report_kernel_serve_status`
  → daemon 状态计算只剩 DaemonService.state() 一处；留着 → 两套推导永久并存。

### RA-029 — turn 具名 seam

- **Constraints**：journal 行的 `(turn, step)` 二元维度语义不变；`state.extra` 袋不动（其余 key
  各有 owner，scope 外）；projection 缺席的 unbound 单测仍要能跑（0 默认保留，但收进 seam 显式化）。
- **Dependencies**：写方 `harness/projection/agent_state.py:70`（`session.created.v1` /
  `turn.started.v1` 投影）；读方 `simple_body.py:230`、`invoke.py:104`；`AgentState` 定义
  （`contracts/models/core/state/state.py`）。若选 `AgentState.current_turn` 字段方案，
  注意 `AgentState` 可能是 frozen dataclass——字段加法 vs accessor 二选一 spike 定。
- **Shape of the deepened module**：二选一（spike 定）：(a) `AgentState` 加 `current_turn: int | None`
  可空字段，projection 填充，读方 `state.current_turn if ... else <seam默认>`；
  (b) contracts 层 `turn_of(state) -> int` accessor（对标 RA-025 `step_id_for`），内部封装
  袋读 + 默认策略。seam 后面是"projection 设没设"的知识，前面是两个读方。
- **Test survival**：现有 persist/dispatch/session 测试全绿；新测试：projection 跑完后
  `dispatch_tool_calls` 的 journal 行 turn 正确（端到端钉传播链）；另钉"袋缺席时 seam 的显式默认"。
- **Deletion test verdict**：**concentrates**。"turn 从哪来"从 3 处魔法字符串收进 1 个 seam。

### RA-030 — anomaly detector 模型对齐 spine 语义

- **Constraints**：8 个 detector 的 kind 名不变（下游可能按 kind 订阅）；阈值保持公开具名
  （design §7.5.4.1）；`on_event` 的 fail-contained 语义（FD-2）不动；`bind_anomaly_sink` 不动。
- **Dependencies**：上游 spine 事件流（EventRecord 的 sequence/span_id/execution_point 产生方）——
  改模型前先确认"跳号正常""span_id 复用正常"是 spine 的**契约**而非巧合（读 spine 的 span/sequence
  产生代码钉住）；下游 anomaly sink 消费者（日志/订阅方）——误报减少是纯收益。
- **Shape of the deepened module**：`_check_stalled`：按 `(producer, sequence)` 分别追踪或显式
  gap 容忍；`_check_collision`：复用 `_open_spans` 表，只在 span_id 已 open 未 close 时重复出现才报；
  `_check_cycle`：EP 分两类（per-event 如 reducer.apply / per-turn），per-event 类要求更高
  consecutive_count 或直接豁免。seam 后面是"何为正常"的基线，前面是 8 个 check 的统一形状。
- **Test survival**：现有 anomaly deriver 测试全绿；新测试：用真实 healthy run 的事件流形状
  （跳号序列、复用 span_id、per-event EP）喂 detector，断言零误报——这是今天写不出来的测试。
- **Deletion test verdict**：**concentrates**。"何为异常"的定义从操作员的脑子里收进 detector。

## 丢弃（有证据）

- `NativeToolCall` 映射里的三处 `getattr(..., "wire_status", None) or "ok"` 死防御：类型是 frozen
  dataclass 具名字段，getattr 永不 fallback——接口诚实化小瑕疵，单函数内、无杠杆，不开 story
  （记入 learnings：以后 friction walk 见到"类型保证 vs 防御式读取"矛盾可直接按诚实化修）。
- `_handle_output_text_chunk` 的函数内 import + per-chunk `current_bindings_view()` 重查：
  可能是"bindings 可热变"的刻意设计，无失败证据，不立案，记观察。
- `_summarize_after_search` vs `_stream_turn` 的两套空响应恢复（重 stream 3 次 vs 转 complete 2 次）：
  语义确有差异（summarize 本是 non-stream），收敛形状 speculative，不立案。
- retry loop 4 处（stream_event_manager / executor ×2 / casting）：各有独立常量与 body，
  不是同一仪式，不成簇。
- `ProactiveScheduler.js` state dict（patterns 已有）：本轮未新增证据，维持 speculative。
- `ModelVisibleHook.before_publish`/`after_dispatch` 占位（patterns 已有）：ADR-0185 PR-3 未决，维持。
- `run(None)` TypeError / `NativeToolCall.arguments` 传 str 晦涩报错（10-07 P2）：defer 给
  iter-quality lane，本轮未立案（patterns 已有）。
- `CLIProvider.provision()` 内 `self.run` 与裸 `subprocess.run` 混用：同一方法的两处 tsc 调用
  走了不同进程 seam——真不一致，但属单方法内 hygiene，杠杆不足以单独立 story；RA-028 优化轮可顺手收敛。
- Round 7 评估曾以"RA-014/015 已做"整体避开 user_cli.py：本轮 RA-028 只取**观察路径**
  （status/heal），与 RA-014/015 的 start/stop lifecycle scope 正交，不属重审——此区分已在本
  assessment 顶部 Scope 注记，避免后人误判为重复立案。
