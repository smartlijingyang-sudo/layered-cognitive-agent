# ADR-0281：Run 产物文件系统权限契约（owner-only 隔离）

## 状态

**Proposed — 2026-10-04**

**更新注记（2026-10-06，iter-arch）**：§1.1 的 run-failure writer 路径(`…/handlers/runs/terminal/failure/failure.py`)是 `2edc98c18`(2026-10-04)当时的 stat 快照，落笔时准确；`1997d84ef`(2026-10-05，RunTerminalCoordinator 重构)已将该目录展平为 `terminal/failure.py`(单层)，盘上已无 `failure/` 子目录。按此路径查找请用 `lca/plugins/transport/webserver/handlers/runs/terminal/failure.py`(与 ADR-0122 §5、docs/debug/README.md 一致)。§1.1 正文(`2edc98c18` stat 锚定)保留为 2026-10-04 快照，不改历史。

> **一句话**：`traces/runs/<run_id>/` 目录与其中落盘的 run 产物（spine ledger、exceptions 索引等）现在被钉在 owner-only 权限上（目录 0700 / 文件 0600）——`2edc98c18` 已在实现层落地，本 ADR 把它写成契约，钉住语义、边界与待拍板项。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？跑在同一宿主机上的多个 assistant / 租户：run 产物常含用户原话、工具入参（含可能的凭证片段）、journal 轨迹，同机其他 uid 可读就是泄漏面。
2. 真实问题？实现已落地（`2edc98c18 fix(observability): hold run artifacts at owner-only access`，2026-10-04 02:04），但 **docs/** 对 0700/0600 零提及（grep 实证）——契约只存在于代码和测试里，改一边的人不知道另一边的存在。
3. 删掉会坏什么？不坏——本 ADR 是收敛记录，不新增行为；但 0700/0600 的语义（新建/收紧/抑制）会继续只存在于实现者脑中。
4. 更简单方案？只在 backlog 记一笔。否决：权限边界是安全契约（与 ADR-0253 凭证边界同族），值得 ADR 级钉住——权限漂移是静默的（umask、copy 工具都不报错）。
5. 契约先行？否——语义已在实现+测试中落地（见 §1），本 ADR 只做"名实相符"的收敛记录，状态诚实标 Proposed。
6. 与现有 ADR 冲突？无。0253（Sentinel 出站控制面与凭证边界）管"凭证不许出边界"，本 ADR 管"边界内产物不许跨 owner 可读"——是 0253 在文件系统层的细化还是独立契约，见待拍板③。
7. 状态诚实？Proposed。范围扩展、遗留产物处置、与 0253/0266 的归属，全部待拍板，见 §3。

## 1. 实证（main@2edc98c18）

### 1.1 权限原语

| 原语 | 值 | 位置 | 语义 |
|---|---|---|---|
| `RUN_DIR_MODE` | `0o700` | `lca/infrastructure/persistence/run_paths.py:15` | run 目录的持有权限 |
| `RUN_ARTIFACT_MODE` | `0o600` | `lca/infrastructure/observability/spine/sinks/naming.py:29` | run 产出文件的持有权限 |

- 目录：`ensure_run_dir()`（run_paths.py:33-46）——mkdir 后**每次调用都 chmod 0700**；chmod 失败被 `contextlib.suppress(OSError)` 抑制（docstring 明示理由：目录可能属于别的 owner，那不该让 run 落盘失败——**fail-open 是故意的**，见待拍板④）。
- 文件：`file_sink.py:193-211` 用 `os.open(path, O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC, RUN_ARTIFACT_MODE)`——mode 交给内核，umask 只能收紧不能放宽（0600 & ~umask 恒为 0600）。
- 覆盖的 writer（`2edc98c18` stat）：`run_buffer_registry.py`、`file_sink.py`、`writable_matrix/defaults.py`、`ledger_seam.py`、run-failure 的 `kernel.log` 路径（`lca/lca_kernel/.../handlers/runs/terminal/failure/failure.py`）——全部把 run 目录的 mkdir 路由到 `ensure_run_dir`。

### 1.2 契约测试（已存在）

- `tests/observability/spine/sinks/test_run_artifact_mode.py`：断言 ledger（`run_mode.spine.jsonl`）与 exceptions 索引无 group/other 位；`ensure_run_dir` 新建即 0700；**已存在的 0775 目录被收紧回 0700**（`test_ensure_run_dir_tightens_a_directory_that_already_exists`）。
- `tests/persistence/test_run_paths_import_order.py`：每种 import 顺序在新解释器中复验（pytest 收集期先 import sink 会掩盖 CLI 真实失败面）——修的是 `2edc98c18` 顺带发现的循环 import（message 有记录）。

### 1.3 反向缺口

`docs/` 全仓 grep "0700|owner-only|0600" **零命中**（本轮实证）——实现者写了测试但没写文档；任一后续改动（如新增 writer 直调 `mkdir` 而不走 `ensure_run_dir`）都会静默打破契约。

## 2. 契约

- **C1（目录持有，现状已落地）**：所有 per-run 目录的创建/路过必须经 `ensure_run_dir()`，持有 0700；已存在的宽松目录会被先到的 writer 收紧；chmod 失败抑制（fail-open，故意，见 §3④）。
- **C2（文件持有，现状已落地）**：run 产物文件的创建 mode 必须为 `RUN_ARTIFACT_MODE`（0600），通过 `os.open` 的 mode 参数传递，不许事后 `chmod` 补救（TOCTOU 窗口）。
- **C3（新增 writer 纪律）**：任何新增的 run 产物 writer 必须① 目录经 `ensure_run_dir`、② 文件经 `RUN_ARTIFACT_MODE`、③ 补一条 owner-only 断言测试（三件套缺一即违反本契约）。
- **C4（边界声明，未裁决）**：本契约当前只覆盖 `runs/<run_id>/` 下的 run 产物；memory/sessions/uploads 等其他持久化产物不在范围内（见待拍板②）。

## 3. 待拍板（需李超/Athena 裁决，arch 轮不擅自决定）

1. **遗留产物**：`2edc98c18` 只收紧"被 writer 路过"的目录；历史上已落盘的 group-readable 文件（旧 run 目录、未被新 writer 触及的）是否需要批量收紧或声明豁免？
2. **范围扩展**：契约是否扩展到 `memory/`、`sessions/`、`workspace/uploads`（FileStore 全局单例，见 ADR-0277 Implementation Notes）？扩展意味着改 FileStore 与 session writer 的创建路径。
3. **归属**：本契约是 ADR-0253（凭证边界）在文件系统层的细化条款，还是与 0266（standing 写权限矩阵）并列的独立契约？决定 ADR 索引的交叉引用写法。
4. **chmod 抑制的 fail-open**：`ensure_run_dir` 对"目录属于别的 owner"的 chmod 失败选择抑制（run 不死、目录保持宽松）——这是深思熟虑的可用性权衡，还是应该在 multi-user 部署下改为 fail-closed（并给出 owner 冲突的显式错误）？

## 4. 验收

- T1：新建 run 目录即 0700、已存在宽松目录被收紧——已由 `test_ensure_run_dir_holds_the_access_bound` / `test_ensure_run_dir_tightens_a_directory_that_already_exists` 覆盖，本 ADR 只做引用。
- T2：ledger 与 exceptions 索引无 group/other 位——已由 `test_file_sink_ledger_and_exceptions_index_are_owner_only` / `test_routing_file_storage_ledger_is_owner_only` 覆盖，本 ADR 只做引用。
- T3：新增 writer 三件套纪律——tests lane 可认领：扫描所有直调 `mkdir`/`open` 创建 run 产物的 writer，逐个补断言（本轮未做，只立项）。
- T4：待拍板①②③④决议落盘——任一方向都行，但必须显式记录，不能 silent。
