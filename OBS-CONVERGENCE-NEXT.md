# OBS-CONVERGENCE-NEXT — 观测面收敛可并行 PR 清单

> 依据:根 note + 5 子 note,对照仓库现状(2026-09-04)。
> 排除:ADR-0185 PR-4(删 model_visible 旁路 + composer hook 接线)。

## 0. 仓库现状(已核验)

| 项 | 已落地 | 剩余 |
|---|---|---|
| note 1 L1 | `RunLifecycleStatus` + COMPAT alias | status/RoleStatus 字面比较位点; `to_jsonable` 双份(后者随 PR-4 删 `_capture_io`) |
| note 2 fsync | `FsyncPolicy` + `PLAN-fsync.md` | ADR-0179;`FileSink.fsync_policy`; TracingFileSink fallback 无 fsync |
| note 3 emit | **已合入**:`def emit_exception_caught` 仅 `exception_emit.py`;runtime_loop 走 `exc_to_record` | FileSink `sidecar_label` 分流(原 note PR-4);dual spine accessor 统一 |
| note 4 payload | model_visible typed;spine.yaml 101 payload_class | 98/101 泛型;`PLAN-payload-typing.md` PR-0~4 |
| note 5 lint | emit gate + event-bus 守门族 | `check_runtime_invariants.py` 完整版;fsync lint |
| ADR-0185 | PR-0~3 + PR-3.1 doctor/narrative | **PR-4**(他处进行中) |

## 1. 可立即并行的 5 项(文件集不重叠)

### P1 · fsync 协议(复用 FsyncPolicy,见 PLAN-fsync.md)
- 新 ADR-0179;`FileSink`/`TracingFileSink` 接 `fsync_policy`;fallback 强制 fsync
- `scripts/check_fsync_ssot.py` + run-layout 文档
- 验收:`pytest tests/observability/spine/ tests/lca_kernel/events/ -q`

### P2 · payload 地基(PLAN-payload-typing.md PR-0)
- 修 `build_record` 对非壳 typed payload 落空 dict
- `_validate_schema` 启用 fields 校验骨架
- exception yaml 4 键 vs ExceptionRecord 11 键对齐

### P3 · exception typed payload(PLAN-payload-typing.md PR-1)
- `SpineExceptionCaughtPayload` + spine.yaml fields
- 依赖 P2

### P4 · status 字面收口(note 1)
- `result_finalizer` / journal_doc / CLI / step_tree / member_status 等字面 → enum 谓词
- 架构断言:`rg '"paused"'` / `rg '== RoleStatus\.'` 白名单化

### P5 · dual spine accessor 统一(emit review HIGH)
- `exception.caught` 用 `resolve_active_spine`,`exception.finally` 用 `set_active_spine`
- 统一为一个 accessor;补回归锁

## 2. 刻意缓办

1. ADR-0185 PR-4(他处)
2. `to_jsonable` 合并(与 PR-4 删 `_capture_io` 同批)
3. note 5 大一统守门(反模式迁完后再落)

## 3. 已完成(本批会话)

- ADR-0185 PR-3.1 doctor fold + narrative + waterfall 注释
- note-3 emit 单入口合入 + emit lint 转绿
- `DSH-GAP-AUDIT.md` / `PLAN-fsync.md` / `PLAN-payload-typing.md`
