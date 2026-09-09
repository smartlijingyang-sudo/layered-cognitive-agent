# ADR-0212 — step_tree 派生面 SSOT 单写收口：删 tree_accumulator 与 O7 shim，StepTreeFoldDeriver 失败可见

> **状态：** **Proposed — 2026-09-09**
>
> **一句话**：journal.json 的派生面 SSOT 单写已在 ADR-0186 / 0191 / 0194 / 0195 收口为 `StepTreeFoldDeriver`；同 PR 把残留的 `StepTreeAccumulatorDeriver` 整文件、`infrastructure/observability/spine/derivers/step/tree.py` re-export shim（O7 delete-when）一次性删完，并把 `StepTreeFoldDeriver.derive()` 的写盘失败从 `log.warning + swallow` 升级为 fail-loud，让观测面真正成为事实面。
>
> **Review：** 待评审。
>
> **Accepted 闸门：**
> 1. §4 三个 deletion 全部 delete-when 满足：`rg "StepTreeAccumulatorDeriver" lca/ lca_kernel/` = 0；`rg "infrastructure\.observability\.spine\.derivers\.step\.tree\b" lca/ lca_kernel/ tests/` = 0；`rg "from lca\.infrastructure\.observability\.spine\.derivers\.step " lca/ lca_kernel/ tests/` = 0
> 2. §5 fail-loud 实现到位：`StepTreeFoldDeriver.derive()` 写盘失败不再 `log.warning` swallow，而是抛 `JournalWriteError`（typed exception, contract 层登记），`flush()` 同语义
> 3. §6 回归测试 `tests/plugins/session/derivers/step_tree/test_fold_deriver_idempotence.py` 落地，覆盖：重复 flush 幂等、写盘失败抛 typed exception、单次 fold 重放 = spine 重放
> 4. `tests/observability/spine/derivers/test_step_tree_accumulator.py` 删除；同 import 的 `test_observation_ssot_regression.py` / `test_orphan_cancel_pre_boot.py` / `test_orphan.py` / `test_runtime_journal_binding_integration.py` 全部不再 import `tree_accumulator`
> 5. doctor H3 对 run_f78f66322f1d 复跑从 `duplicate step_id: ['step-001']` 转 `ok=true`（闭集合规）
> 6. CI 同步门 `scripts/check_run_debug_sync.py` + `scripts/check_package_contracts.py` + `uv run pytest tests/plugins/session/derivers/step_tree/ tests/scenario/doctor/ -q` 全过

**编号**：0212（0209 / 0210 / 0211 已占用）。

**关系**：

- **Builds on**：ADR-0015 contracts 无行为、ADR-0062 Plugin 运行时收口、ADR-0093 持续控制面、ADR-0110 插件合约统一化、ADR-0167 step-tree materialization、ADR-0167.1 step-tree deriver wiring cleanup、ADR-0186 Session SSOT、ADR-0191 Fact Plane 收敛、ADR-0194 认知 Loop 架构收敛、ADR-0195 平台架构收敛（O7 退役契约持有者）、ADR-0209 agent_lab 收编、ADR-0211 Worker Contract 收紧。
- **Refines**：ADR-0167 §"StepTreeAccumulatorDeriver 退役声明"（从「声明不写盘」到「物理删除」）、ADR-0195 §2.5 P5（O7 delete-when 真正达成）、ADR-0186 §I-SESSION-5（派生面失败可见性，C9 幂等/重入 与 C11 事实可追溯 的失败端）。
- **Supersedes**：无。
- **Reject**：「保留 tree_accumulator 但加 `@deprecated`」（跨 PR 后门，违反 AGENTS.md §4「无 delete-when 的兼容分支 = 红灯」）；「让 derive() 继续 `log.warning` swallow 写盘失败」（观测面 silent failure，正是 run_f78f66322f1d 的根因面）；「把 O7 shim 改名为新 shim 再删」（没意义的多一步）；「新增第二个 fold deriver 用于 'capability provide'」（违反 C4 Reducer single-write 与 ADR-0195 §1.4 单写矩阵）。

**理由**：run_f78f66322f1d 的 doctor H3 报 `duplicate step_id: ['step-001']`（journal.json 3 步、spine 重放仅 2 步）。replay `StepTreeFoldDeriver.fold_step_tree(events)` 直接产 2 步无重复 → **fold 函数正确，问题在写入侧的失败可见性**：当前 `derive()` 写盘失败被 `log.warning` 吞掉（`fold_deriver.py:122-127`），若第二次写入在某路径上因 stale state 或 partial-write 失败，caller 完全看不到，观测面留下"看起来写完"的 journal.json 与事实面分歧。这是 C4（Reducer single-write / 派生面一致性）与 C11（事实可追溯）的失败端未收口。同时 `StepTreeAccumulatorDeriver` 整文件（926 行，self-claim「不再写盘」但类、`flush()`、`_build_document`、`_write_journal` 全在）保留在生产 import path 上，是「delete-when 没清干净」+ 「CapReactor 单写声明」未兑现的具体点。本 ADR 把这两件事在同一 PR 收口。

---

## 0. 第一性原理：问题本质

### 0.1 三个具体不变量违反

| 不变量 | 当前形态 | 证据 |
|---|---|---|
| **C4 Reducer single-write** | journal.json 在文件层"只 1 个写者"声明，但旧 `tree_accumulator._build_document` + `JournalDocumentWriter` 调用链仍可达；删未删 = 失败端未兑现 | `tree_accumulator.py:1-13` 自标 COMPAT 但类仍导出；`fold_deriver.py:125` 写盘失败 swallow |
| **C9 幂等/重入** | `flush()` 文档说「no-op when prior derive ran」，但实现是「再 derive 一次覆盖同一份文件」（`fold_deriver.py:131-140`）；若第二次 fold 因 transient state 失败，journal.json 残留的是第一次的正确结果，**没人知道第二次失败** | 同上 swallow |
| **C11 事实可追溯 + ADR-0195 §1.4 单写矩阵** | O7 delete-when 仍 =1（`tree.py` 自引）；journal.json 写者矩阵只剩 1 行承诺但实代码可触达 2 个 | `rg "JournalDocumentWriter" lca/infrastructure/observability/spine/derivers/step/` 当前 = 1（`tree_accumulator.py` 内） |

### 0.2 真实病因面（run_f78f66322f1d 复盘）

spine 事件流只有 2 个 `writable.step.start`（step_id=step-001 / step-002）；`.venv/bin/python /tmp/replay_fold_full.py run_f78f66322f1d` 重放 spine 产 2 步无重复；但磁盘上 journal.json 是 3 步且 step-001 重复。fold 逻辑正确、写入侧的失败端未兑现 → "写盘失败 + swallow" 在某种 transient 路径上留下 stale 写入。**修法不是猜 fold**，是把"派生面失败可见"与"派生面单一真值"两层都收口。

---

## 1. 目标

| ID | 内容 |
|---|---|
| G1 | 物理删除 `StepTreeAccumulatorDeriver` 整文件与 O7 re-export shim，兑现 ADR-0167 §"退役声明" 与 ADR-0195 O7 delete-when |
| G2 | `StepTreeFoldDeriver.derive()` 写盘失败从 `log.warning + swallow` 升级为 typed exception fail-loud；观测面失败成为事实面事件 |
| G3 | `flush()` 第二次调用幂等（覆盖写入同一份数据 + step 数量不变） |
| G4 | 同 PR 落地回归测试 + 删 stale 测试 + 同步 11 个引用文档 |

---

## 2. 非目标

- 不重写 `fold_step_tree` 闭集（已 ADR-0166 D4 闭集，本 ADR 不动 phase 词汇表）
- 不改 Session SSOT（ADR-0186 / 0191 已收口）
- 不新增派生面（ADR-0195 §1.4 严禁平行 provider）
- 不动 doctor H3 判定逻辑（它本身就在 catch 本 ADR 要修的 bug）

---

## 3. 范围与不在范围

### 3.1 In-scope

- `lca/infrastructure/observability/spine/derivers/step/tree_accumulator.py`（926 行）— 删
- `lca/infrastructure/observability/spine/derivers/step/tree.py`（re-export shim）— 删
- `lca/plugins/session/derivers/step_tree/fold_deriver.py:122-127` — 写盘失败改抛 typed exception
- `tests/observability/spine/derivers/test_step_tree_accumulator.py` — 删
- `tests/observability/test_observation_ssot_regression.py` / `test_orphan_cancel_pre_boot.py` / `test_orphan.py` / `test_runtime_journal_binding_integration.py` — 移除 `tree_accumulator` import（如果有，改走 `StepTreeFoldDeriver` fixture）
- `tests/plugins/session/derivers/step_tree/test_fold_deriver_idempotence.py` — 新增（覆盖幂等 + 失败可见 + 单 fold = spine 重放）
- `lca/contracts/observability/journal/errors.py`（若无则新建）— 登记 `JournalWriteError`（typed exception）
- 11 个引用文档：扫到 tree_accumulator 字面 → 把 "StepTreeAccumulatorDeriver (legacy) 已删；生产用 StepTreeFoldDeriver" 替换旧引用

### 3.2 Out-of-scope

- `lca/plugins/observability/deriver/step_tree/plugin.py` — 保留（这是 O7 shim 的目标态，能力声明的真源）
- `lca/plugins/session/derivers/step_tree/journal_fold.py` — 不动（fold 逻辑已对，spine 重放验证 2 步）
- `docs/observability/run-layout.md` — 文案更新（同步删 O7 shim 与 tree_accumulator 提及），不改结构

---

## 4. 删除清单（delete-when 守卫）

| ID | 文件 / 入口 | 守卫命令（执行 = 0 才 Accept） |
|---|---|---|
| D1 | `lca/infrastructure/observability/spine/derivers/step/tree_accumulator.py` | `rg "StepTreeAccumulatorDeriver" lca/ lca_kernel/` = 0 |
| D2 | `lca/infrastructure/observability/spine/derivers/step/tree.py` | `rg "infrastructure\.observability\.spine\.derivers\.step\.tree\b" lca/ lca_kernel/ tests/` = 0（O7 守卫） |
| D3 | `tree_accumulator` 在测试中的所有 import | `rg "from lca\.infrastructure\.observability\.spine\.derivers\.step\.tree_accumulator\|from lca\.infrastructure\.observability\.spine\.derivers\.step import.*tree_accumulator" tests/` = 0 |

D2 满足时 O7 的 `delete_when: rg "infrastructure.observability.spine.derivers.step_tree" lca/ = 0` 同时满足（`tree.py` 是唯一 import 自己的来源）。

---

## 5. fail-loud 设计

### 5.1 typed exception 登记

`lca/contracts/observability/journal/errors.py`：

```python
class JournalWriteError(RuntimeError):
    """journal.json 写盘失败。观测面失败 = 事实面事件，必须 raise。

    与 Session.append 的 `FactAppendError` 同语义层（ADR-0186 / 0191 单轨）。
    """
    def __init__(self, run_id: str, target: Path, original: BaseException) -> None:
        self.run_id = run_id
        self.target = Path(target)
        self.original = original
        super().__init__(
            f"journal.json write failed run_id={run_id} target={target}: {original}"
        )
```

登记到 `lca/contracts/observability/journal/__init__.py` 的 `__all__`，与 `JournalStep` / `JournalDocument` 同层。

### 5.2 `StepTreeFoldDeriver.derive()` 行为变更

```python
# before (fold_deriver.py:122-127):
try:
    JournalDocumentWriter(self._run_dir / "journal.json").write(doc)
except Exception as exc:
    log.warning("StepTreeFoldDeriver.derive write failed err=%s", exc)
return doc

# after:
JournalDocumentWriter(self._run_dir / "journal.json").write(doc)
return doc
```

错误透传给 caller；caller（`RunTerminalizer.terminalize`）已经持有 `manifest.extra.flush_errors` 收集位，把 `JournalWriteError` 登记进去并 fail-loud 终止 run 关闭流程，而不是像今天 silent。

### 5.3 `flush()` 幂等保证

```python
def flush(self, *, outcome: str | None = None) -> None:
    if outcome is not None:
        self._outcome = outcome
    events = list(self._iter_events())
    if not events and self._last_document is not None:
        return  # 已是当前语义；保留
    self.derive(events)  # 第二次 flush 会重新 fold 同份 events → 同结果
```

幂等保证由 `fold_step_tree` 的纯函数语义提供：同 events 输入永远产同 JournalDocument（同 step_id / step_index / phase / outcome / window_signal）。**第二次 flush 写盘覆盖第一次，结果相同**。回归测试覆盖此不变量。

---

## 6. 回归测试

`tests/plugins/session/derivers/step_tree/test_fold_deriver_idempotence.py`：

```python
def test_repeat_flush_writes_identical_journal(tmp_path):
    """C9 幂等/重入：同 events + 同 outcome → 同 JournalDocument。"""
    spine_events = [_make_writable_step_start(step_id="step-001", step=1, phase="perceive"),
                    _make_phase_think_fold(step_index=1),
                    _make_brain_think_end(),
                    _make_writable_step_start(step_id="step-002", step=2, phase="perceive"),
                    _make_phase_think_fold(step_index=2),
                    _make_brain_think_end()]
    d1 = StepTreeFoldDeriver("run_x", tmp_path).derive(spine_events)
    d2 = StepTreeFoldDeriver("run_x", tmp_path).derive(spine_events)
    assert d1.steps == d2.steps
    assert [s.step_id for s in d1.steps] == ["step-001", "step-002"]  # 不重复

def test_write_failure_raises_typed_exception(tmp_path):
    """C11 事实可追溯：写盘失败不再 swallow。"""
    deriver = StepTreeFoldDeriver("run_x", tmp_path)
    # 制造不可写路径（read-only fs）
    (tmp_path / "journal.json").write_text("placeholder")
    (tmp_path).chmod(0o444)
    with pytest.raises(JournalWriteError) as exc_info:
        deriver.derive([_make_minimal_event()])
    assert exc_info.value.run_id == "run_x"

def test_spine_replay_equals_single_fold(run_f78f66322f1d):
    """回归 run_f78f66322f1d：单次 fold 等于 spine 重放。"""
    spine = jsonl_to_events(f"traces/runs/run_f78f66322f1d/run_f78f66322f1d.spine.jsonl")
    doc = StepTreeFoldDeriver("run_f78f66322f1d", Path("traces/runs/run_f78f66322f1d")).derive(spine)
    assert [s.step_id for s in doc.steps] == ["step-001", "step-002"]
    assert doc.s["step_id"] for s in doc.steps == sorted_unique([s.step_id for s in doc.steps])
```

---

## 7. 验证矩阵

| 变更 | 命令 | 期望 |
|---|---|---|
| 删 tree_accumulator | `rg "StepTreeAccumulatorDeriver" lca/ lca_kernel/` | exit 0, 0 行 |
| 删 O7 shim | `rg "infrastructure\.observability\.spine\.derivers\.step\.tree\b" lca/ lca_kernel/ tests/` | exit 0, 0 行 |
| fail-loud 行为 | `pytest tests/plugins/session/derivers/step_tree/test_fold_deriver_idempotence.py -q` | 全过 |
| doctor H3 修复 | `./scripts/lca-ops debug-run run_f78f66322f1d` | H3.ok=true |
| ruff / format | `uv run ruff check lca/ tests/` | exit 0 |
| 同步门 | `uv run python scripts/check_run_debug_sync.py` | exit 0 |
| 包契约 | `uv run python scripts/check_package_contracts.py` | exit 0 |
| 集成 | `uv run pytest tests/plugins/session/derivers/step_tree/ tests/scenario/doctor/ tests/observability/spine/ -q` | 全过；原 test_step_tree_accumulator.py 已删 |

---

## 8. 风险与回滚

| 风险 | 概率 | 缓解 |
|---|---|---|
| 测试集有人依赖 tree_accumulator 旧行为 | 中 | D3 守卫 + CI；同 PR 同步改 |
| 11 个引用文档漏改 | 低 | `rg "StepTreeAccumulator" docs/` 在 merge 前扫一次 |
| 写盘 fail-loud 后某个 doctor / terminalize 路径误抛 | 低 | fail-loud 透传，caller 自己决定 retry/abort；JournalWriteError 是 typed，子句易 catch |
| 删 O7 shim 破坏 `lint-imports` | 低 | shim 本身只 re-export，删后 plugin.py 仍暴露相同名字 |

无 ADR-0212 即回滚到 ADR-0186 / 0195 既有事实面。

---

## 9. 落地切片（同 PR 一次性收口）

1. `git rm lca/infrastructure/observability/spine/derivers/step/tree_accumulator.py`
2. `git rm lca/infrastructure/observability/spine/derivers/step/tree.py`
3. `git rm tests/observability/spine/derivers/test_step_tree_accumulator.py`
4. 新增 `lca/contracts/observability/journal/errors.py` 与 `JournalWriteError`
5. 改 `lca/plugins/session/derivers/step_tree/fold_deriver.py:122-127`：写盘失败 raise typed exception
6. 新增 `tests/plugins/session/derivers/step_tree/test_fold_deriver_idempotence.py`
7. 改 4 个 import 树（test_observation_ssot_regression / test_orphan_cancel_pre_boot / test_orphan / test_runtime_journal_binding_integration）：移除 `tree_accumulator` import
8. 改 11 个引用文档：tree_accumulator 字面 → StepTreeFoldDeriver
9. 跑 §7 验证矩阵；通过后提 PR

---

## 10. 与 ADR-0186 / 0191 / 0194 / 0195 / 0209 / 0211 的关系

- ADR-0186 I-SESSION-5：派生面 SSOT 已收敛为 StepTreeFoldDeriver；本 ADR 把"退役声明"兑现为物理删除。
- ADR-0191 Fact Plane 收敛：本 ADR 让 FactAppendError 旁边多一个 JournalWriteError（typed exception 同语义层）。
- ADR-0194 P5：衍生面 SSOT 收口的一部分。
- ADR-0195 O7 delete-when：本 ADR 让 O7 守卫从 1 → 0。
- ADR-0209 / 0211：lab / Worker Contract 系列；本 ADR 与它们无重叠（不动 lab plugin 与 Worker signature），但同 PR 一起跑 `lca-pre-push-checks` 减少集成 risk。

---

**Appendix A — 触发事件**：run_f78f66322f1d 复盘（2026-09-09）。
**Appendix B — 与 run_f78f66322f1d 的具体关系**：spine 重放 fold 产 2 步无重复 → fold 正确；journal.json 3 步重复 step-001 → 写入侧失败 + swallow 让 stale state 漏掉；doctor H3 仍能 catch 它（事实面完整），但 fix 在写入侧的失败可见性 + 物理删除残留 deriver。
**Appendix C — 一次性格而非 COMPAT shim**：本 ADR 不引入 compat shim；删除与替换在同 PR 完成（AGENTS.md §4）。