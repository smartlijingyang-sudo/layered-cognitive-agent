# ADR-0184 — 事件生命周期受管理投递：统一入口、阶段可查、丢失可定位

## 状态

Proposed（2026-09-04 起草）。实施按 §5 PR 序列推进；全部验收标准见 §5 各 PR
与 §6 最终验证协议。

## 0. 决策摘要

`EventBus.publish` 当前只管理发送资格（鉴权 + schema），不管理送达事实。
三个被允许的静默构成投递黑洞：零挂载 sink 时 `_dispatch_sinks` 直接返回
（`lca_kernel/events/bus.py` `_dispatch_sinks`）；零订阅者时 `_fanout` 空转；
生产 boot 只调 `register_pipeline_once`（仅装 hooks，不挂 sink / 不订阅，
`lca/harness/profile/boot.py` `_register_event_pipeline`），已迁总线的
publisher 事件无任何落盘与消费路径。

后果（证据 `traces/runs/run_a96beb4f1c4c`，2026-09-03）：
`brain.think.start` 等认知族事件从账本消失 → `step_tree_accumulator` 隐式
开窗永不触发 → `journal.json` `steps=[]` → doctor `H-seg`
（`sum(steps.segments)=0 != totals.segments=3`）；09-03 21:53 起每个 run 复现。

本 ADR 把事件生命周期定义为四段显式阶段，每段产出记录在案的结果；新增三条
不变量（装配契约、发送必落、写入实现单一）；给出 5 个实施 PR + 1 个终态
follow-up，每个 PR 自带测试与验收命令，序列无悬空依赖。

## 1. 生命周期四段

```text
send(payload, producer)
 ├─ S1 ACCEPT    鉴权（Category 闭集 + publisher 白名单）+ schema 校验
 ├─ S2 RECORD    stamp：seq / epoch / trace_id / causality（SpineContext 分配）
 ├─ S3 PERSIST   sink 落盘，FD-1 fail-fast
 └─ S4 DELIVER   subscriber 派发，FD-2 contained
```

四段与 `publish` 现行实现一一对应（`can_publish` / pre_dispatch hooks /
`_dispatch_sinks` / `_fanout`），不新开平行机制。「受管理」= 每段的结果是
机制的一等公民：阶段结果要么可见成功，要么 fail-loud；「通过但什么都没发生」
不是合法状态。

## 2. 关键决策

### D1. 投递回执：EventRef 携带送达状态

`EventRef`（`lca_kernel/events/bus.py`）新增两个字段：

- `persisted: bool` —— S3 是否有 ≥1 个 sink 实际写入成功；
- `subscriber_count: int` —— S4 实际派发的订阅者数量。

类型：`dataclass(frozen=True)`，默认值禁止（构造方必填）。失败语义：字段
只反映事实，不抛错；抛错由 I2 负责。时序：`publish` 返回前填充完毕。
所有权：机制层唯一写方；发送方只读。外部后果：发送方可在调用点立即判断
事件停在哪个阶段。

### D2. 机制投递计数器

`EventBus` 实例持进程内计数器，按 category 累计四值：
`published / persisted / delivered / dropped`。`dropped` 定义：
`persisted=False` 或 `delivered=0` 且该 category 在注册表中声明了
`subscribers`。实现为内存 `defaultdict`，不落盘；经 §3.10 既有自观察缝
（`subscribe_self_observation`，`event.bus.dispatch.*`）对外暴露，并新增
`lca-ops events-delivery [--category <cat>]` 诊断命令打印快照。
「在哪个节点丢的」从考古变成查询。

### D3. I1 装配契约：声明 = 接线

鉴权矩阵（`lca_kernel/events/config/**/*.yaml`）是接线合同，不只是许可表。
boot 装配完成后断言（失败 = 进程退出，错误信息指向缺失的 category / sink）：

1. Pipeline 声明的每个 sink 已 `mount_sink`；
2. 注册表中声明 `subscribers` 的每个 category 有 ≥1 个活跃订阅；
3. 任一条件不满足 → `EventPipelineWiringError`，boot 失败。

校验点在 `lca/harness/profile/pipeline_loader.py`（`apply_pipeline` 返回后），
由架构测试守护。「半装配」状态（只装 hooks）不再是合法运行态。

### D4. I2 发送必落：零落盘 = 可见错误

对注册表标记持久的 category（`plane: OBSERVABILITY` 的 spine 全族），
`_dispatch_sinks` 发现 `self._sinks` 为空时：

- 生产默认：`EventNoSinkError` 上抛（fail-loud）；
- 迁移窗口允许降级为 `dropped` 计数 + `structlog` error，降级开关是
  `EventBus.configure_delivery_policy(strict=False)`，带 COMPAT：
  `delete-when: PR-C 合并且 live-run 验证通过，tracking: ADR-0184 PR-C`。

非持久 category（业务诊断类）零 sink 只计数不抛错。

### D5. I3 写入实现单一

全仓写 `<run_id>.spine.jsonl` 的物理实现唯一：`spine_port_append`
（`lca/infrastructure/observability/loop_cursor/_spine_port.py`）的落盘段。
总线侧 `SpineSink` backend（`lca_kernel/events/sinks/spine_sink.py`）持有
与该文件绑定的同一写实例（共享 `SpineContext` seq / hash-chain 分配），
两条入口路径（总线 `publish` / 老链 `write_port_append`）每个事件物理写入
恰好一次。双写者不是时序问题，是结构上不可能。

终态方向：全部写入经 `send()`，`write_port_append` 调用方清零；该步是
follow-up（§5 PR-F），启动条件为 PR-D/E 验收通过。

### D6. 消费侧契约：显式 step 边界信号

`journal.json` step 派生（`lca/infrastructure/observability/spine/derivers/
step_tree_accumulator.py`）的开窗信号恢复显式契约：

- `writable.step.start` / `writable.step.end` 为 step 边界契约 EP。发射点：
  `cursor.record_request_header`（start，与 `llm.request.header` 同源同步）、
  `cursor.advance("stop")` 与 `cursor.close`（end）。发射函数与 yaml 授权
  已存在（`lca/plugins/events/publishers/spine_reflector_writable/plugin.py`、
  `lca_kernel/events/config/observability/spine.yaml`），缺的是调用方。
- `brain.think.start` 隐式开窗（ADR-0176 D1 §1(2)）保留为兜底；
  `JournalStep.extra` 记录 `window_signal`（`explicit` / `implicit`），
  step 的开窗来源可查。

### D7. 回归锁：投递可达性

场景级测试（`tests/scenarios/test_event_delivery_e2e.py`）：真 profile
boot → 最小 run（stub LLM）→ 断言：

1. `journal.json` `steps ≥ 1`；
2. doctor `broken_hop is None`（H-seg 干净）；
3. 账本含 `brain.think.start` + `llm.request.header` + `writable.step.start`；
4. 计数器 `dropped == 0`。

该测试先于装配切换（PR-C）落地：它是迁移的判定标准，不是事后补丁。

## 3. 与既有决策的关系

- ADR-0183：本 ADR 补齐其投递语义。0183 状态区「`register_pipeline` 不挂
  sink（迁移期安全，等 21 publisher 全迁后切 `apply_pipeline`）」的迁移期
  论证由 D3 + D4 接管：切换不再靠时序默契，靠 I1/I2 机制强制。
- ADR-0181 D2：hash chain 归 sink 的边界不变；D5 在该边界内要求写实例唯一。
- ADR-0176 D1：step 派生闭集不变；D6 只补显式信号与来源记录。
- ADR-0182：yaml 白名单收敛形态不变；D3 在其上增加装配断言。

不新开平行机制：全部扩展点（hooks、自观察缝、`EventRef`、鉴权矩阵、
`apply_pipeline`）均为既有缝。

## 4. 失败语义汇总

| 场景 | 行为 |
|---|---|
| 未授权 publish / subscribe | 抛错（现状保持） |
| schema 校验失败 | 抛错（现状保持） |
| 持久 category + 零 sink | `EventNoSinkError`（迁移窗口内降级为 `dropped` 计数 + error 日志） |
| sink 写入抛错 | FD-1 fail-fast 上抛（现状保持） |
| subscriber 抛错 | FD-2 contained（现状保持），计入计数器 |
| 声明有订阅者但实际零订阅 | boot 失败（I1） |
| 声明 sink 未挂载 | boot 失败（I1） |

## 5. PR 切分

序列：`A → B → C → D → E`，线性依赖；每 PR 合并时全仓绿（见 §6.1）。
不允许跳序：C 依赖 A 的降级开关，D/E 依赖 C 的装配。每 PR 一个提交主题。

### PR-A 投递回执 + 计数器 + I2

- **范围**：`EventRef` 加 `persisted` / `subscriber_count`；`EventBus`
  计数器与 `configure_delivery_policy(strict=...)`；`_dispatch_sinks` 零落盘
  策略；`events-delivery` 诊断命令（`lca/infrastructure/cli/`，注册进
  `lca-ops` 命令矩阵——同步 `docs/debug/run-debug-guide.md`，该文件受
  `scripts/check_run_debug_sync.py` CI 门禁）。
- **触点**：`lca_kernel/events/bus.py`、`lca_kernel/events/errors.py`、
  `lca/infrastructure/cli/commands/`、`scripts/lca-ops`。
- **依赖**：无。可立即开始。
- **测试**：`tests/lca_kernel/events/test_bus_delivery_receipt.py`
  （回执字段、计数器四值、零落盘抛错 / 降级两态、诊断命令输出）。
- **验收**：`uv run pytest tests/lca_kernel/events/ -q` 全绿；
  `./scripts/lca-ops events-delivery` 可执行。
- **迁移窗口策略**：本 PR 合并时 `strict` 默认 **False**（现状有大量事件
  走老链，总线零 sink 是过渡态事实）；PR-C 翻转为 True。
  翻转是本 ADR 的显式步骤，不是待办。

### PR-B 回归锁（先于装配切换）

- **范围**：`tests/scenarios/test_event_delivery_e2e.py`（D7 四条断言）。
  若现有场景夹具不支持真 profile + stub LLM 组合，本 PR 一并补夹具；
  夹具形态以 `tests/` 既有分层（单元 / 契约 / 架构 / 集成 / 场景）为准。
- **依赖**：PR-A（断言 4 用计数器）。
- **测试**：本测试在 PR-C 前允许以 `pytest.xfail(strict=True,
  reason="ADR-0184 PR-C 装配切换前投递黑洞")` 标记——锁先挂上，C 落地时
  翻正；翻正是 C 的验收动作之一。
- **验收**：`uv run pytest tests/scenarios/test_event_delivery_e2e.py -q`
  以声明状态通过（xfail 或 pass）。

### PR-C boot 切 apply_pipeline + I1 装配校验 + 共享写实例

- **范围**：`boot._register_event_pipeline` 改调 `apply_pipeline`；
  `pipeline_loader` 增装配断言（D3）+ `EventPipelineWiringError`；
  总线 `SpineSink` backend 与运行态 FileSink 共享写实例（D5）；
  `configure_delivery_policy(strict=True)` 翻转；PR-B 的 xfail 翻正；
  删除 `register_pipeline_once` 生产调用（函数保留给测试，带 COMPAT：
  `delete-when: rg "register_pipeline_once" lca/ 仅剩测试与
  pipeline_loader 定义，tracking: ADR-0184 PR-C`）。
- **依赖**：A、B。
- **测试**：`tests/architecture/test_event_bus_invariants.py` 增
  I1 装配断言用例；`tests/harness/test_boot_pipeline_wiring.py`
  （缺订阅 / 缺 sink 两种 boot 失败）；PR-B 场景测试翻正。
- **验收**：§6.2 live-run 协议通过；`strict=True` 下无 `EventNoSinkError`。

### PR-D cursor 迁总线入口

- **范围**：`spine.yaml` 为 `LoopCursorPlugin`
  （`lca/plugins/events/publishers/spine_loop_cursor/plugin.py`）登记全部
  cursor EP category 的 publisher 授权；cursor `_append` 切
  `LoopCursorPlugin.send`；`write_port_append` 的调用方仅剩共享写实例内部。
- **依赖**：C。
- **测试**：`tests/plugins/events/publishers/test_spine_loop_cursor.py`
  （鉴权 + 载荷映射）；既有 `tests/observability/` cursor 套件全绿。
- **验收**：对同一输入，切换前后账本 EP 序列与 `journal.json` 内容一致
  （快照比对测试）；`writable.step.start` 之外的全部 cursor EP 经总线落盘。

### PR-E 恢复 writable.step.* 契约 + 开窗来源记录

- **范围**：`cursor.record_request_header` 发 `writable.step.start`、
  `cursor.advance("stop")` / `close` 发 `writable.step.end`（经 PR-D 的
  总线路径）；`StepCoordinator.begin_step` / `end_step` docstring 与
  `_block_ep_write` COMPAT 块同步更新（`lca/infrastructure/observability/
  writable_matrix/coordinator.py`，tracking: ADR-0169-task-25 不变，条件
  文本修正）；`JournalStep.extra.window_signal` 记录。
- **依赖**：D。
- **测试**：accumulator 单测（显式开窗 + `window_signal` 两值）；
  PR-B 场景测试断言 3 扩展为显式信号；
  `./scripts/lca-ops audit-plugin-shape` 无新违例。
- **验收**：连续 3 个 `lca-ops runs create` 的 run 全部 `steps ≥ 1` 且
  `window_signal=explicit`；doctor 无 H-seg。
- **delete-when**（`brain.think.start` 隐式兜底的删除条件）：
  连续 14 天生产 run `window_signal` 全为 `explicit`，
  tracking: ADR-0184 PR-E。

### PR-F（follow-up，启动条件：E 验收通过）

EmitPipeline（`lca/plugins/observability/spine/emit_pipeline.py`，
`phase_graph` 族）迁总线 + `write_port_append` 调用方清零。本 ADR 只锁
启动条件与终态方向；范围、测试与验收在该 PR 启动时按同一模板展开。

## 6. 验证协议

### 6.1 每 PR 门禁（写进每个提交说明）

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
```

动 `lca_kernel/events/` 或公共签名时追加：

```sh
uv run pytest tests/architecture/ tests/lca_kernel/ -q
./scripts/lca-ops notes-check
```

### 6.2 最终 live-run 协议（PR-E 验收执行一次，命令全部实跑）

```sh
./scripts/lca-ops kernel-restart
RUN_ID=$(./scripts/lca-ops runs create --user-text "ping" | jq -r .run_id)
./scripts/lca-ops debug-run "$RUN_ID"                 # [1/8] 无 broken_hop
jq '.steps | length' traces/runs/"$RUN_ID"/journal.json        # ≥ 1
jq '.steps[0].extra.window_signal' traces/runs/"$RUN_ID"/journal.json  # "explicit"
grep -c 'writable.step.start' traces/runs/"$RUN_ID"/*.spine.jsonl     # ≥ 1
./scripts/lca-ops events-delivery                     # dropped == 0
./scripts/lca-ops explain "$RUN_ID"                   # 无失败终态
```

六条全部满足 = 最终效果达成：统一入口、阶段可查、丢失可定位、journal step
恢复、回归锁在位。

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 共享写实例的 seq / chain 交错 | `SpineContext` 是 seq / epoch / hash 唯一分配者；两入口共用同一分配器，单调性由机制保证。PR-C 含交错场景测试（总线与老链交替写 100 事件，断言 chain 校验通过） |
| I1 使 boot 在配置不全的 profile 下失败 | 错误信息列出全部缺失项；诊断指针进 `docs/debug/run-debug-guide.md`（同 PR 过 `check_run_debug_sync.py`） |
| 计数器内存增长 | 按 category 聚合，上限 = Category 闭集大小 × 4；无按事件保留 |
| 回滚 | PR-A 纯加法可单独回滚；B–E 按序回滚（每 PR 一个提交）。回滚 = 投递黑洞复现，因此回滚仅作为事故止血，不作为常态选项 |

## 8. 词表

- **投递黑洞**：`publish` 返回成功但事件未落盘且未派发的状态。本 ADR 的
  消除对象。
- **装配契约**：鉴权矩阵声明与运行时接线的一致性断言（D3 / I1）。
- **投递回执**：`EventRef.persisted` + `subscriber_count`（D1）。
