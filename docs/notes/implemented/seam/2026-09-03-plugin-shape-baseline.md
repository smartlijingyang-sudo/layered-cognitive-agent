# Agent Note: lca/plugins/ 单 Manifest 范式 —— 三类违例全清零

Status: implemented(2026-09-03)

## Problem

`lca/plugins/` 下 plugin 形态不统一。Phase A 基线共 **70 个违例**:

| 违例 | 数量 | 影响 |
|---|---|---|
| `@plugin(...)` 缺可见的 `effects=` 声明 | 49 | 副作用类无法静态推导,review 与 tripwire 失效 |
| events/{sinks,publishers,subscribers}/*/manifest.py 双形态残留(`event_plugin_spec` + `plugin_spec: dict`) | 17 | 鉴权真值在 `lca_kernel/events/config/**/*.yaml`,dict 是零读者孤儿数据 |
| 同 id 镜像 | 2 对 4 处 | 启动 DAG 行为漂移 |

## Decision

### Phase A:审计工具(只加法)

新增 `scripts/check_plugin_shape.py`(三维 AST 扫描:missing_effects / dual_form_residue / duplicate_id),与 `codegen_plugin_metadata.py` 的 ADR-0110 contract 面正交。`lca-ops audit-plugin-shape` 包装;AGENTS.md §5 加 Plugin 范式节。

### Phase B:删 17 个孤儿 manifest(决策偏离:删而非转 @plugin)

原计划写"转 `@plugin`",但转出来是无人装配的死代码(违反单一职责与零死代码要求)。全仓三遍 grep(`*.py`/`*.yaml`,lca/lca_kernel/tests/bundles/profiles)确认 17 个文件零读者后**直接删除**。鉴权真值不动(`EventRegistry.load` 读 yaml)。`delegation_cache/manifest.py` 有真读者,保留。

### Phase C:补 effects + 合镜像

关键发现:49 个"缺 effects"里 **37 个已有 `effects=EffectClass.X` 枚举形态**,但静态扫描器(`_kw_literal_str`)只认字符串字面量。运行期 `_normalize_effects` 对两种形态等价(`EffectClass` 是 str Enum),故统一转小写字符串形态 + 清理失效 `EffectClass` import。剩余 12 个按文件实际行为判定补声明(落盘→`"filesystem"`、OTLP→`"network"`、纯计算→`"none"` 等,逐文件理由在提交 `31f895d7` / `f88fa7a1` body)。

镜像合并:
- `lca-run-loop-driver-registry`:保留 `loop_drivers/registry.py`(生产 `$module` 指向它,`bundles/web-app.yaml:200`、`bundles/runtime-core.yaml:19`),删根文件,改 `execute/loop_drivers.py` 两处 import
- `control.act.execute`:保留平铺 `act_execute.py`(`__init__.py` 唯一引用),删 `act/` 整个子目录(零引用)

顺带修复:`sinks/file.py` 死 import `LEGACY_FILE_NAME`(该符号不存在于 `naming.py`,导致 `test_e2e_journal_wiring.py` 2 个失败)—— 属 C1 触碰区域的邻接清理,修复了分支既有断裂。

## 影响面

| 阶段 | 提交 | 改动 |
|---|---|---|
| A | `8841debf` | 新建扫描器 + CLI + AGENTS.md 节 + 基线 |
| B | `970233a4` | 删 17 个孤儿 manifest(−538 行) |
| C3 | `7b443a1f` | 合并 2 对镜像(−2 个 @plugin 入口) |
| C1 | `31f895d7` | 22 个 effects(observability + learning) |
| C2 | `f88fa7a1` | 25 个 effects(phase_graph + control) |

## 验收

| 检查 | 结果 |
|---|---|
| `python scripts/check_plugin_shape.py` | **all 228 plugins follow single-Manifest convention**(70 → 0) |
| 基线快照 `docs/notes/baselines/plugin-shape.json` | 三维全 0 |
| `python scripts/check_plugin_metadata.py --json` | 228 plugins,critical 10 持平,warning 220 → 218 |
| 装配链路 | `SpineChainSink` 仍由 `profiles/event-pipeline/web-standard.yaml` 装配;6 个有生产引用方的 publisher 的 `plugin.py` 未动 |
| 测试 | `tests/lca_kernel/events tests/plugins/events tests/architecture/test_event_bus_invariants.py tests/harness/test_pipeline_loader.py tests/integration/test_e2e_journal_wiring.py tests/integration/test_event_bus_e2e.py` = 183 passed, 1 xfailed(PR-9 既有债) |
| 既有断裂修复 | `test_e2e_journal_wiring.py` 由 2 failed → 2 passed |
| ruff | 分支不引入新错(`lca/plugins` 错误数 16 → 12,剩余全部为基分支既有,位于未触碰文件) |

## 已知既有孤儿(不在本次范围,未动)

- 9 个零生产引用方的 publisher:`spine_reflector_{boot,control,kernel_loop,perception,phase,phase_graph,team,writable}` + `spine_writable_matrix` + `spine_loop_cursor` 的 `plugin.py`
- plugin 版 `spine_step_tree_accumulator/subscriber.py`(生产用的是 `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py`)

## delete-when

| 路径 | 触发删除条件 |
|---|---|
| `scripts/check_plugin_shape.py` + `lca-ops audit-plugin-shape` | 长期保留为守护门禁;若决定只靠 CI 集成则可删 |
| 上述既有孤儿 | 由 ADR-0183 后续 PR 决定迁/删(需与事件总线迁移同步) |
| `lca/plugins` 剩余 12 个 ruff 错(console.py E402 ×7 / run_ledger / step_check / lifecycle) | 各文件责任方修复,非本范式范围 |
