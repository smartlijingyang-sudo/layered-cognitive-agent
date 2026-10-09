# Raphy Round 16 Assessment — raphy/arch-20261009-2045（基线 7ce6becc0）

评估时间：2026-10-09 20:45–21:05 CST。新鲜会话，零记忆，全部状态来自仓库文件。
上一轮 raphy/arch-20261009-1643 已合 main（merge 07221f0f4），RA-001~RA-100 全 done（无 dropped）。
禁区遵守：未读未碰 `lca/infrastructure/computer/guest/preamble.py` 的 emit/resolve 路径映射；
未碰主工作树脏分支 `fix/grant-absence-hitl-separation` 的 9 个文件
（`lca/contracts/runtime/trust.py`、`lca/nodes/act/authorize/authorize.py`、
`lca/nodes/intervene/approve_gate.py`、`lca/application/runtime/default_facade.py`、
`bundles/act/act_subgraph.yaml`、`bundles/outer/phase_main.yaml` + 3 个测试文件）——
有人正在其上工作。

## Phase 1 — Explore

### 1.1 Scope via YAGNI

`git log --oneline` 回溯 40 commits：热点区 = raphy/ 自身（mechanical）、以及本次 assess
锁定的三区（上一轮已收敛区之外的新领地）：

- `lca/framework/graph/interpreter.py`（596 行；RA-023 只在 agent 层翻译了它的
  LoopObligationExceededError，kernel 本体无人走过）
- `lca/plugins/observability/spine/derivers/anomaly.py`（440 行；RA-030 做过
  per-run scoping + per-EP baseline，但 10-07 运行时 P2.3 仍报正常 run 误报）
- `lca/framework/graph/port_reader.py`（123 行）+ `port_registry.py`（175 行）
  + `predicate_evaluator.py`（106 行）+ `traversal.py`（138 行）+ `loop_budget.py`（48 行）

CONTEXT.md 与相关 ADR（ADR-0217 §3.3.3、ADR-0219 §5、ADR-0225、ADR-0240/0241）已读。

### 1.2 Organic friction walk（5 问必答，精读非 grep）

**Area A — `lca/framework/graph/interpreter.py`（全读 596 行）+ `loop_budget.py` + `traversal.py`（全读）**

1. 理解一个概念跨多少小模块？visit 循环本身是单方法，职责清晰（visit→execute→
   merge→edge→advance）。刺痛的是**三个 ~20 行的 visit-end 仪式块**：
   routing-terminate break（`_visit_end_of` + `latency.record` + `VisitRecord` +
   `recorder.record` + `visits.append` + `facts.extend` + `terminal_node = node.id`）、
   terminal_predicate break（同仪式 + 前置 `traversal.terminal_reason`）、
   循环末尾正常路径（同仪式，dispatch=`dispatch.kind`）。三处逐行对照，差异仅
   dispatch kind 与 terminal_reason。→ 候选 RA-102。
2. 浅模块？`_resolve_depth`（8 行，`getattr(outer_state, "graph_depth", None)`
   嗅探）——interface（AgentState-shaped outer state）与实现同构，但它是有意为之的
   宽容读取（kernel 不硬依赖 AgentState 类型），deletion test 不通过，不碰。
   `_terminate_routing` 浓缩了"只有本 visit 的 routing 信号能停机"的关键不变式，
   earns existence。
3. 为 testability 抽出的纯函数？`_str_keyed`（PortName NewType 擦除显式化）、
   `_terminal_port_values`（declared_inputs 为空时回退全快照）——locality 好，
   注释讲清了"为什么"。
4. Leaky seam？`port_registry_seed` 的 Mapping/Callable/None 三态是**已声明**的
   canonical seam（docstring 逐条讲），不算泄漏。`_port_registry_seed_from_runtime_plane`
   的 `except Exception: return seed` 是有意的降级（测试注入路径），注释说明了，
   不算泄漏。
5. 未测试/穿透 interface 测试？三个仪式块的行为由 interpreter scenario 测试整体
   pin（visit records / observations），细粒度无缺口。`LoopObligationExceededError`
   的 raise 点有 RA-023 的 pin。

**Area B — `lca/plugins/observability/spine/derivers/anomaly.py`（全读 440 行）+
`lca/plugins/session/spine_anomaly/spine_anomaly.py`（全读 120 行）**

1. 跨模块？deriver（8 个 `_check_*`）+ session observer（`_SpineAnomalyObserver`
   做 SessionEvent→EventRecord 投影）+ `bind_anomaly_sink` 注入点——职责分层清晰。
2. 浅模块？**有**：`_recent_points: deque[str] = deque(maxlen=self.CYCLE_WINDOW)`。
   RA-030 把 cycle 检测从"100-event window 内重复"改写成 consecutive-count +
   per-EP baseline，但 deque 留了下来：每 event `append`（line 189），唯一消费是
   line 196 的 `point in self._recent_points`——point 刚 append 进去，**恒为 True**。
   `CYCLE_WINDOW` 类属性、`deque` import  plumbing、`_check_cycle` docstring
   （"Trip when the same execution_point repeats within CYCLE_WINDOW"）都在讲述
   一种实现已不再采用的语义。deletion test：删掉它，复杂度**集中**到
   consecutive-count 这一处真实语义——Concentrates。→ 候选 RA-103。
3. 纯函数抽取？8 个 `_check_*` 都是纯判定（输入 EventRecord → bool），locality 正确。
   `_check_stuck` 与 `_check_collision` 共享 `_open_spans` 表，注释讲清了顺序依赖
   （collision 必须在 stuck 之前跑），这是状态机该待在一起的例子。
4. Leaky seam？`_make_anomaly_payload` 的 evidence_hash 用 canonical_digest——
   观测面与证据面分离得干净。`bind_anomaly_sink` 的 Any 类型是 profile boot 未定型
   的有意宽容，注释说了"once it exists"，不算泄漏。
5. 测试面？`tests/lca_plugins/observability/spine/test_anomaly_detector.py` +
   `test_cycle_detector_fingerprint.py` pin 了 8 个 detector 的 trip 行为。
   删 deque 不改变任何 trip 结果（恒真条件），测试即 pin。

**Area C — `lca/framework/graph/port_reader.py`（全读）+ `port_registry.py`（全读）+
`predicate_evaluator.py`（全读）**

1. 跨模块？`select_edge` → `reader_factory` → `PortReader.read` → `registry.read`：
   调用链短，D4 后类型清晰。
2. 浅模块？**`PortRegistry.has_port` 与 `PortReader.port_has_value` 是"同一个概念
   的两条路"**：registry 已声明 `has_port(PortName) -> bool`（O(1) 成员检查，
   close_out_adapter 在用，有显式测试 pin `test_uses_has_port_not_keyerror`）；
   但 `PortReader.port_has_value(name: str)` 绕开它，走
   `name in self.registry.snapshot()`——**每次调用复制整个 port store**
   （`snapshot()` 返回 `dict(self._ports)`）。`predicate_evaluator` 对每条边的
   PortSet/PortNotSet 谓词调 `port_has_value`（3 个调用点）；循环重的图
   （act→think re-ask ×24 轮）每轮每条边都在做全量复制。
   "The interface is the test surface"：registry 已经把"port 是否存在"声明成
   seam 了，reader 却不用。→ 候选 RA-101。
3. 纯函数抽取？`_resolve_field` 里 BaseModel / dataclass 两分支的
   "field 是否存在"检查是机械对称（只差取字段名的方式）——但合并它属于
   hygiene 级别的小收敛，可在 RA-101 的 AC 里顺手提，不单独成 story。
   4 个 `raise UnknownFieldError` 的 `"edge from {source!r} reads port {name!r}"`
   前缀重复 ×4（+1 个 UnsetPortError 同前缀）——同上，hygiene，不单独立项。
4. Leaky seam？`port_has_value` 拿 `snapshot()` 做成员检查就是泄漏本尊：
   它把 registry 的"读一致性视图"语义（copy）用在了只需要"存在性"的场景。
5. 测试面？`has_port` 有 pin；`port_has_value` 的行为（set/未写/被清空）由
   predicate evaluator 测试覆盖。改完后三者语义必须一致：
   注意 `read` 把 value=None（被清空）也视为 Unset——`has_port` 对 None 值
   返回 True（key 存在），`port_has_value` 现状（snapshot 成员检查）同样
   返回 True——**两者一致**，改法安全。

### 1.3 Runtime verification（实跑，LLM_API_KEY=<redacted>

基线 7ce6becc0，MockLLMAdapter，四项核心流程：

- (a) 基础 run → COMPLETED ✅
- (b) 带 tool call 的 run（首轮 tool_call、次轮文本）→ COMPLETED ✅
- (c) 同一 agent 两次顺序 run → completed/completed ✅
- (d) 永不收敛 run（每轮都 tool_call，max_steps=5）→ 返回 failed Result，
  **未抛异常** ✅（RA-023 的 pin 依然有效；loop_budget.clamp_loop_bounds 生效）

本轮无新的运行时 P0/P1。

### 1.4 Duplication scan（次要）

- interpreter.py 三处 visit-end 仪式块 → RA-102。
- port_reader `_resolve_field` 的 BaseModel/dataclass 双分支、5 处 error 前缀
  重复——hygiene 级，不单独立项。
- 其余重复均为已收敛（Observation 构造器、run_envelope、registry 白名单）。

---

## Phase 2 — Self-grilling

### RA-101（Strong）

- **Constraints**：`PortReader.port_has_value(name: str)` 签名不变（predicate_evaluator
  3 个调用点传 str）；`PortRegistry.snapshot()` 语义不变（interpreter 的
  `_terminal_port_values` / `_str_keyed` 观测面仍需 copy）；`has_port` 接受
  `PortName`（NewType(str)），运行时 str 直通，类型检查器侧做 `PortName(name)` 转换。
- **Dependencies**：调用方 = `predicate_evaluator.py` 3 处；被绕过的 seam =
  `PortRegistry.has_port`（close_out_adapter 已在用，有 pin）。
- **Shape**：`port_has_value` 本体改成 `return self.registry.has_port(PortName(name))`；
  `PortName` 已在模块 import（`from ...ports import PortName`）。
- **Test survival**：`tests/cognition/wire/test_close_out_adapter.py::test_uses_has_port_not_keyerror`
 （has_port 语义 pin）；predicate evaluator 的 PortSet/PortNotSet 测试；
  新增：port_has_value 对"从未写 / 已写 / 被清空（None 值）"三态与 has_port 一致。
- **Deletion test**："port 是否存在"只剩 registry 一处知识——Concentrates。✅

### RA-102（Worth exploring）

- **Constraints**：visit 结束的 6 步仪式顺序不变（observe → latency.record →
  VisitRecord → recorder.record → visits.append → facts.extend → terminal_node）；
  terminal_predicate 路径的 `traversal.terminal = True` + `terminal_reason` 赋值
  保留在 helper 调用之前；`_classify(edge, output)` 的 dispatch 判定不变。
- **Dependencies**：只有 `PlanInterpreter.run` 内部三处调用；helper 全私有。
- **Shape**：`def _record_visit_end(self, *, node, plan_id, traversal, depth, visit_started, inputs, outputs, dispatch_kind) -> VisitRecord`——
  内部做 observer.observe(_visit_end_of(...dispatch=dispatch_kind)) + latency +
  record/append/extend，返回 VisitRecord；`terminal_node = node.id` 留在调用方
  （它是循环局部变量赋值，不是仪式）。
- **Test survival**：interpreter scenario 测试（visit records / GraphObservation
  序列）是行为 pin，改后必须一致。
- **Deletion test**："一次 visit 结束意味着什么"成为单一命名 seam——Concentrates。✅

### RA-103（Worth exploring）

- **Constraints**：8 个 `_check_*` 方法一个不少（I16 build-time 反射检查）；
  per-EP baselines（CYCLE_BASELINES）与 CYCLE_BASELINE_DEFAULT 不动；
  trip 语义零变更（删的是恒真条件）。
- **Dependencies**：`_recent_points` 无外部消费者（grep 确认仅本模块 3 处）；
  `CYCLE_WINDOW` 无外部引用。
- **Shape**：删 `self._recent_points` + `CYCLE_WINDOW` 类属性 + line 196 的
  `and point in self._recent_points`；`_check_cycle` docstring 与 `__init__`
  注释改写成 consecutive-count 语义；`deque` import 若无他用则删。
- **Test survival**：test_anomaly_detector.py + test_cycle_detector_fingerprint.py
  全绿即行为 pin（trip 结果与删前一致）。
- **Deletion test**：删掉 ghost state，detector 的状态只讲 consecutive-count
  一个故事——Concentrates。✅

---

## Phase 3 — Present and record

| ID | Files | Problem | Solution | Benefits | Strength |
|----|-------|---------|----------|----------|----------|
| RA-101 | `lca/framework/graph/port_reader.py`（`port_has_value`）, `lca/framework/graph/port_registry.py`（`has_port` 已声明） | `PortReader.port_has_value` 绕开 registry 已声明的 `has_port` seam，用 `name in registry.snapshot()` 做存在性检查——每次调用复制整个 port store；`predicate_evaluator` 每条边谓词求值调它（3 处），循环重的图每轮每条边都在全量复制。 | 委托给 `registry.has_port(PortName(name))`，签名不变；`snapshot()` 语义不动。 | locality："port 是否存在"的知识回到 registry 一处；leverage：所有未来的边谓词求值免费拿到 O(1) 成员检查；interface 即 test surface：已声明的 seam 终于被自己人用。 | Strong |
| RA-102 | `lca/framework/graph/interpreter.py` | `run()` 内三处 ~20 行 visit-end 仪式块（routing-terminate break / terminal_predicate break / 循环末尾）逐行重复，仅 dispatch kind 与 terminal_reason 不同。 | 抽私有 `_record_visit_end(...)` helper 收敛 6 步仪式；terminal_reason 赋值与 `terminal_node = node.id` 留在调用方。 | locality："一次 visit 结束"成为单一命名 seam；leverage：下次给 visit-end 加观测字段只改一处。 | Worth exploring |
| RA-103 | `lca/plugins/observability/spine/derivers/anomaly.py` | RA-030 把 cycle 检测改写成 consecutive-count + per-EP baseline 后，`_recent_points` deque（CYCLE_WINDOW=100 语义）成了 ghost state：每 event append，唯一消费 `point in self._recent_points` 恒为 True；类属性、注释、docstring 还在讲已被废弃的 window 语义。 | 删 deque + `CYCLE_WINDOW` + 恒真条件；docstring/注释改写成 consecutive-count 语义；8 个 `_check_*` 与 baselines 不动。 | locality：detector 状态只讲一个故事；leverage：以后调阈值不再被 ghost state 误导。 | Worth exploring |

**Top recommendation：RA-101**。它是本轮唯一的 Strong：已声明的 seam 被自己人
绕开（"the interface is the test surface" 的反例），且有真实的 per-edge 成本
（每条边谓词求值 × 全量复制）。Runner-up：RA-103（ghost state 是读代码的人
的税，删它零行为变更）。

依赖顺序：三者相互独立；RA-101 先（seam 类问题优先）。

**Diversity quota**：3 个 stories 中 duplication 类 1 个（RA-102），其余 2 个来自
friction walk（RA-101 leaky seam、RA-103 vestigial state）。满足"至少一个来自
friction walk"。

---

Assessment complete: 3 stories written, top is RA-101.
