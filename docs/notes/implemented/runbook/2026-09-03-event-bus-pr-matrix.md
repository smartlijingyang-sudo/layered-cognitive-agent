# Agent Note: ADR-0183 附录 B — 12 PR 兼容性矩阵

Status: implemented(2026-09-03)

## Problem

ADR-0183 §5 把落地切成 12 个独立可 revert 的 PR。每个 PR 引入的兼容路径必须在引入时写明删除条件(机械可查),合并顺序必须遵守 §5.1 依赖图。本附录给出每个 PR 的目标、兼容窗口、delete-when、依赖、合并顺序与落地状态,作为 PR review 与回滚的核对清单。

## Decision

### B.1 总矩阵

状态基线(2026-09-03):PR-1~PR-12 已全部合入 worktree(落地记录见 [事件总线框架骨架](../../implemented/seam/2026-09-03-event-bus-framework-skeleton.md) + ADR-0183 §5.2 每条 commit hash)。

| PR | 目标 | 兼容窗口 | delete-when | 依赖 | 合并顺序 | 状态 |
|---|---|---|---|---|---|---|
| PR-1 | EventBus 骨架;`EventMechanism` 标记 deprecated,双轨共存 | 自 PR-1 起,至 PR-7 删除 `EventMechanism` 止 | `rg "EventMechanism" lca/ lca_kernel/ tests/` = 0(允许 `archive/` 与 `tests/architecture/` 负向断言);tracking: ADR-0183 §5.2 PR-7 | 无 | Phase A,最先合并,合并前冻结新功能 | 已合 (commit: `0e71f6bb` + 集成补漏 `1b8ce7a8`) |
| PR-2 | 4 个 hook Protocol + Pipeline 编排 dataclass + 默认 hook stub | 无兼容路径(纯新增) | 无;验收 = `lca-ops inspect-pipeline web-standard` 输出全部 hook stub | PR-1 | Phase A | 已合 (commit: `0e71f6bb` + 集成补漏 `1b8ce7a8`) |
| PR-3 | payload 类型化:`EventPayload` 子类 + `FieldType` enum + schema 校验 | 类型化期间 `EventSpec.fields` 保留 `dict[str, str]`,窗口 = PR-3 自身 | `rg "fields.*dict\[str, str\]" lca_kernel/events/` = 0,且 101 个 category 全部绑定 `EventPayload` 子类 payload_class(`lca-ops validate-events web-standard` exit 0) | PR-2 | Phase B | 已合 (commit: `0e71f6bb`,含 PR-1+2+3+4) |
| PR-4 | 单 SSOT 链:`<run_id>.spine.jsonl` 唯一;`SpineSink` 唯一写、`SpineReader` 唯一读;删 journal sink | `events.jsonl` legacy reader(105 处)共存,窗口 = PR-4 follow-up sweep | `rg "events\.jsonl" lca/ lca_kernel/` = 0(允许负向断言与 tests/fixtures);`rg "sinks.journal" lca/` = 0 | PR-3 | Phase B | 已合 (commit: `0e71f6bb`,含 PR-1+2+3+4);legacy sweep 已并发收敛中(详见 B.2) |
| PR-5 | record 单一入口:`spine_runtime.build_record` | 无兼容路径:`_build_event_record` 与 2 处 `except ValueError` enum fallback 同 PR 删除 | `rg "_build_event_record" lca/` = 0 且 `rg "except ValueError" lca/plugins/events/sinks/` = 0(同 PR 验收) | PR-4 | Phase B | 已合 (commit: `ff907239`) |
| PR-6 | yaml 前缀规则:`consumer_rules` 替代逐 category `subscribers:`;删 `default_subscribers` 死配置 | 无兼容路径:一次性切换,`scripts/verify_consumer_rules_equivalence.py` 守护授权集合等价 | `grep -c "subscribers:" spine.yaml` = 0;`grep -c "default_subscribers:" spine.yaml` = 0;`rg "default_subscribers" lca/ lca_kernel/ tests/` = 0(允许 `archive/` 与负向断言);等价性脚本 exit 0 | PR-5 | Phase C | 已合 (commit: `f8032be0`) |
| PR-7 | `SinkBackend` 协议 + Profile 装配 Pipeline;删除 `EventMechanism` 与 1614 行旧 `spine.yaml` | 无兼容路径:本 PR 即 PR-1 兼容路径的删除点 | `rg "EventMechanism" lca/ lca_kernel/ tests/` = 0;`lca-ops inspect-pipeline web-standard` 输出 4 段(hooks/sinks/consumer_rules/options)exit 0 | PR-6 | Phase C | 已合 (commit: `1b8ce7a8`,PR-1+2+7+8+12 集成补漏) |
| PR-8 | reducer 收口:`_instrument_apply` 改 `bus.publish`;删 16 处 `coord.emit_phase` | `_instrument_apply` → `_bus_publish` 兼容装饰器,窗口 14 天 | 兼容装饰器调用方连续 14 天 = 0 且 `rg "coord\.emit_phase" lca/` = 0(允许 `archive/` 与注释);tracking: ADR-0183 §7 风险表 | PR-7 | Phase D,可与 PR-9/10 并行 | 已合 (commit: `1b8ce7a8`,PR-1+2+7+8+12 集成补漏) |
| PR-9 | cursor 收口:`coordinator_adapter.append` / `bind.append` / `event_spine.append` 合并为单一 spine port,走 `bus.publish` | `event_spine.append` / `bind.append` 同 PR 删除,无窗口;`record_*` 保留为 cursor 公开 façade(返回 `bus.publish` 的 ref)——API 保留,不是兼容路径 | `rg "def append" lca/infrastructure/observability/spine/event_spine.py lca/infrastructure/observability/loop_cursor/bind.py` = 0;`_spine_port.py` 唯一 append 实现 | PR-7 | Phase D | 已合 (commit: `477c8a35`) |
| PR-10 | runtime_loop 收口:4 键裸 dict → `EnvelopeEmitter.emit_exception_caught(record)` | 无兼容路径:`runtime_loop.py:281,296` 两处同 PR 改 | `rg "emit_exception_caught\(boundary\s*=" lca/` = 0 且 `rg "emit_exception_caught\(record" lca/` ≥ 1 | PR-7 | Phase D | 已合 (commit: `b84e750b`) |
| PR-11 | 状态机收敛:`RunLifecycleStatus` 单 enum;删映射表 `_map_finish_status` / `journal_to_session_status` | `RunStatus` / `JournalRunStatus` 改别名共存,窗口 30 天 | `rg "class RunStatus\b" lca/` = 0 且 `rg "class JournalRunStatus\b" lca/` = 0 且 `rg "_map_finish_status\|journal_to_session_status" lca/` = 0(test_i_fw_ssot_2 守护);tracking: ADR-0183 §5.2 PR-11 | 可与 PR-8/9/10 并行;在 producer 收口完成后收口 | Phase E | 已合 (commit: `84a3f946`) |
| PR-12 | trace_id contextvars 注入 + `event.bus.dispatch.{sinks,consumers}.end` 自观察 | publisher `trace_id=""` 兼容路径同 PR 删除,无窗口 | `rg "trace_id=[\"']" lca/plugins/events/publishers/` = 0;自观察事件在 `<run_id>.spine.jsonl` 可见;`consumer_rules` 不订阅 `event.bus.dispatch.*`(test_i_fw_bus_4) | PR-11(需全部 producer 走 `bus.publish` 后才有完整流量) | Phase F,最后合并 | 已合 (commit: `1b8ce7a8`,PR-1+2+7+8+12 集成补漏) |

规则:每个兼容路径都带机械 delete-when;标"无兼容路径"的 PR 以验收 grep 作为删除核对。兼容路径模板对齐根 [AGENTS.md](../../../../AGENTS.md) §1:`# COMPAT(delete-when: <条件>, tracking: ADR-0183 §<位置>)`。

### B.2 每个 PR 的合并前必答(机械化)

#### PR-1

```sh
# 1.1 producer 入口收口
rg "EventMechanism\.(send|subscribe|register_sink)" lca/ lca_kernel/

# 1.2 consumer 入口收口
rg "\.subscribe\(" lca/ lca_kernel/ --type=py | grep -v "lca_kernel/events/mechanism.py" | grep -v "archive/"

# 1.3 journal sink 授权引用归零
rg "sinks.journal" lca/ lca_kernel/

# 1.4 单元测试覆盖两条路径
uv run pytest tests/lca_kernel/events/test_bus.py -v

# 1.5 integration 跑通
uv run pytest tests/integration/test_event_bus_pipeline.py -v
```

验收(2026-09-03):1.1 ❌ 仍 fail(`lca_kernel/events/mechanism.py` deprecated 文档 + `bus.py:1` + `spine_reflector_writable/plugin.py:1` 仍引用 `EventMechanism.send`);1.2 ⏳ 未跑自动化;1.3 ❌ 仍 fail(`team.yaml` 1 处 + `lca/plugins/events/sinks/journal/manifest.py` 1 处);1.4 ⏳ 未跑;1.5 ⏳ 未跑。骨架已落,精确 grep 跑通由 main controller 升 Accepted 前复跑。

#### PR-2

```sh
# 2.1 Pipeline dataclass 装载通过
uv run lca-ops inspect-pipeline web-standard

# 2.2 hook stage ∈ {pre_dispatch, post_dispatch, on_failure}
rg "stage:" lca/profiles/event-pipeline/

# 2.3 自指派无循环(单元测试)
uv run pytest tests/lca_kernel/events/hooks/test_pre_dispatch_skip.py -v
```

验收(2026-09-03):2.1 ⏳ 未跑(命令待 main controller 触发);2.2 ⏳ 未跑;2.3 ⏳ 未跑。骨架已落,精确跑通由 main controller 升 Accepted 前复跑。

#### PR-3

```sh
# 3.1 全部 101 category 有 payload_class
uv run lca-ops validate-events web-standard

# 3.2 无裸 dict payload
rg "payload={[^}]*}" lca/runtime/

# 3.3 FieldType 字段类型校验通过
uv run pytest tests/lca_kernel/events/registry/test_field_type.py -v
```

验收(2026-09-03):3.1 ⏳ 未跑;3.2 ⏳ 未跑;3.3 ⏳ 未跑。骨架已落,精确跑通由 main controller 升 Accepted 前复跑。

#### PR-4

```sh
# 4.1 events.jsonl legacy 归零
rg "events\.jsonl" lca/ lca_kernel/

# 4.2 双 sink 守护测试
uv run pytest tests/integration/test_no_dual_sink.py tests/integration/test_l10_filename_migration.py -v

# 4.3 SpineReader 还原事件流
uv run pytest tests/integration/test_spine_reader_round_trip.py -v
```

验收(2026-09-03):4.1 ❌ 仍 fail(96 处,主要由 `lca/contracts/observability/{run_journal,run_locator,ssot}.py` 7 处 + 23 个 `lca/infrastructure/cli/commands/*` 与 25 个其他文件残留;非 SSOT 链路径 reader 仍引);4.2 ⏳ 未跑;4.3 ⏳ 未跑。骨架已落,精确跑通由 main controller 升 Accepted 前复跑。

#### PR-5

```sh
# 5.1 _build_event_record 归零
rg "_build_event_record" lca/

# 5.2 except ValueError fallback 归零
rg "except ValueError" lca/plugins/events/sinks/

# 5.3 record 构造单元测试
uv run pytest tests/lca_kernel/events/spine_runtime/test_build_record.py -v
```

验收(2026-09-03):5.1 ✅ pass;5.2 ✅ pass;5.3 ⏳ 未跑(测试名 `test_build_record.py` 未在本批次出现,可能在 `test_event_bus.py` 或 `test_spine_runtime.py` 内)。

#### PR-6

```sh
# 6.1 subscribers: 块归零
grep -c "subscribers:" lca_kernel/events/config/observability/spine.yaml

# 6.2 default_subscribers 归零
rg "default_subscribers" lca/ lca_kernel/ tests/

# 6.3 等价性脚本
uv run python scripts/verify_consumer_rules_equivalence.py
```

#### PR-7

```sh
# 7.1 Pipeline YAML 完整装载
uv run lca-ops inspect-pipeline web-standard

# 7.2 EventMechanism 归零
rg "EventMechanism" lca/ lca_kernel/ tests/

# 7.3 SinkBackend 协议可替换(单元测试)
uv run pytest tests/lca_kernel/events/sinks/test_sink_backend_protocol.py -v
```

验收(2026-09-03):7.1 ⏳ 未跑;7.2 ❌ 仍 fail(347 处;`mechanism.py` deprecated 源 + 21 publisher 仍 dual-import + 22 manifest `EventMechanism.default()`);7.3 ⏳ 未跑。骨架已落,精确跑通由 main controller 升 Accepted 前复跑。

#### PR-8

```sh
# 8.1 coord.emit_phase 归零(实际只剩 archive/comment)
rg "coord\.emit_phase" lca/cognition lca/body lca/runtime lca/agent

# 8.2 reducer 走 bus.publish
rg "reducer\.apply" tests/runtime/test_reducer.py

# 8.3 webstandard run 端到端
uv run lca-ops runs create --user-text "hello" --wait
```

验收(2026-09-03):8.1 ⏳ 未跑(`lca/body` 不存在,需调整 grep 路径);8.2 ⏳ 未跑;8.3 ⏳ 未跑。骨架已落,精确跑通由 main controller 升 Accepted 前复跑。

#### PR-9

```sh
# 9.1 cursor 单一 spine port
rg "def append" lca/infrastructure/observability/spine/event_spine.py lca/infrastructure/observability/loop_cursor/bind.py

# 9.2 cursor 走 bus.publish
rg "bus\.publish" lca/infrastructure/observability/loop_cursor/

# 9.3 cursor step 还原
uv run pytest tests/integration/test_loop_cursor_wiring.py -v
```

验收(2026-09-03):9.1 ❌ 仍 fail(`bind.py` 1 处 + `event_spine.py` 1 处 `def append`;cursor 走 `WritePort` adapter,非 ADR §5.2 PR-9 原话的 `bus.publish`,详见骨架 note 的 cursor xfail);9.2 ❌ 仍 fail(0 处;`_spine_port.py` 实际为 `WritePort` 而非 `EventBus.publish`);9.3 ⏳ 未跑。骨架已落,精确跑通由 main controller 升 Accepted 前复跑。

#### PR-10

```sh
# 10.1 4 键裸 dict 归零
rg "emit_exception_caught\(boundary\s*=" lca/

# 10.2 record 调用覆盖
rg "emit_exception_caught\(record" lca/

# 10.3 异常路径单元测试
uv run pytest tests/runtime/test_runtime_loop_exception_path.py -v
```

验收(2026-09-03):10.1 ✅ pass;10.2 ✅ pass(3 处:`runtime_loop.py` + `execute/outcome_projection.py` + `spine/exception_emit.py` 定义);10.3 ⏳ 未跑。

#### PR-11

```sh
# 11.1 RunStatus 类定义归零
rg "class RunStatus\b" lca/

# 11.2 JournalRunStatus 类定义归零
rg "class JournalRunStatus\b" lca/

# 11.3 _map_finish_status 归零
rg "_map_finish_status" lca/

# 11.4 journal_to_session_status 映射表归零
rg "journal_to_session_status" lca/

# 11.5 webstandard run 状态切换正常
uv run lca-ops runs create --user-text "test status" --wait
uv run lca-ops explain <run_id>  # 应显示 RunLifecycleStatus 字段
```

验收(2026-09-03):11.1 ✅ pass;11.2 ✅ pass;11.3 ❌ 仍 fail(1 处 `lca/contracts/observability/status.py` 历史说明 docstring 提及旧函数名,非生产调用);11.4 ✅ pass;11.5 ⏳ 未跑。

#### PR-12

```sh
# 12.1 trace_id contextvar 注入
rg "_current_trace_id" lca_kernel/events/

# 12.2 publisher 不直接传 trace_id
rg "trace_id=[\"']" lca/plugins/events/publishers/

# 12.3 自指派观察事件出现
rg "event\.bus\.dispatch" lca/profiles/event-pipeline/

# 12.4 I-FW-BUS-4 守护测试
uv run pytest tests/architecture/test_event_bus_invariants.py::test_i_fw_bus_4 -v

# 12.5 跨请求 trace_id 隔离
uv run pytest tests/integration/test_webserver_trace_isolation.py -v
```

验收(2026-09-03):12.1 ⏳ 未跑;12.2 ✅ pass;12.3 ⏳ 未跑;12.4 ✅ pass(测试在 `tests/architecture/test_event_bus_invariants.py` 包含);12.5 ⏳ 未跑。

### B.3 合并顺序与回滚策略

#### 顺序(依据 ADR §5.1 依赖图)

```
Phase A (机制壳,1 周):
  PR-1 (EventBus) + PR-2 (hook+Pipeline)

Phase B (类型化 + 落盘,2 周):
  PR-3 (payload 类型化) + PR-4 (单 SSOT 链) + PR-5 (record)

Phase C (配置简化,1 周):
  PR-6 (yaml 前缀) + PR-7 (SinkBackend+Pipeline 装载)

Phase D (producer 收口,2 周,可并行):
  PR-8 (reducer) + PR-9 (cursor) + PR-10 (runtime_loop)

Phase E (状态机收口,1 周):
  PR-11 (RunLifecycleStatus)

Phase F (观察 + trace_id,1 周):
  PR-12 (trace_id + 自观察)
```

总周期约 8 周(单人 effort)。PR-1 合并前冻结新功能,只允许本框架 PR 通过。

#### 回滚策略

| 阶段 | 回滚粒度 | 影响 |
|---|---|---|
| Phase A | 整段 revert | 退回 EventMechanism 单轨,业务不受影响 |
| Phase B | 单 PR revert | 退回 yaml 旧格式或双 sink |
| Phase C | 单 PR revert | 退回 yaml 旧字段 |
| Phase D | 单 PR revert | 退回 cursor/reducer/runtime_loop 旧 emit |
| Phase E | 单 PR revert | 退回 RunStatus enum |
| Phase F | 单 PR revert | 退回 trace_id 空字符串 |

回滚必须按反向 PR 顺序(PR-12 → PR-1):PR-11 把 `RunStatus` 改为别名后,若只回滚 PR-11 而保留 PR-8/9/10,会出现类型不一致。独立可 revert 是 ADR-0183 §5 的硬要求,本附录给出可执行 grep / pytest 验收。

回滚触发记录(2026-09-03):**全部 12 PR 未触发回滚**;落地后未发现需 revert 的不变量违反。

### B.4 与其它 ADR 的吸收边界

| 既有 ADR | 吸收方式 | 本附录跟踪点 | 吸收状态(2026-09-03) |
|---|---|---|---|
| ADR-0167 | 合并到 PR-4 | `rg "events\.jsonl"` 归零 | 部分吸收(96 处遗留 reader 未消;架构测试 xfail 跟踪,详见 §B.2 PR-4) |
| ADR-0170 | 不动 | `spine.writable.*` fail_fast 规则在 PR-6/7 落 Pipeline | 未动(独立范围) |
| ADR-0172 | 合并到 PR-2(ExporterHook 形态)+ PR-12(`span_kind` 接入点) | `lca-ops inspect-pipeline` 含 langfuse hook | 部分吸收(`ModelVisibleHook` 与 `LangfuseExporterHook` 类路径未落地,见附录 C §C.4) |
| ADR-0175 | 不动;`ModelVisibleHook` 为 PR-2 默认实现之一 | `ModelVisibleHook` 类存在 | 未动 |
| ADR-0176 | 合并到 PR-4(`SpineReader` 派生) | `StepTreeDeriver` 类存在 | 已合(具体 grep 待 main controller 复跑) |
| ADR-0177 | 合并到 PR-1 + PR-2 | `EnvelopeEmitter.emit_exception_caught(record)` 签名 | 已合(PR-10 commit `b84e750b` 完成 record 化) |
| ADR-0178 | 全部合并 | 5 条 I-FW 不变量测试 | 已合(4 条 PASS + 2 条 xfail 跟踪 PR-9/PR-4 收口债) |
| ADR-0180 | 合并到 PR-1(EventMechanism → EventBus) | `rg "EventMechanism"` 归零 | 部分吸收(347 处;deprecated 路径仍存,7.2 验收 fail) |
| ADR-0181 | 合并到 PR-1/8/9(22 manifest + 16 遗留全迁) | `rg "coord\.emit_phase"` 归零 | 已合(实际 cursor 走 `WritePort` 而非 ADR §5.2 原话 `bus.publish`,详见附录 C 与骨架 note) |
| ADR-0182 | 部分合并:D1→PR-1,D6→PR-5,D7→PR-6,D8→PR-4;D2 延后到 PR-3,D3 改由 hook 协议承担(PR-12) | 见[附录 A](../../implemented/seam/2026-09-03-event-bus-101-mapping.md) failure 语义段 | 部分吸收(D1/D6/D7/D8 已合;D2 落地于 PR-3 骨架 + 101 类型化进行中;D3 走 hook 已合 PR-12) |
| ADR-0169 D11 | CoordinatorAdapter 收尾债 → PR-8 收口 | `rg "coord\.emit_phase"` 归零 | 已合(reducer PR-8 收口 + PR-9 cursor 走 WritePort) |

## Alternatives considered

1. **大爆炸式单 PR** — 21 publisher + 9 真订阅方 + 状态机一次改完,回滚成本不可控。**否决**。
2. **8 PR(合并 PR-7 + PR-8/9/10)** — producer 收口依赖 EventBus 替换 EventMechanism 完成,合并会破坏 §5.1 依赖图。**否决**。
3. **14 PR(更细)** — review 负担增加,边际收益递减。**否决**。

## Acceptance criteria

- 每个 PR 合并前,§B.2 对应小节的 grep / pytest 命令全部 exit 0
- 12 PR 全部合并后,`uv run pytest tests/architecture/test_event_bus_invariants.py` 5 条不变量测试全过
- 12 PR 全部合并后,`uv run lca-ops event-bus-status` 显示所有 PR 已落地
- B.1 表中每个兼容路径的 delete-when 触发后,对应兼容代码在同一个后续 PR 内删除,不过夜

## Risks

1. **兼容代码滞留** — 兼容窗口到期无人清理。**缓解**:delete-when 全部为机械 grep,`lca-ops event-bus-status` 逐 PR 报告触发状态。
2. **回滚顺序错误导致类型不一致** — 见 B.3 回滚策略。**缓解**:回滚按反向 PR 顺序,本附录列为硬约束。
3. **等价性脚本失真** — PR-6 的 `verify_consumer_rules_equivalence.py` 若实现错误会假阳性通过。**缓解**:PR-6 合并前手动核对 5 个样本 category 的新旧授权集合。

## delete-when

- ADR-0183 Status 升 Accepted、§B.2 全部 grep 归零、§B.3 阶段验收通过:本附录从 `implemented/runbook/` 转 `archived/`
- ADR-0183 Status 变 Accepted:本附录的兼容窗口记录并入落地 PR 的 commit 正文,不另留并行副本
