# PLAN: FileSink fd fsync 协议对齐 DSH — 可执行小计划

> **范围**:`docs/notes/proposed/seam/2026-09-03-2-seam-fsync-semantics.md` 的 4 级收敛子 note 2。
> **状态**:plan(不参与 `check_notes_tree.py` 校验;放 worktree 根,合入前删)。
> **元决策**:[ADR-0178](../../../docs/adr/0178-observation-control-state-convergence.md) / [ADR-0184](../../../docs/adr/0184-event-lifecycle-managed-delivery.md) PR-2。
> **依据**:note 2 + `lca/infrastructure/observability/spine/sinks/{file_sink,tracing_file_sink}.py` + `lca_kernel/events/persistence.py::FsyncPolicy` + `lca_kernel/events/sinks/spine_sink.py` + ADR-0184。

---

## 0. 关键发现(读代码后纠正 note 假设)

| note 假设 | 代码事实 | 纠正 |
|---|---|---|
| "新 ADR 0179 配套" + `FsyncProtocol(PER_WRITE/BATCH/COMMIT)` | `lca_kernel/events/persistence.py:46` 已有 `FsyncPolicy(SYNC/BATCH/ASYNC)`(ADR-0184 PR-2 已落) | **不要新建 `FsyncProtocol`**。要么复用 `FsyncPolicy` 并扩 1 个 `COMMIT` 值,要么 `FsyncProtocol = FsyncPolicy` 别名 — 同一枚举不能两套名字。 |
| "FileSink 3 套 fd fsync 语义不同" | `FileSink._maybe_fsync` 实际上 batch fd 走 `self._fd`,exceptions_fd 跑 close-only fsync;TracingFileSink fallback fd 经 `with open("a")`(`tracing_file_sink.py:135`),**Python 文件对象 close 才刷,无 fsync** | note 描述准确,事实成立。 |
| "`scripts/check_observation_ssot.py` 加规则" | 此 worktree `scripts/` 不存在 `check_observation_ssot.py`(note 5 提到的根 note PR-2 描述里也未列出实际文件;只在 `docs/notes/implemented/` 历史里描述"已建") | 不假定该脚本存在;**lint 守门随对应 PR 一并建**,不在本计划复用。 |
| "9 条规则 0 命中" | `rg "check_observation_ssot" lca/` 无源码命中(只有 `docs/notes/implemented/...` 引用) | 同上 |
| "DSH `~/deepseek-harness` vendor" | 不在 worktree;`vendor/` 只有 cordis/cosmokit/schemastery;pyproject 把 `deepseek_harness` 列为 mypy 忽略模块,**无源码** | DSH 对照只能基于 note 文字("每次 append handle.sync()"),**不可验**。Plan 不依赖 DSH 源码结论,只对齐语义形状。 |
| "journal.json 写盘走 fsync" | `JournalDocumentWriter.write` 走 tmpfile + `replace()`(**原子 rename,无 fsync**); `FilesystemJournalStore.append` 走 staging + `os.fsync` + `os.replace`(fsync + rename,PR-4 已落) | journal.json 是可重建物化视图(ADR-0167 D11),**fsync 是 nice-to-have,非核心**;spine ledger 才是 SSOT。本计划不动 journal.json fsync 路径。 |

**净结论**:note 2 方向对(3 套 fd 缺统一协议),但具体实施必须**复用已有 `FsyncPolicy`** 而不是再造一个,且不要预设 `check_observation_ssot.py` 文件存在。

---

## 1. 现状差距表(LCA vs DSH 形态)

| 维度 | DSH 形态(note 描述) | LCA 现状(代码事实) | 差距 |
|---|---|---|---|
| 主 spine fd `<run_id>.spine.jsonl` | per-write `handle.sync()` | `_maybe_fsync` batch(100 条 / 100ms);close 时 fsync;`SpineSink._maybe_fsync` batch(100 / 50ms) | LCA 走 batch 是性能折中;**正确但需文档化** + 让 caller 显式选 |
| `<run_id>.exceptions.jsonl`(exception index) | (DSH 无独立 index,exceptions 与 spine 同 fd) | 仅 close 时 fsync,**运行期崩溃丢尾部** | 形态不同:**LCA 异常 index 与主 fd 分开**,正确性反而更脆弱。需选 `PER_WRITE` 或提高 fsync 频率 |
| TracingFileSink fallback `FALLBACK.log` | (DSH 无此概念) | `with open("a")` 文本追加,**无 fsync** | 异常兜底路径 = traceback 永久丢失风险(用户 2026-09-03 反馈)。必须 `PER_WRITE` |
| 进程级异步 fsync 接管 | (DSH 同步) | `PersistenceWorker`(ADR-0184 PR-2 已落)异步消费 `DeliveryQueue`,`FsyncPolicy.SYNC/BATCH/ASYNC` 三档 | **新平面**——老 `FileSink` 走 spine.py 同步路径,新 worker 走 queue + 异步路径。**两条入口 fsync 策略不联动** |
| 协议承载 | DSH 每次 `handle.sync()` 强制 | LCA 3 套隐式行为 + caller 1 个 worker 显式 | **统一 enum 缺失** |
| 用户文档 | DSH 有 | 无(`FileSink.__init__` docstring 只写 "Fsync runs every N events or T ms") | 差距中等,补 docs 即可 |

---

## 2. 最小 PR 切分(≤ 3 PR)

> 序列 `PR-A → PR-B → PR-C`,线性依赖;每 PR 一个提交主题,自带测试与验收命令。
> 总 commit 形式:`docs(notes): fsync seam executable plan from DSH gap audit`(本 plan 文件)+ 三个 PR commit。

### PR-A:协议载体统一(`FsyncPolicy` 扩 1 值 + FileSink 接受)

- **新文件 `docs/adr/0179-file-sink-fsync-protocol.md`**(note 2 提到,本计划确认需要)
  - §0 决策摘要:**不新建 `FsyncProtocol` 枚举**,复用 `lca_kernel.events.persistence.FsyncPolicy`(`ADR-0184 PR-2`)并扩一个 `COMMIT` 值。理由:同一概念双名 = SSOT 违反(AGENTS.md §1 + ADR-0178 §0 "SSOT 已存在")。
  - §2 决策:
    - D1 `FsyncPolicy.COMMIT` 新增值,语义"仅 close 时 fsync",最小开销,接受风险。
    - D2 `FileSink.__init__` 接受 `fsync_policy: FsyncPolicy = FsyncPolicy.BATCH`(注:此处**不是 Protocol**,沿用既有 worker 命名)。
    - D3 旧 `fsync_batch` / `fsync_interval_ms` 参数**保留 + 标 deprecated**:`# COMPAT(delete-when: PR-A 全 caller 迁完, tracking: ADR-0179 PR-A)`。`fsync_policy=BATCH` 时读旧;`SYNC/ASYNC/COMMIT` 时旧参数忽略(显式 log warning,非 fail-loud)。
  - §3 不在范围:`TracingFileSink.fallback_fd` 单独策略(PR-B)、`PersistenceWorker` 行为(已落)、`journal.json` 写盘(独立)。
- **改动**:
  - `lca_kernel/events/persistence.py:46`:`FsyncPolicy` 加 `COMMIT = "commit"`。
  - `lca/infrastructure/observability/spine/sinks/file_sink.py`:
    - `__init__` 加 `fsync_policy: FsyncPolicy = FsyncPolicy.BATCH` 参数(从 `lca_kernel.events.persistence` import,层向检查:`infrastructure` → `lca_kernel` 是否被 lint-imports 允许 — 需 `pyproject.toml` importlinter 配置确认;若不允许,改为 Protocol-level Literal ["sync"|"batch"|"async"|"commit"],由 caller 端 mapping)。
    - `_maybe_fsync(self, fd: int)` 改 `_maybe_fsync(self, fd: int, policy: FsyncPolicy)`:
      - `SYNC`:每次 `_maybe_fsync` 都 `os.fsync`;`_writes_since_fsync` / `_last_fsync_at` 计数器可停用。
      - `BATCH`:现状不变。
      - `ASYNC`:no-op(留给上层 Profile 接管,沿用 worker 行为)。
      - `COMMIT`:no-op,仅 close 时 fsync。
    - `close()` 按 policy 决定:`COMMIT` 不再 close-time fsync(SYNC/BATCH 保留)。
  - `lca/infrastructure/observability/spine/sinks/tracing_file_sink.py`:
    - `__init__` 接受 `fsync_policy` 参数,转发给 `FileSink`(fallback 路径策略下 PR-B 强制覆盖)。
- **测试**:`tests/observability/spine/test_file_sink_fsync.py` 新建
  - 矩阵:`FsyncPolicy ∈ {SYNC, BATCH, ASYNC, COMMIT}` × `fd ∈ {main, exceptions}` = 8 case
  - mock `os.fsync` 计数;断言 SYNC 每事件 fsync;COMMIT 仅 close 时;BATCH 按阈值;ASYNC 零调用
  - 回归锁:旧 `fsync_batch=10, fsync_interval_ms=50` 默认调用下行为不变
- **验收**:
  ```sh
  uv run ruff check --fix . && uv run ruff format .
  uv run lint-imports
  uv run pytest tests/observability/spine/test_file_sink_fsync.py -q
  uv run pytest tests/observability/ tests/lca_kernel/events/ -q
  ```
- **delete-when**:
  - 旧 `fsync_batch` / `fsync_interval_ms` 参数 — `delete-when: 全 caller 切 `fsync_policy`, tracking: ADR-0179 PR-A`
  - `FsyncPolicy.COMMIT` 命名(若 PR-B 决定用别处别名)— PR-B 决策后回填

### PR-B:TracingFileSink fallback fd 强制 PER_WRITE + 文档化

- **触发**:PR-A 协议落地后,fallback 路径语义仍未统一,note 2 §"Alternatives considered" 已识别这是"bug,不是性能折中"。
- **改动**:
  - `lca/infrastructure/observability/spine/sinks/tracing_file_sink.py`:
    - `_write_fallback` 改用 `os.open(..., O_APPEND | O_CREAT)` + `os.write` + `os.fsync`(每次 fallback 写入后 fsync)。
    - 保留 `_summarize_payload` 形态不变。
  - `lca/infrastructure/observability/spine/sinks/file_sink.py::docstring` 修订:补 "3 套 fd × 3 档 fsync 语义表"。
  - `docs/architecture/optimization-iterations.md` 新增 "FileSink fd 持久化协议" 节(承 note 2 acceptance criterion)。
- **测试**:`tests/observability/spine/test_tracing_file_sink_fallback.py` 新建
  - 触发 fallback 后 SIGKILL 模拟(`os.fsync` mock + `fsync` 计数),断言 FALLBACK.log 落盘完整
  - 失败路径(main raise + fallback raise)失败必升级到 structlog ERROR,fsync 计数 = 1
- **验收**:
  ```sh
  uv run ruff check --fix . && uv run ruff format .
  uv run pytest tests/observability/spine/ -q
  ```
- **delete-when**:无 compat shim,无

### PR-C:守门脚本 + 与 PersistenceWorker 联动文档

- **新文件 `scripts/check_fsync_ssot.py`**(不复用 `check_observation_ssot.py` — 该文件此 worktree 不存在,note 5 也只描述性引用,不假定):
  - 规则 1:`rg "fsync_batch\s*=" lca/infrastructure/observability/spine/sinks/` 命中必须 ≤ N(PR-A 迁移后),带 `# COMPAT(delete-when: 命中 = 0, tracking: ADR-0179 PR-A)` 行级豁免位
  - 规则 2:`TracingFileSink._write_fallback` 必须出现 `os.fsync`(AST 静态检查)
  - 规则 3:`FileSink.__init__` 必须含 `fsync_policy` 参数
  - 规则 4:`FsyncPolicy` 单一来源声明:`rg "^class FsyncPolic" lca/` 必须命中 = 1(防止双枚举复发)
- **`docs/observability/run-layout.md`** 补一节 "fsync 协议与崩溃一致性":说明
  - 主 spine fd:`PersistenceWorker(ADR-0184 PR-2)` 异步消费 + 任意 FsyncPolicy
  - 老链 `FileSink.__init__` 直写:仅 boot / 兼容性路径
  - TracingFileSink fallback:`PR-B` 后强制 `PER_WRITE`(注:`PER_WRITE` 是 DSH 用词;LCA 实际值 = `FsyncPolicy.SYNC`,文中对齐)
- **测试**:`tests/scripts/test_check_fsync_ssot.py`(脚本自身的 fixture 测试)
- **验收**:
  ```sh
  uv run python scripts/check_fsync_ssot.py
  uv run pytest tests/scripts/ -q
  uv run pytest tests/observability/ tests/lca_kernel/events/ -q
  ```
- **delete-when**:
  - 旧 `fsync_batch=` 行级豁免 — `delete-when: rg 命中 = 0, tracking: ADR-0179 PR-C`

---

## 3. delete-when 全表(汇总)

| compat / 临时路径 | delete-when 条件 | tracking |
|---|---|---|
| 旧 `fsync_batch` / `fsync_interval_ms` 参数 | 全 caller 切 `fsync_policy` 参数 + 稳定 ≥ 14 天 | ADR-0179 PR-A |
| PR-A 警告日志(fsnc 旧参数被忽略) | `fsync_policy` 默认值被 Profile 全声明 + lint 命中 = 0 | ADR-0179 PR-A |
| `# COMPAT` 行级豁免(`check_fsync_ssot.py` 规则 1) | rg 命中 = 0 | ADR-0179 PR-C |
| PR-A 在 `FileSink.__init__` 的 `fsync_policy` 缺省 `BATCH` | Profile / Bundle 全覆盖 `fsync_policy` + 14 天 | ADR-0179 PR-A |

---

## 4. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `FsyncPolicy` 上提 `FileSink` 跨层依赖(`infrastructure` → `lca_kernel`) | PR-A 实施前先确认 `pyproject.toml` importlinter 配置;不允许则 `FileSink` 端用 `Literal["sync","batch","async","commit"]` + `runtime_checkable` Protocol 镜像 |
| `FsyncPolicy.COMMIT` 与 `ASYNC` 语义重叠 | 区分 `COMMIT`(close-only 落盘) vs `ASYNC`(后台线程 — LCA 未实装,no-op 等效 BATCH);PR-A docstring 必写差异 |
| 性能回归:fallback fd 强制 `PER_WRITE` 后,异常风暴场景下 IOPS 下降 | fallback 本就是异常路径,降速可接受;`lca-ops events-delivery --policy` 已能观察;PR-B 加 assertion "`_open_fallback_fd` 触发率 < 1/1000 event"(在 `test_tracing_file_sink_fallback.py` 文档化,**不实装**监控,避免范围 creep) |
| 测试 mock `os.fsync` 不能验"真的 fsync" | PR-A/B 矩阵以计数 + 调用时机为断言,功能正确性 + 真实 fsync 靠集成层 `test_event_delivery_e2e`(已有,ADR-0184 PR-B) |
| Windows fsync 语义差异 | PR-A docstring 写明 POSIX-only;Windows 行为 `os.fsync` 在 win32 等效 `FlushFileBuffers`,依赖 Python stdlib 抽象,不分支处理 |
| `SpineSink`(kernel 侧 ADR-0184)与 `FileSink`(infra 侧 ADR-0189/0169)是两条入口,fsync 策略可能互不知晓 | PR-C 文档化明确双路径;`PersistenceWorker.fsync_policy` 与 `FileSink.fsync_policy` 由调用方独立配置,但协议枚举共享 |

---

## 5. 计划外发现(本任务不动,留 ADR 提案)

> 仅记录,不修。

1. `JournalDocumentWriter.write`(journal.json)走 tmpfile + `replace()`,**无 fsync**;若用户要求 journal.json 强一致需另开 ADR。
2. `FilesystemJournalStore.append`(L2 durable)走 staging + fsync + rename,已合理;但其 `fsync_each_append` 默认 `True` 与 `FileSink` 默认 `BATCH` 不一致 — 双账本 2 套语义。
3. `close_barrier.py` 文件不存在(grep 0 命中),ADR-0169 D8 描述的 `CloseBarrier` 实现位置需要核实(可能在 `lca/infrastructure/observability/` 子目录)。
4. `TracingFileSink._safe_class_name` shim 与 `safe_class_name` from file_sink 重复定义(legacy 兼容) — 可在 PR-9 旧 spine 全退役时一并删。

---

## 6. 退出条件(本 plan 完成)

- [x] `PLAN-fsync.md` 落到 worktree 根(commit `docs(notes): fsync seam executable plan from DSH gap audit`)
- [ ] PR-A 合入(`FsyncPolicy.COMMIT` + `FileSink.fsync_policy` + 测试)
- [ ] PR-B 合入(TracingFileSink fallback 强制 fsync + 文档)
- [ ] PR-C 合入(守门脚本 + 双路径文档)
- [ ] 全部合后,note 2 `Status: implemented`,根 note 升 `implemented/`,ADR-0179 状态改 `Accepted`

---

## 7. 参考

- `lca/infrastructure/observability/spine/sinks/file_sink.py` — FileSink 当前实现(`_maybe_fsync` line 275)
- `lca/infrastructure/observability/spine/sinks/tracing_file_sink.py` — TracingFileSink 当前实现(`_write_fallback` line 129)
- `lca_kernel/events/persistence.py::FsyncPolicy` — 既有枚举(ADR-0184 PR-2)
- `lca_kernel/events/sinks/spine_sink.py::SpineSink` — worker sink,fsync 策略已配置
- `lca/infrastructure/observability/loop_cursor/persistence_coordinator.py` — 包装 FileSink,`flush()` 走 `getattr(sink, "flush", None)`(line 158)— PR-A 后 `FileSink.flush` 可下放,与现有 Protocol 对齐
- `docs/adr/0178-observation-control-state-convergence.md` §0 — 现状痛点"(2) flush 时机不透明"
- `docs/adr/0184-event-lifecycle-managed-delivery.md` PR-2 — `FsyncPolicy` 首次落地
- AGENTS.md §1 / §3 / §5 / §6 — 工程思维 / 五层单向依赖 / Conventions / 命令矩阵