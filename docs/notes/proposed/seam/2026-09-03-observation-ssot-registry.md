# Agent Note: 观测面 SSOT 全量收口与约束保证

Status: proposed

## Problem

debug agent 的 4 个真 BUG 背后,加上全 repo 扫描,共发现 **5 类 13 处 SSOT 散落反模式**。同一根因:**SSOT 已在 contracts/observability/ 或 contracts/atoms/ 落地,但消费方未走 SSOT,直接用字面字符串 / 文件名 / 路径 / 集合**。新增字段、reader、Status 值,任意一处硬编码未被 lint 拦下,就会重蹈覆辙。

### 反模式 1:文件名 / 路径硬编码(7 处)

| # | 硬编码 | 已存在的 SSOT | 反模式位置 |
|---|---|---|---|
| 1a | `events.jsonl` | `RunLocator.events_path` 已正确实现 spine+legacy 兜底 | `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:71` 直拼路径 |
| 1b | `journal.json` | `RunLocator.journal_step_path` 已存在 | `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py:216`(writer) + `lca/infrastructure/observability/replay/cursor.py:57`(reader) + `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:550`(字符串) |
| 1c | `manifest.json` | `RunLocator.manifest_path` 已存在 | `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:107` |
| 1d | `journal.narrative.md` | `RunLocator.journal_narrative_path` 已存在 | `lca/infrastructure/observability/journal/backends/filesystem.py` writer 路径 |
| 1e | `kernel.log` | **无 SSOT**(RunLocator 未提供该方法) | `lca/plugins/transport/webserver/handlers/runs/terminal/failure.py:72` |
| 1f | `<run_id>.exceptions.jsonl` | **无 SSOT**(由 `file_sink.py:174` 模板拼接) | `lca/infrastructure/observability/spine/sinks/file_sink.py:174` |
| 1g | `profile_snapshot.json` × **2 处常量重复** | 仅 1 处走 `RunLocator`,1 处走本地常量 | `lca/plugins/transport/webserver/handlers/runs/session/diagnostics.py:32` + `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py:30` |

### 反模式 2:Status 枚举字面字符串(30+ 处)

| # | 字符串 | 已存在的 SSOT enum | 反模式位置(全部) |
|---|---|---|---|
| 2a | `"paused"` / `"completed"` / `"failed"` | `lca/contracts/atoms/enums.RoleStatus`(团队委派) | `lca/contracts/models/observability/journal_doc.py:34/181`(Literal 字段),`lca/contracts/protocols/declarative/declarative_execution.py:71/78`,`lca/harness/declarative/compile/phase_governance.py:290/332`,`lca/runtime/result_finalizer.py:70/93`,`lca/plugins/providers/run_ui_encoder/_encoder.py:118/122/124`,`lca/harness/projection/web.py:71`,`lca/harness/projection/agent_state.py:156`,`lca/harness/diagnostics/normalizer.py:126`,`lca/infrastructure/observability/stream/trace_inspector.py:194`,`lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py:283/289/290`,`lca/plugins/transport/webserver/handlers/runs/terminal/materialization.py:153`,`lca/plugins/transport/webserver/handlers/runs/session/session.py:66-71`(显示字典),`lca/infrastructure/cli/commands/runs.py:157` 等 |
| 2b | `RunStatus`(plugin 私有) | `JournalRunStatus`(journal 层) — **无 contracts 层 SSOT** | `lca/plugins/transport/webserver/handlers/runs/session/session.py:53` 定义本地 enum,plugin 反向耦合 |
| 2c | `RoleStatus` 字面比较 | **已有** `is_terminal_status` / `is_success_status` / `is_full_success_status`(自身注释禁止字面比较) | `lca/cognition/member_status/in_memory.py:54/55/63` + `lca/cognition/member_status/consult_policy.py:184` |

### 反模式 3:模型可见投影边界模糊(本 note 串起子 note)

| # | 反模式 | 缺什么 |
|---|---|---|
| 3a | `model_visible_llm_adapter.py:285` 在 LLM `await` **之前** capture | post-call 投影协议 |
| 3b | `tools.json` 22 个 `{}` | 工具 schema 序列化优先级(provider_schema 回退) |
| 3c | `messages[0].role="user"` 但 content 是 system 模板 | 上游 system 注入错误 vs 投影错误分通道 |

### 反模式 4:`to_jsonable` 多份定义

| # | 重复定义 | 单一职责违反 |
|---|---|---|
| 4 | `lca/infrastructure/observability/loop_cursor/_capture_io.py:33` + `lca/infrastructure/observability/journal/step/projector.py:23` 两份 `to_jsonable` | 同一职责两份实现,变更一处忘了另一处 |

### 反模式 5:`CapabilityKey` vs `seam_key: str` 字面

| # | 反模式 |
|---|---|
| 5 | `lca/contracts/harness/composition/plugin.py:82/88/106` 用 `seam_key: str` 字面字符串,与 `lca/contracts/mechanisms/capability.CapabilityKey` 并行;后者本应取代前者 |

### 单一根因 + ADR-0176 D5 形变

这 5 类反模式的共同根因:**观测面 / 装配面的 SSOT 已存在(contracts/observability/ + contracts/atoms/ + contracts/mechanisms/),但消费方各绕各的**。

进一步观察(`docs/specs/harness-spine-spec.md` §0 N1):

> N1 — Journal 唯一事实:任何模型可见输入、工具调用、子代理报告、技能激活都有且仅有一个 durable `SessionEvent`。`AgentState`、`RunSession.status`、前端 activity 都是 journal 的 projection。

当前 `_scan_xref`(H-xref hop)的本质是"writer 双写、reader 双读、各自硬编码"的事后修补。**SSOT 真生效后,H-xref 应退化为"spine 文件可读性 sanity",而不是"两个 writer 是否一致"的事后真值校验** — 即 ADR-0176 D5 形变。

## Proposal

按"第一性原理 + 架构优雅 + 干掉垃圾 + 模块化 + 职责清晰"五项约束,重整为 **L1 SSOT 注册表 + L2 消费方迁移 + L3 lint 守门 + L4 H-xref 退化** 四阶一次性收口。

### L1: `contracts/observability/ssot.py`(本提案核心,1 个文件,5 段)

```python
# 1) spine file SSOT —— 替代 RunLocator.events_path 的 fs 内联
def find_spine_file(run_dir: Path, run_id: str) -> Path: ...

# 2) RunLocator 文件名 SSOT(补全 RunLocator Protocol 缺的 3 个)
class RunLocator(Protocol):
    def run_dir(self, run_id) -> Path: ...
    def journal_step_path(self, run_id) -> Path: ...
    def events_path(self, run_id) -> Path: ...
    def journal_narrative_path(self, run_id) -> Path: ...
    def manifest_path(self, run_id) -> Path: ...
    def kernel_log_path(self, run_id) -> Path: ...        # 新增(1e)
    def exceptions_path(self, run_id) -> Path: ...        # 新增(1f)
    def profile_snapshot_path(self, run_id) -> Path: ...  # 新增(1g 的 SSOT)
    def evidence_dir(self, run_id) -> Path: ...
    def materialization_dir(self, run_id, *, generator_id, generator_version) -> Path: ...
    def latest_pointer_path(self) -> Path: ...
    def update_latest_pointer(self, run_id) -> None: ...

# 3) Run terminal status SSOT(每种状态机 1 套冻结集 + 判定函数)
class RunLifecycleStatus(str, Enum):
    """Run 生命周期的可观察状态。"""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

TERMINAL_RUN_STATUSES: frozenset[RunLifecycleStatus] = frozenset({
    RunLifecycleStatus.PAUSED,
    RunLifecycleStatus.COMPLETED,
    RunLifecycleStatus.FAILED,
    RunLifecycleStatus.CANCELED,
})
SUCCESS_RUN_STATUSES: frozenset[RunLifecycleStatus] = frozenset({RunLifecycleStatus.COMPLETED,})
FAILURE_RUN_STATUSES: frozenset[RunLifecycleStatus] = frozenset({
    RunLifecycleStatus.FAILED, RunLifecycleStatus.CANCELED,
})

def is_terminal(status: str | RunLifecycleStatus) -> bool: ...
def is_success(status: str | RunLifecycleStatus) -> bool: ...
def is_failure(status: str | RunLifecycleStatus) -> bool: ...

# 4) Execution outcome SSOT(给 step / phase / declarative 用 —— 取代所有 "completed/paused/failed/effect_uncertain" 字面)
class ExecutionOutcome(str, Enum):
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
    EFFECT_UNCERTAIN = "effect_uncertain"
    IN_PROGRESS = "in_progress"
    STOPPED = "stopped"

# 5) JSONable SSOT(单一来源,消重复)
def to_jsonable(value: Any) -> Any: ...   # 合并 _capture_io + journal/step/projector 两份
def provider_schema(tool: Any) -> dict | None: ...  # 工具 schema 序列化优先级最高
```

**关键**:`RunLifecycleStatus` **上提到 contracts**(干掉 `lca/plugins/transport/webserver/handlers/runs/session/session.py:53` 的本地 enum);`ExecutionOutcome` **新增 contracts 类**(干掉 5 处 Literal 字面);`to_jsonable` 单一入口。

### L2: 消费方迁移表(7 个 PR,按依赖顺序拆)

每个 PR 自带 acceptance criterion 子集 + 测试;根 note 在所有 PR merged 后升 `implemented/seam/`:

| PR | 改动 | 修复反模式 | 自带测试 |
|---|---|---|---|
| **PR-1** | `contracts/observability/ssot.py` 新增 + RunLocator Protocol 补 3 个方法 + `FilesystemRunLocator` 实现 | L1 全段 | unit test 全覆盖 |
| **PR-2** | `_capture_io.to_jsonable` + `journal/step/projector.py.to_jsonable` 合并到 ssot.to_jsonable;`_capture_io.py` 删;`projector.py` 改 import | 反模式 4 | 单测 |
| **PR-3** | `RunLifecycleStatus` 上提 contracts;删 `session/session.py:53` 本地 enum;`status.py` + `derive_terminal_status` 改委 ssot | 反模式 2b | 跨模块 import 回归 |
| **PR-4** | reader / writer / cli / declarative / projection 共 **30+ 处**改走 `is_terminal` / `is_success` / `is_failure` + `ExecutionOutcome` enum | 反模式 2a 全段 | 字符串回归(无新增裸字符串) |
| **PR-5** | `_scan_xref` / `step_tree_accumulator` / `replay/cursor` / `JournalDocumentWriter` / `failure.py` / `file_sink.py` 等所有 reader / writer 改走 RunLocator | 反模式 1 全段 | 集成测试 |
| **PR-6** | model_visible 拆 `LLMCallTrace` Protocol + `ModelVisibleProjector` 实现 + provider_schema 优先级 + capture_warnings | 反模式 3 | model_visible 单测 + 现状对比 |
| **PR-7** | `seam_key: str` 字面改 `CapabilityKey` enum;`plugin_meta.seam_keys` 同步 | 反模式 5 | 装配单测 |
| **PR-8** | L4 H-xref 退化 + 新 ADR 提案 `H-xref → H-ssot-readable` | L4 | doctor 单测 |

PR-1 ~ PR-5 是 SSOT 核心,可独立 ship;PR-6 / PR-7 依赖前面但可与 PR-3 / PR-4 互锁。

### L3: lint 守门(防止反模式重新出现)

新增 `scripts/check_observation_ssot.py`,CI 跑:

```bash
# 文件名硬编码(1a-1g)
rg '"events\.jsonl"' lca/ scripts/ tests/  | grep -v 'ssot.py\|naming.py\|run_locator_fs.py' → 0
rg '"journal\.json"' lca/ scripts/ tests/ | grep -v 'ssot.py\|run_locator_fs.py'             → 0
rg '"manifest\.json"' lca/ scripts/ tests/ | grep -v 'ssot.py\|run_locator_fs.py'            → 0
rg '"journal\.narrative\.md"' lca/ scripts/ tests/ | grep -v 'ssot.py\|run_locator_fs.py'    → 0
rg '"kernel\.log"' lca/ scripts/ tests/ | grep -v 'ssot.py'                                    → 0
rg '".*\.exceptions\.jsonl"' lca/ scripts/ tests/ | grep -v 'ssot.py\|file_sink.py'           → 0
rg '"profile_snapshot\.json"' lca/ scripts/ tests/ | grep -v 'ssot.py'                         → 0  # 字面数 ≤ 1

# Status 字面字符串(2a-2c)
rg 'in \{"success", "failed", "cancelled"' lca/ scripts/ tests/ | grep -v 'ssot.py'           → 0
rg 'in \{"completed", "paused", "failed"' lca/ scripts/ tests/ | grep -v 'ssot.py'           → 0
rg 'Literal\["completed", "failed", "paused"' lca/ scripts/ tests/ | grep -v 'ssot.py'        → 0
rg '== RoleStatus\.(DONE|FAILED)' lca/ scripts/ tests/ | grep -v 'role_status_rules\.py'      → 0

# 反向耦合(2b)
rg 'from lca\.plugins\.transport\.webserver\.handlers\.runs\.session\.session import RunStatus' lca/ scripts/ tests/ → 0

# to_jsonable 重复(反模式 4)
rg '^def to_jsonable' lca/ | wc -l = 1
```

`scripts/check_observation_ssot.py` 失败 = CI fail-loud。**PR 收口 + CI 守门** = 一次性保证。

### L4: H-xref 退化(配合 harness-spine-spec N1)

`_hop_h_xref` 当前 5 段 broken detection 改 1 段:
- 删:工具 / LLM / phase / manifest flush_errors 4 段(spine 与 journal 不一致由 L3 lint 在 write-time 拦)。
- 留:仅"spine SSOT 是否可读"sanity(对应 ADR-0176 D5 形变)。

新 ADR 提案 `docs/adr/H-xref-deprecation.md`(单 ADR,本 note 升级时同 PR)。

## Wire contract

### `lca/contracts/observability/ssot.py`(新增)

- `find_spine_file(run_dir, run_id) -> Path`
- `class RunLocator(Protocol)`:补 `kernel_log_path` / `exceptions_path` / `profile_snapshot_path` 3 个方法
- `class RunLifecycleStatus(str, Enum)`:7 个状态值
- `TERMINAL_RUN_STATUSES` / `SUCCESS_RUN_STATUSES` / `FAILURE_RUN_STATUSES` + 3 个 `is_*` 判定函数
- `class ExecutionOutcome(str, Enum)`:6 个 outcome 值
- `to_jsonable(value) -> Any`(合并 2 份) + `provider_schema(tool) -> dict | None`

### 修改文件

- `lca/contracts/observability/run_locator.py` Protocol 增 3 个方法
- `lca/infrastructure/observability/backends/run_locator_fs.py` 实现 3 个新方法
- `lca/plugins/transport/webserver/handlers/runs/session/session.py:53` 本地 enum 删,改 import
- `lca/infrastructure/observability/loop_cursor/_capture_io.py` `to_jsonable` 删
- `lca/infrastructure/observability/journal/step/projector.py` `to_jsonable` 删,改 import
- `lca/contracts/observability/model_visible_capture.py:ModelVisibleArtifact` 增 `messages_after_assistant` + `capture_warnings` 字段
- `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py` 拆:新增 `lca/contracts/observability/llm_call_trace.py`(Protocol)+ `lca/infrastructure/observability/projector/model_visible_projector.py`(实现)
- `lca/contracts/harness/composition/plugin.py:82/88/106` `seam_key: str` → `seam_key: CapabilityKey`

### 新增文件

- `lca/contracts/observability/llm_call_trace.py`(`LLMCallTrace` / `LLMCallInputs` / `LLMCallOutput` Protocol)
- `lca/infrastructure/observability/projector/model_visible_projector.py`
- `scripts/check_observation_ssot.py`(CI lint)
- `docs/adr/H-xref-deprecation.md`(L4 新 ADR)

## Alternatives considered

### Why not 每个 reader 一个 PR(8+ 个 PR)?

第一性原理违反。**8 个反模式是同一根因的 8 个症状**——L1 SSOT 注册表一次性建立,后续 PR 只是消费方迁移。拆碎 8 个 PR 等于 8 次相同的设计讨论、8 次合并冲突、8 次 lint 守门反复触发。

### Why not 只修 4 条 note 提到的 4 个 BUG,不扩大范围?

`AGENTS.md §1` 总闸 4 问第 3 问"现有 seam / Protocol / ADR 能否表达?"。**回答:能,而且已存在**(5 类反模式对应的 SSOT 都已存在)。既然修一个,就要修一类;否则下次同类 BUG 又要重新提案。

### Why not 把 SSOT 拆 5 个小文件而不是 1 个 ssot.py?

考虑过(每类 SSOT 一个文件)。否决:**反模式 1-5 都属"观测面 SSOT"**,合在一起更显式"一次性收口"的意图;拆 5 个文件会被理解成"5 个独立决策",反过来鼓励"再加一类时另开新文件"的习惯。1 个文件 + 5 段是"集中化 + 模块化"的最佳平衡。

### Why not 把 `to_jsonable` 放 `lca/contracts/`,不放在 `lca/infrastructure/`?

考虑过。否决:`to_jsonable` 不是契约,是工具;`lca/infrastructure/observability/ssot.py` 命名为 SSOT 的"运行时定义"更准确。契约(Protocol / Enum)放在 `contracts/`,实现放在 `infrastructure/`,跟 seam 分层一致。

### Why not 不修反模式 5(`seam_key: str`)?

可以推迟(影响面较窄)。否决:**`AGENTS.md §3` 不变量 C7"控制/观察分离"对 CapabilityKey 这种"控制契约"的字符串使用是显式禁令**。一次收口更彻底。

### Why not 不退化 H-xref(留 5 段 broken detection)?

否决。N1(Journal 唯一事实)与"H-xref 检测 spine 与 journal 不一致"在 SSOT 真生效后**互相矛盾**——H-xref 存在的全部理由是"writer 双写 + reader 双读",L1+L2+L3 落地后这前提消失。**留 H-xref 5 段 = 让代码继续撒谎**。

## Acceptance criteria

1. **`ssot.py` 单测覆盖**:每段至少 1 case。
2. **`find_spine_file` 4 case**:spine 命名存在 / legacy 存在 / 都存在(spine 优先) / 都不存在(raise FileNotFoundError)。
3. **`is_terminal` / `is_success` / `is_failure` 全集**:覆盖 `RunLifecycleStatus` 7 值 + 字符串变体。
4. **`ExecutionOutcome` enum 替代**:原 5 处 Literal 字段全消失,改 enum;新增 outcome 值时 grep 不到裸字符串。
5. **`RunStatus` 上提**:全 `rg "RunStatus\."` 不出现 `session.session` 来源。
6. **lint 守门**:`scripts/check_observation_ssot.py` 在 `lca/` `scripts/` `tests/` 跑通,且 9 条规则 0 命中。
7. **H-xref 退化后**:同一 run `H-xref.hops.spine_event_total` 等于真实 spine event 数;`H-xref.detail` 含 SSOT 可读性 hint(而非"journal ⇄ spine 一致")。
8. **`runs create --wait`** 在 run `status="completed"` 时 < 30s 退出。
9. **model_visible `messages.json`** 含至少 3 条 messages(user / assistant / tool)。
10. **`to_jsonable` 单一**:全 repo `rg '^def to_jsonable' lca/` = 1 命中。
11. **`seam_key: CapabilityKey`**:全 `rg 'seam_key: str' lca/contracts/` = 0 命中。

## Risks

- **PR 面铺到 5 个 seam**(contracts / observability / plugin / scripts / adr)+ 13 个文件类型改动 + 5 个协议新增。**必须按 L2 表拆 PR**,一次提交违反 `AGENTS.md §1` "契约改动必须同 PR 改实现 + 测试"。
- **`RunLifecycleStatus` 上提**会让 `session.py:53` 本地 enum 引用全失效;`lca/plugins/` import 该 enum 的位置(`status.py:11`、`materialization.py`、`api/query_endpoints.py` 等)需要同 PR 改。检索命令写在 acceptance #5。
- **`ExecutionOutcome` 新增**:删 5 处 Literal 时,有些 Literal 跟 `RunLifecycleStatus` 字段名重叠(`COMPLETED`);分清楚两套 enum 的**语义边界**(ExecutionOutcome 是 step/phase/declarative 内部 outcome,RunLifecycleStatus 是 run lifecycle 可观察状态),**不能合并**。
- **`H-xref` 退化**对应新 ADR;但 `docs/notes/README.md` 显式"老 ADR 不动"——新 ADR 在 `docs/adr/`,旧 ADR-0176 D5 不改。**新 ADR 必须明确说明形变语义**(从"一致性校验"→"可读性 sanity"),不能含糊。
- **lint 守门误伤**:`ssot.py` / `naming.py` / `run_locator_fs.py` 内部允许裸字符串(就是它们定义 SSOT)。lint 必须能区分"定义侧"与"消费侧"。

## Migration plan

PR-1 ~ PR-5 是 SSOT 核心(必发),PR-6 ~ PR-8 是增强(可独立发或合并)。根 note 在 PR-1 ~ PR-5 merged 后从 `proposed/seam/` 升 `implemented/seam/`(若还有 PR-6 ~ PR-8 pending,升 `Status: proposed — implementation in progress`)。

PR-1 提交后:**lint 守门**已经能跑且 fail-loud(只跑通会失败,因为现状不通过);后续每个 PR 让 lint 命中数减少,直至 PR-5 merged 后命中数 = 0。

## Open questions

- **`scripts/check_observation_ssot.py` 是新文件还是并入 `scripts/check_run_debug_sync.py`?**
  倾向新文件:`check_run_debug_sync.py` 是 run debug SOP 同步门禁,新 lint 守"SSOT 消费方",职责不同。但 `scripts/check_*.py` 现有结构需复核。
- **`model_visible` Projection 的 provider_schema 优先级,是 Provider 类加 `__provider_schema__()` 方法,还是统一由 LLM Resolver 装配时计算?**
  倾向 Provider 类方法:工具实例知道自己是哪个 provider,运行期才知道 schema;Resolver 装配时算会让工具 schema 与 profile patch 后注入的工具错位。
- **`ExecutionOutcome` 与 `RunLifecycleStatus` 是否合并?**
  倾向不合并:前者是"step / phase / declarative 单次执行的 outcome"(原子),后者是"run 整体 lifecycle 状态"(宏观)。强行合并会让"run 在 phase 失败时是 FAILED 还是 RUNNING"语义模糊。
- **`kernel_log_path` / `exceptions_path` 是新增到 RunLocator Protocol,还是只放 ssot.py?**
  倾向 Protocol(与现有 `journal_step_path` 等一致),但 `exceptions_path` 的文件命名是 `<run_id>.exceptions.jsonl`(run_id 派生),需要 Protocol 接受 run_id 入参。

## Related

### 根因 + 子 note

- 本 note(根):全量 SSOT 收口 + 约束保证
- [`docs/notes/proposed/contract/2026-09-03-doctor-h-xref-spine-filename.md`](../contract/2026-09-03-doctor-h-xref-spine-filename.md) — 反模式 1a 的子 note
- [`docs/notes/proposed/seam/2026-09-03-model-visible-incomplete-projection.md`](2026-09-03-model-visible-incomplete-projection.md) — 反模式 3 的子 note
- [`docs/notes/proposed/runbook/2026-09-03-runs-create-wait-hangs-on-completed.md`](../runbook/2026-09-03-runs-create-wait-hangs-on-completed.md) — 反模式 2a 的子 note

### 已有 SSOT(本 note 收口)

- `lca/contracts/observability/run_locator.py` — 8 方法,补到 11 方法
- `lca/contracts/observability/event_descriptor.py` — EP 派生
- `lca/contracts/observability/event_descriptor_registry.py` — EP 注册
- `lca/contracts/observability/cordis_event_table.py` — EP → cordis_name
- `lca/contracts/atoms/enums.py` — RoleStatus / SpanStatus / MessageRole / MemoryLayer / MemoryRecordKind / LLMStreamEventType
- `lca/contracts/models/team/role_status_rules.py` — RoleStatus 判定范式
- `lca/contracts/models/observability/diagnostic.py` — DiagnosticStatus
- `lca/contracts/models/core/lifecycle.py` — TaskStatus
- `lca/contracts/mechanisms/capability.py` — CapabilityKey
- `lca/contracts/harness/collaboration/agent.py` — LiveAgentStatus
- `lca/contracts/harness/tasks/task.py` — StepStatus
- `lca/contracts/harness/tasks/continuous.py` — WorkStatus
- `lca/contracts/harness/gate/result_verifier.py` — VerificationStatus
- `lca/contracts/protocols/think/learning.py` — LearningReviewTicketStatus

### ADR

- ADR-0065 §七 / ADR-0164 / ADR-0169 PR-27 L10 — RunLocator + spine 命名迁移
- ADR-0167 D11 — spine SSOT
- ADR-0176 D5 — H-xref(将形变,见 L4)
- ADR-2026-09-02 / ADR-0165 / ADR-0166 — journal / spine / step / segment 演化

### Spec

- `docs/specs/harness-spine-spec.md` §0 N1 — Journal 唯一事实
- `docs/architecture/optimization-iterations.md` — 历史迭代

### 反模式位置(本 note 一次性消除)

- `lca/infrastructure/cli/commands/runs.py:157` — 终态集硬编码
- `lca/plugins/transport/webserver/handlers/runs/doctor/step_check.py:71/107/550` — 文件名硬编码
- `lca/plugins/transport/webserver/handlers/runs/session/session.py:53` — plugin 反向引用
- `lca/contracts/protocols/declarative/declarative_execution.py:71/78` — Literal 字面
- `lca/harness/projection/web.py:71` — 终态集硬编码
- `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py:216/283/289/290` — writer 路径 + 终态字面
- `lca/infrastructure/observability/replay/cursor.py:57` — reader 路径
- `lca/plugins/transport/webserver/handlers/runs/terminal/failure.py:72` — kernel.log 路径
- `lca/infrastructure/observability/spine/sinks/file_sink.py:174` — exceptions 文件名
- `lca/plugins/transport/webserver/handlers/runs/session/diagnostics.py:32` + `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py:30` — 重复常量
- `lca/contracts/harness/composition/plugin.py:82/88/106` — seam_key: str 字面
- `lca/infrastructure/observability/loop_cursor/_capture_io.py:33` + `lca/infrastructure/observability/journal/step/projector.py:23` — to_jsonable 重复
- `lca/cognition/member_status/in_memory.py:54/55/63` + `lca/cognition/member_status/consult_policy.py:184` — RoleStatus 字面比较