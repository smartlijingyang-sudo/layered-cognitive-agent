# ADR-0290: 三违规类名仲裁（DesktopLockManager / SpineHandler / ReclaimInfo）

> **Status: Proposed**（2026-10-05 起草）
> 本提案裁决三个被 `test_no_banned_class_name_patterns` 健身函数红钉的类名：
> 两个改名（归 quality lane 实施），一个豁免（本 ADR 即宪法规定的豁免归档）。
> **未改动任何代码与文档现状**；改名与豁免登记实施后，本 ADR 可由李超裁决转为 Accepted/Implemented。

## 1. Context（发现）

2026-10-05 iter-tests 08:09 轮（`e53659c2a`，todo-53）删除了 `tests/scenario/code/test_code_conventions.py`
中自引入起恒空的 `"gateway"` 扫描条目后，`test_no_banned_class_name_patterns` 健身函数
**首次真正执行**，揭出 3 个真实命名违规（此前该测试被空心条目掩盖）：

| 类名 | 位置 | 引入时间 | 引用数（lca+tests+docs） |
|---|---|---|---|
| `DesktopLockManager` | `lca/infrastructure/computer/desktop_lock.py` | 2026-09-24 | 18 |
| `SpineHandler` | `lca/infrastructure/observability/spine/registry/registry.py` | 2026-09-06 | 18 |
| `ReclaimInfo` | `lca/application/routine/locks.py` | 2026-10-03 | 9 |

裁决依据：`docs/design/naming-constitution.md`（ADR-0106 命名宪法）§4.1 角色后缀强制词表、
§4.3 禁止后缀、§13 Phase E（豁免归档规则）。

## 2. 裁决

### 2.1 DesktopLockManager → 改名 DesktopLockCoordinator（改名，quality lane）

宪法 §4.3：`Manager` 后缀太泛，"改用 `Coordinator` / `Registry` / `Driver`"。
该类职责：为多个 agent 协调单屏桌面独占锁的分配/释放/TTL 回收（`allocate_window` / `freeWindow`，
120s 超时自动回收防死锁）——正是"跨组件协调生命周期或流程"的 Coordinator 语义。
先例：原命名规范迁移表 `ActivationManager` → `SubagentActivationCoordinator`。

引用 18 处（含 `lca/infrastructure/browser/subagent.py` 生产引用、
`tests/scenario/adr0248/` ADR-0248 闭环测试）。按命名规范迁移原则同步改源码+测试+导出列表+
docs 引用（当前 docs 无直接类名引用，无 drift 债务），**不保留旧名别名**。

### 2.2 SpineHandler → 豁免（本 ADR 即豁免归档；实施归 tests lane）

宪法 §4.1：`Handler` 是**合法**角色后缀，语义"处理单个请求"，先例
`ActionHandler` / `DeltaHandler` / `CommandHandler`；附录 A.1 快速决策表：
"处理单事件 → `<Subject>Handler`"。
`SpineHandler` 恰是"每 EP（execution point）一个 handler"的注册语义（ADR-0165.1 Layer-1，
`SpineRegistry` 每 EP 绑定一个 `wrap_fn` + `target_module`）——健身函数正则属**误杀**，
不是真违规。

宪法 §13 Phase E 要求"**在 ADR 中归档所有豁免和过渡态**"——本节即该归档：
豁免仅保 `SpineHandler` 这一例，不延伸为"Handler 后缀随便用"。

实施（tests lane，**以李超拍板本 ADR 为前置**）：
`_NAME_EXEMPT` 登记 `"SpineHandler"` + 理由（宪法 §4.1 Handler 合法后缀，每 EP 单请求处理）；
同时修正该测试注释中 stale 的豁免登记指向——注释写"在 docs/specs/glossary.md 命名约定章节登记"，
但 `glossary.md` 已无"命名约定"章节（实证：全文件 0 命中），规则已并入
`docs/design/naming-constitution.md`，豁免归档按宪法 §13 在 ADR，不在 glossary。

### 2.3 ReclaimInfo → 改名 ReclaimTrace（改名，quality lane）

宪法 §4.3：`Info` / `Data` 作后缀禁止，"必须改成具体领域名词"。
类自身 docstring 定义："Trace left by a stale-lock reclaim"；
ADR-0263 C2 要求"reclaim 留下 trace、**永不沉默**"——`ReclaimTrace` 与契约语言逐字一致，
是该类的真实领域名词。

引用 9 处（`lca/application/routine/__init__.py` 导出 + 内部调用方）。
按迁移原则同步改，不保留旧名别名。

## 3. 实施清单（均以李超拍板本 ADR 为前置）

1. quality lane：`DesktopLockManager` → `DesktopLockCoordinator`（18 处引用+导出列表+相关测试）。
2. quality lane：`ReclaimInfo` → `ReclaimTrace`（9 处引用+导出列表）。
3. tests lane：`_NAME_EXEMPT` 登记 `SpineHandler` 豁免理由 + 修正 stale 注释指向（§2.2）。

## 4. 诚实边界

- 本 ADR 为 Proposed：**不改变任何现状**，改名/登记未落地前 tests 仍红是**设计意图的红**
  （健身函数正在起作用），不洗绿。
- 三项裁决的完整证据链：宪法原文引用（§4.1/§4.3/§13 Phase E）、引用数实证、
  各类 docstring 与 ADR 交叉验证（0263 C2 / 0165.1 Layer-1），见上。
- 豁免登记与改名若与李超后续工作冲突（如他正在改这些文件），以他的版本为准，arch 不强行推进。
