# Agent Note: Doctor H-xref 漏读 `<run_id>.spine.jsonl`

Status: proposed

## Problem

`lca.infrastructure.observability.spine.sinks.naming` 在 PR-27 之后把默认 spine 文件名从 `events.jsonl` 迁移到 `$run_id.spine.jsonl`,并明确文档"所有 reader 对 `<run_id>.spine.jsonl` 与 `events.jsonl` 都接受;当两个文件同时存在时,优先读取 spine 命名"。但 doctor 的 `_scan_xref`(`lca.plugins.transport.webserver.handlers.runs.doctor.step_check`)仍只读 `<run_dir>/events.jsonl`,导致该 hop 在所有走 PR-27 默认配置的 run 里读到全零(`spine_event_total=0` / `spine_body_tool_start=0` / `events_jsonl_exists=false`),`HopVerdict.ok=True`,**该报的 broken 全部漏报**:

- `body.tool.execute.start > 0 且 journal.steps[*].tool_call 全为空` — 即"工具执行了但 step-tree 没记录"这种因果链断裂
- `llm.call.end > 0 且 journal.totals.steps == 0`
- `phase.*.fold > 0 且 journal.totals.phases == 0`

证据来源:

- `traces/runs/run_365ad8d3c2c0/`:spine 实际写入 `run_365ad8d3c2c0.spine.jsonl`(273 KB, 371 events, 含 2 个 `body.tool.execute.start`),`events.jsonl` 不存在。`manifest.extra.doctor_report.hops["H-xref"]` 字段全部为零、`ok=true`、`detail="journal ⇄ spine 一致"`。同时 `H7.tool_total=0`(从 `journal.json` 读),但 spine 里有 2 个 `step.tool_call.record`(tool=`bash`,outcome=`success`)—— 客观证据(`/tmp/lca-tool-probe-*/probe.txt` 已写入)与 doctor 报告完全矛盾。
- `lca/infrastructure/observability/spine/sinks/naming.py` 的 docstring 与 `DEFAULT_SPINE_TEMPLATE = "$run_id.spine.jsonl"`。
- `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:71`:`spine_path = run_dir / "events.jsonl"`,无 `run_id.spine.jsonl` fallback。

debug agent 在用 `debug-run` 时会拿到"一切 ok"的结论,但其实跨源已经断了;失去 H-xref 这道门禁意味着任何"spine 写了但 journal 没反映"的真 bug 都会无声通过 run-doctor 与 manifest 物化。

## Proposal

把 `_scan_xref` 与相关 consumer 改成调用 `lca.infrastructure.observability.spine.sinks.naming.spine_filename_for_run(run_id)` 派生文件路径,或直接显式 `run_dir / f"{run_id}.spine.jsonl"` fallback:

1. 在 `step_check.py` 的 `_scan_xref` 顶部用 `spine_filename_for_run(run_id)` 算出首选路径,`events.jsonl` 作为次选;两者都存在时按 naming.py 约定选 spine 命名。
2. 把同样的 fallback 模式应用到所有直接构造 `run_dir / "events.jsonl"` 的 reader(`debug-run` / `journal logs -r` / `journal trace` 等),用一次 `scripts/check_no_legacy_events_path.py` 类 grep 守护。
3. 在 `lca/infrastructure/observability/spine/sinks/naming.py` 增加 `find_spine_file(run_dir, run_id) -> Path` 助手,把"spine 命名优先 + events.jsonl fallback + 都不存在时 raise FileNotFoundError"封装成单一入口,所有 reader 走它,避免再出现"hardcoded 一个文件名"的 seam 漏修。
4. doctor 模型 `events_jsonl_exists` 字段重命名为 `spine_file_exists`,减少"events.jsonl 是 SSOT"的旧心智模型泄漏。

## Wire contract

- 派生函数:`spine_filename_for_run(run_id: str) -> str`(已存在,naming.py)。
- 新增助手:`find_spine_file(run_dir: Path, run_id: str) -> Path` — 优先 `<run_dir>/<run_id>.spine.jsonl`,其次 `<run_dir>/events.jsonl`,都缺则抛 `FileNotFoundError`。
- doctor `StepScan.events_jsonl_exists: bool` → `spine_file_exists: bool`(同语义)。

## Alternatives considered

### Why not 仅在 doctor 里 hardcode `run_id.spine.jsonl`?

最小改法是 `step_check.py:71` 把 `run_dir / "events.jsonl"` 改成 `run_dir / f"{run_id}.spine.jsonl"`。否决:**其他 reader 仍有同样问题**(`journal logs -r` / `journal trace` / `debug-run`),挨个 patch 是同一 seam 的同一类错误,应该一次性抽出 `find_spine_file`。留个 COMPAT,先做对、后续逐步消除 readers 里的硬编码。

### Why not 强制保留 `events.jsonl` 不变、撤回 PR-27?

否决:PR-27 已落地、boot 事件用 `boot-events.jsonl` 而非全局 `events.jsonl` 的设计本身正确(`events.jsonl` 重名导致目录冲突),撤回等于推翻已有 ADR 决策,且把每个 run 的所有事件挤进一个固定文件名与 trace 隔离模型相悖。代价大于收益。

### Why not 不修 doctor,改让 step-tree accumulator 把 tool_call 写回 `journal.json`?

doctor 反映的不只是"tool_total 是否对",还有 `llm.call.end > 0 且 totals.steps == 0` 等。问题源头是 doctor 拿不到 spine 计数;改 accumulator 只能盖住其中一个 case,且会引入"为了让 doctor ok 而改 Reducer 单写路径"这种 C4 违例。

## Acceptance criteria

- 给定 `traces/runs/run_365ad8d3c2c0/`,`debug-run` 在 `H-xref.ok=false`、`detail` 含 `"spine.body.tool.execute.start=2 but journal.tool_total=0 (no tool recorded)"`。
- `scripts/check_no_legacy_events_path.py`(或同等 lint)在 CI 失败当任何 reader 文件出现 `Path("events.jsonl")` 字面构造,且未与 `find_spine_file` 关联。
- `find_spine_file` 的单测覆盖 4 种 case:`<run_id>.spine.jsonl` 存在 / `events.jsonl` 存在 / 两者并存 / 都不存在。

## Risks

- 把 `events_jsonl_exists` 字段重命名会让 `manifest.extra.doctor_report.hops["H-xref"]` 的字段名变更;若有 downstream consumer 写死字段名,需要同 PR 改。检索范围 `lca/` `scripts/` `docs/`。
- 误把 `boot-events.jsonl` 卷进 fallback 链。boot 事件不进 per-run dir,本来就隔离;但要在 `find_spine_file` docstring 与测试里钉死"只看 per-run dir"。

## Migration plan

1. 引入 `find_spine_file(run_dir, run_id)`。
2. `_scan_xref` 切到新 helper,把 `events_jsonl_exists` 改名为 `spine_file_exists`,下下游 grep 改字段名。
3. 把 `journal logs -r`、`journal trace`、`debug-run` 的 reader 改成同一 helper。
4. 加 lint 守门:`Path("events.jsonl")` 字面构造 + 未引用 `find_spine_file` = 失败。

## Related

- `lca/infrastructure/observability/spine/sinks/naming.py` — PR-27 默认名迁移的 SSOT。
- `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py` — H-xref 实现位置。
- `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:519` — 期望的 broken detection 代码已就位,只因计数为零永远不触发。
- `docs/specs/harness-spine-spec.md` — spine 命名约束的 ADR-0167 / ADR-0169。