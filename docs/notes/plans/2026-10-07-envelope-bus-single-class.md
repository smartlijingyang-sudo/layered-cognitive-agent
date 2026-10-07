# 事件总线单类收口 —— EnvelopeBus / EventBus 双名收敛

> **状态**：plans（待实施；实施后按 §复盘触发 收敛为 implemented Note 或归档）
> **日期**：2026-10-07
> **依据决策**：[ADR-0194 G6](../../adr/0194-cognitive-loop-architecture-convergence.md) · [ADR-0195 O4](../../adr/0195-platform-architecture-convergence.md)（两者均已 Accepted，本计划是其实施路径，不新开决策）
> **skill 链**：`lca-find-simplifications`（sweep）→ `lca-improve-codebase`（本文件）→ `lca-trim-cot-leakage`（PR-2/PR-3 prose）→ `lca-code-review`（standing rule）→ `lca-pre-push-checks`（每 PR 证据）

## 候选范围

事件机制承担一件事：接受一个经授权生产者投递的事件，给出回执，落盘，派发给订阅者。今天这件事被两个类名分持——名为 canonical 的那个能鉴权、能出回执，但不能落盘也不能派发；名为 compat 的那个承载全部落盘与派发路径。生产代码没有任何一处单独构造 canonical 类，进程拿到哪一个取决于哪个调用点先索取共享实例。

边界：`lca_kernel/events/bus/`（机制本体，L0 kernel 元层）及其 6 个代码位消费方（boot、manifest、hooks Protocol、pipeline_loader、`_session_publish`、webserver query_endpoints）。不跨认知闭集、不改事件词表、不改 Profile 拓扑。

主文件：[`lca_kernel/events/bus/bus.py`](../../../lca_kernel/events/bus/bus.py)（824 行）。

## 当前症状

每条症状给出 `file:line` 证据并绑定一条 standing rule。

### S1 · canonical 类无投递面，且零构造点

[`bus.py:181-350`](../../../lca_kernel/events/bus/bus.py) `EnvelopeBus`（170 行）的 `publish()`（[:226-278](../../../lca_kernel/events/bus/bus.py)）跑完 S1 鉴权 + S2 回执 + `published` 计数后直接 return，不触达 sink 也不触达订阅者。类内无 `subscribe` / `mount_sink` / `_sinks` / `_subscribers` / hook 链——四者全部只在 [`bus.py:486`](../../../lca_kernel/events/bus/bus.py) 起的 `EventBus`（453 行）上。

`git grep -n 'EnvelopeBus(' -- 'lca/**' 'lca_kernel/**' 'tests/**'` 唯一命中是 [`bus.py:181`](../../../lca_kernel/events/bus/bus.py) 的类定义本身：**生产与测试零构造点**。

违反 [AGENTS.md §1.5 规则 4](../../../AGENTS.md)「真正需要插件点的位置才抽（至少两个实现）」——这里只有一个实现，基类是 hypothetical seam。

### S2 · 进程单例的运行时类型取决于首个调用点

[`bus.py:331-342`](../../../lca_kernel/events/bus/bus.py) `default()` 把共享槽写成 `EnvelopeBus._default_instance = cls(registry)`，`cls` 由调用方决定。实测（`.venv/bin/python`，两次独立进程）：

| 首个调用 | `type(EnvelopeBus.default())` | `type(EventBus.default())` | `hasattr(bus,'subscribe')` | `hasattr(bus,'mount_sink')` |
|---|---|---|---|---|
| `EnvelopeBus.default()` | `EnvelopeBus` | `EnvelopeBus` | False | False |
| `EventBus.default()` | `EventBus` | `EventBus` | True | True |

两次返回同一对象。第一行的进程持有一个接受事件、出回执、投递数为零的总线；后续 `EventBus.default()` 拿到同一个空壳，`publish()` 静默不投递，`subscribe()` 抛 `AttributeError`。

[`bus.py:332-335`](../../../lca_kernel/events/bus/bus.py) 的 `NOTE(round-0390)` 记录了该设计已造成的一次缺陷（per-subclass shadow 使 `EventBus.set_default` 对 `EnvelopeBus.default()` 不可见）。同一根因第二次出现即上次未修到位（[AGENTS.md §1.5 规则 2](../../../AGENTS.md)）。

**当前为潜伏态**：三个 `EnvelopeBus.default()` 调用点分别在独立 CLI 进程（[`events_delivery.py:51`](../../../lca/infrastructure/cli/commands/ops/events_delivery.py)）、boot 之后的请求处理器（[`query_endpoints.py:614`](../../../lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py)）、L0 之后的 plugin setup（[`publisher.py:133`](../../../lca/plugins/events/publishers/model_visible/publisher.py)）。无生产路径在 boot 前索取单例。缺陷是结构性的，不是已发生的事故。

违反 C9 幂等/重入（[AGENTS.md §3](../../../AGENTS.md)）：启动与恢复的幂等边界不得靠"通常没事"。

### S3 · 声明的 canonical 类型无法表达真实实例

两处生产代码需要类型检查器压制才能描述自己持有的对象：

- [`boot.py:296`](../../../lca_kernel/boot/boot.py) — `bus: EventBus[Any] = EventBus.default()  # type: ignore[assignment]`
- [`_session_publish.py:44`](../../../lca/plugins/events/publishers/_session_publish.py) — 同一形态

[`hooks.py:114`](../../../lca_kernel/events/hooks/hooks.py) 的 `PublishContext.bus: EventBus` 只能用 compat 名表达 hook 契约。[`manifest.py:71`](../../../lca_kernel/events/manifest/manifest.py) 注释直书 `EventBus compat subclass required for register_pipeline until G6 delete-when`：boot 必须构造 compat 类，因为 canonical 类做不了这件事。

违反 [AGENTS.md §1.5 规则 7](../../../AGENTS.md)「类型标注完整」与 §4「用异常吞没、空 catch、隐式 fallback 掩盖契约缺失」。

### S4 · 三个方法体在基类与子类逐字重复

AST 比对（忽略 docstring）：`configure_delivery_policy`（[:287](../../../lca_kernel/events/bus/bus.py) vs [:596](../../../lca_kernel/events/bus/bus.py)）、`delivery_policy`（[:295](../../../lca_kernel/events/bus/bus.py) vs [:605](../../../lca_kernel/events/bus/bus.py)）、`delivery_snapshot`（[:279](../../../lca_kernel/events/bus/bus.py) vs [:585](../../../lca_kernel/events/bus/bus.py)）三对 body 全等。子类重写无任何行为差异。

`configure_delivery_policy` 的 `git grep` 生产调用点为零，仅 [`tests/lca_kernel/events/test_bus_delivery_receipt.py:254,256,263,302`](../../../tests/lca_kernel/events/test_bus_delivery_receipt.py) 使用。

违反 [AGENTS.md §1.5 规则 6](../../../AGENTS.md)「一起改的代码挨着放」——两份可独立漂移的同义 body。

### S5 · 空壳 publish 路径零测试覆盖

[`test_envelope_bus.py:27-34`](../../../tests/lca_kernel/events/test_envelope_bus.py) 的 `_make_envelope_bus()` 返回 `build_test_bus()`，而 [`events/test/catalog.py:73`](../../../lca_kernel/events/test/catalog.py) 的 `build_test_bus()` 返回 `EventBus(registry)`。名为「EnvelopeBus.publish 返回 4 字段 EnvelopeRef」的用例实际跑的是 `EventBus.publish`（6 字段 `EventRef`），其 `isinstance(ref, EnvelopeRef)` 断言经继承恒真；[:60-66](../../../tests/lca_kernel/events/test_envelope_bus.py) 的注释自认「此处用 hasattr 作弱断言」。

S1 的空壳路径无任何用例触达。违反 [AGENTS.md §1.5 规则 6](../../../AGENTS.md)「测试是设计的一部分」与 §5「每个 bugfix 至少一个回归测试」。

### S6 · 一个死构造形参是空壳单例的唯一进程内入口

[`hook.py:156-158`](../../../lca/plugins/events/hooks/model_visible/hook.py) 的 `ModelVisibleHook.__init__(*, bus: EnvelopeBus[Any])` 把参数存为 `self._bus`；`grep -n '_bus' hook.py` 唯一命中就是第 158 行的赋值——**从未被读**。[`publisher.py:133-134,138-147`](../../../lca/plugins/events/publishers/model_visible/publisher.py) 调 `EnvelopeBus.default()` 只为填这个形参，其自身注释已说明 `publish 不经 bus`。

违反 C6 最小化（[AGENTS.md §3](../../../AGENTS.md)）：原语默认 no-op，优先组合已有原语。

### S7 · G6 / O4 的 delete-when 按字面不可达，且窗口已过期

[`bus.py:7-9`](../../../lca_kernel/events/bus/bus.py) 的条件是 `rg '\bEventBus\b' lca/ lca_kernel/ --glob '!**/harness/**' --glob '!**/tests/**' --glob '!**/bus/**' = 0`；[ADR-0194:230](../../adr/0194-cognitive-loop-architecture-convergence.md) 的条件是「仅 harness」。两者都被 `lca/contracts/` 永久挡住：

- [`contracts/mechanisms/__init__.py:86`](../../../lca/contracts/mechanisms/__init__.py) `class EventBus(Protocol)` —— 一个 `emit` / `subscribe` / `drain` / `waterfall` / `serial` 形态的异步 Protocol，与 kernel 总线同名但无关
- 经 [`contracts/__init__.py:14`](../../../lca/contracts/__init__.py) 与 [`contracts/protocols/__init__.py:17,391`](../../../lca/contracts/protocols/__init__.py) 两处 barrel 再导出
- `git grep -nE '(:|->|\[)\s*EventBus\b'` 在类型位零命中；`git grep -n 'isinstance.*EventBus'` 生产零命中。唯一 `.serial(` 运行时调用是 [`hook_registry.py:106`](../../../lca/cognition/brain/gate/hook_registry.py) 作用于 Cordis `ctx.events`，未经该 Protocol 标注

窗口：`EnvelopeBus` 于 2026-09-06 落地（`git log -S'class EnvelopeBus' -- lca_kernel/events/bus/bus.py` → `291a55c0d`），[`events/__init__.py:5`](../../../lca_kernel/events/__init__.py) 与 [`bus.py:367-369`](../../../lca_kernel/events/bus/bus.py) 声明「30 天窗口」，2026-10-06 到期。窗口过期而条件不可达，正是 `lca-find-simplifications`「delete-condition 永不落地」的 shim 形态。

违反 [AGENTS.md §4](../../../AGENTS.md)「无 delete-when 的兼容分支 = 红灯」。

### S8 · 候选模块 prose 布满变更叙述

`grep -cE 'PR-[0-9]|本 PR|本类|原状迁移|推迟到|round-0|收口|迁移窗口|兼容 shim|compat' bus.py` → 25 处。样本：[:171](../../../lca_kernel/events/bus/bus.py)「本 PR 框架不实装删除路径」、[:196](../../../lca_kernel/events/bus/bus.py)「PR-2 接入 worker 后生效」、[:383](../../../lca_kernel/events/bus/bus.py)「全部从原 331 行原状迁移」、[:416-427](../../../lca_kernel/events/bus/bus.py)「与原 EventBus.publish 的差别：1. 2. 3.」、[:640](../../../lca_kernel/events/bus/bus.py)「详细 spec.fields 校验推迟到 PR-3」。

读者在 HEAD 无法解析「本 PR」「原 331 行」「PR-2/PR-3」。按 [`lca-trim-cot-leakage`](../../../.agents/skills/lca-trim-cot-leakage/SKILL.md) §LCA-specific leakage shapes 3/5，随 PR-2 一并重述为当前状态。

该 skill 的机械探针 `scripts/verify_doc_slop.py` 只扫 `docs/**/*.md`，对 `.py` 无覆盖（实测 `--root lca_kernel/events/bus` 仍报 `Scope: docs/**/*.md`）。本条的 25 处计数出自上面的 grep，验收靠人工读 + 同一 grep 归零，不靠脚本。

## 不变量（实施中不得破坏）

| 名称 | 守护点 |
|---|---|
| I-FW-BUS-1 producer 唯一入口 | [`tests/architecture/test_event_bus_invariants.py:119`](../../../tests/architecture/test_event_bus_invariants.py) |
| I-FW-BUS-2 consumer 唯一入口 | 同上 `:192` |
| I-FW-BUS-3 自定义逻辑只经 Pipeline + 4 hook + SinkBackend | [`bus.py:557`](../../../lca_kernel/events/bus/bus.py) `register_pipeline` 签名不变 |
| I-FW-BUS-4 业务不订阅 `event.bus.dispatch.*` | [`bus.py:_emit_self_observation`](../../../lca_kernel/events/bus/bus.py) 内部路径不变 |
| C11 事件闭集 | 本计划不增删任何 EP 名 / `Category` 成员 / `EXECUTION_POINTS` 条目 |
| C3 事实可追溯 · ADR-0186 Session SSOT | [`_session_publish._authorize_producer`](../../../lca/plugins/events/publishers/_session_publish.py) 的 `registry.can_publish` 鉴权与 `Session.append` 单轨不变 |
| C5 能力单调 | `EventRegistry.can_publish` 矩阵与 yaml 白名单不变 |
| C7 控制/观察分离 | `delivery_snapshot()` 保持只读投影，不触发控制面副作用 |
| C8 确定性 | trace_id 解析链（显式参数 → `payload.trace_id` → ambient contextvars → `new_id("trc")`）不变 |
| C13 信息血统闭合 | `SpineEventRecord` 10 键布局与 [`spine/runtime.build_record(payload, ref: EnvelopeRef)`](../../../lca_kernel/events/spine/runtime.py) 签名不变 |
| 五层单向依赖 | `lca_kernel` 不 import `lca.application`；`contracts` 不因本计划新增实现层依赖 |
| Plugin manifest 契约 | `provides=["event.bus"]` / `requires=[]` / `effects="none"` / `emits=("event.bus.boot",)` 不变 |
| 回执 wire 形态 | [`bind.py:75-85`](../../../lca/session/lifecycle/bind.py) `_event_ref_from_session` 返回的 6 字段 `EventRef` 不变（见 §范围外 R1） |

## PR 列表（3 个，各自可独立推送与回滚）

### PR-1 · 删除死依赖与三份重复 body（不改名）

**动机**：先摘掉零风险的两块，使 PR-2 的 diff 只剩类合并本身。

**文件**：
- [`lca/plugins/events/hooks/model_visible/hook.py`](../../../lca/plugins/events/hooks/model_visible/hook.py) — 删 `__init__` 的 `bus` 形参与 `self._bus`
- [`lca/plugins/events/publishers/model_visible/publisher.py`](../../../lca/plugins/events/publishers/model_visible/publisher.py) — 删 `EnvelopeBus.default()` 调用、`_build_hook(bus=...)` 形参、相关 lazy import
- [`lca_kernel/events/bus/bus.py`](../../../lca_kernel/events/bus/bus.py) — 删 `EventBus` 侧三份与基类全等的重写（`:585`、`:596`、`:605`），改为继承
- [`tests/plugins/events/publishers/model_visible/test_publisher.py`](../../../tests/plugins/events/publishers/model_visible/test_publisher.py) — 4 处 `ModelVisibleHook(bus=bus)` / `_build_hook_fixture(bus)` 去参；`EventBus.set_default(bus)` 保留（鉴权仍经 `default().registry`）

**验收**：
1. `grep -n '_bus' lca/plugins/events/hooks/model_visible/hook.py` 零命中
2. `git grep -n 'EnvelopeBus.default()' -- 'lca/plugins/events/**'` 零命中。[`query_endpoints.py:614`](../../../lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py) 是 `/health` 的真实消费方，保留；PR-2 单类收口后它成为唯一正确的调用形态
3. `configure_delivery_policy` / `delivery_policy` / `delivery_snapshot` 在 `bus.py` 各只剩一处 `def`
4. `pytest tests/lca_kernel/events/ tests/plugins/events/publishers/model_visible/ --no-cov` 零失败（基线 252 passed + 16 passed）
5. 新增回归测试：`ModelVisibleHook()` 无参可构造，且 `capture_pre_llm` 行为与去参前逐字段相同

**Delete-when**：无。本 PR 不引入 shim、并行 schema 或迁移路径。

**证据集**（`lca-pre-push-checks`「Single module implementation」+「Delete a shared symbol」）：`ruff check --fix` + `ruff format` 上述 4 文件；上述 pytest；`vulture lca/plugins/events --min-confidence 80`。

---

### PR-2 · 单类收口：投递面并入 `EnvelopeBus`，删除 `EventBus` 类

**动机**：消除 S1/S2/S3/S5。存活名取 `EnvelopeBus`——[ADR-0194:230](../../adr/0194-cognitive-loop-architecture-convergence.md) 与 [ADR-0195:222](../../adr/0195-platform-architecture-convergence.md) 已把收敛目标定为 `EnvelopeBus`；老 ADR 不动，本 PR 满足其条件。

**文件**：
- [`lca_kernel/events/bus/bus.py`](../../../lca_kernel/events/bus/bus.py) — `EventBus` 的 `__init__` 字段、`publish`、`subscribe`、`subscribe_self_observation`、`mount_sink`、`register_pipeline`、`_dispatch_sinks`、`_fanout`、`_run_pre_dispatch`、`_run_post_dispatch`、`_emit_self_observation`、`_run_failure_hooks`、`_validate_schema`、`_has_declared_subscribers` 全部并入 `EnvelopeBus`；删 `class EventBus`；`__all__` 去掉 `"EventBus"`；删 `:7-9` 与 `:367-369` 两处 COMPAT 标记；删 `:332-335` `NOTE(round-0390)`（其保护的 shadow 缺陷随单类消失）；`default()` 的 `cls(registry)` 保持，此时 `cls` 恒为 `EnvelopeBus`
- 代码位消费方 6 处：[`boot.py:294-296`](../../../lca_kernel/boot/boot.py)（去 `# type: ignore[assignment]`）、[`manifest.py:66-77`](../../../lca_kernel/events/manifest/manifest.py)、[`hooks.py:114`](../../../lca_kernel/events/hooks/hooks.py)、[`_session_publish.py:41-44`](../../../lca/plugins/events/publishers/_session_publish.py)（去 `# type: ignore[assignment]`）、[`query_endpoints.py:519-521`](../../../lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py)、[`pipeline_loader.py:45,169-204`](../../../lca/harness/profile/resolve/pipeline_loader.py)
- [`lca_kernel/events/__init__.py`](../../../lca_kernel/events/__init__.py) — 删 `EventBus` 导入与 `__all__` 条目，重写 `:4-13` 公开面 docstring
- [`lca_kernel/events/test/catalog.py:16,54-73`](../../../lca_kernel/events/test/catalog.py) — `build_test_bus()` 返回类型与构造改为单类
- **名字字面量守护同步更新（否则不变量静默失效）**：
  - [`tests/architecture/test_fold_no_io.py:295`](../../../tests/architecture/test_fold_no_io.py) — 字面构造禁令 `node.func.id == "EventBus"` 改为 `"EnvelopeBus"`
  - [`tests/architecture/test_assistant_routes_invariants.py:179`](../../../tests/architecture/test_assistant_routes_invariants.py) — 禁词表加 `"EnvelopeBus.publish"`
- [`tests/lca_kernel/events/test_envelope_bus.py`](../../../tests/lca_kernel/events/test_envelope_bus.py) — 重写：删 `isinstance(bus, EventBus)`（`:76`）与 `TestEventBusCompatShim` 类名，断言改为「publish 抵达已 mount 的 sink」与「publish 抵达已 subscribe 的 callback」

**验收**：
1. `git grep -n 'class EventBus' -- 'lca_kernel/**'` 零命中
2. `git grep -c 'type: ignore\[assignment\]' -- lca_kernel/boot/boot.py lca/plugins/events/publishers/_session_publish.py` 零命中
3. `bus.py` 中 `def publish` / `def delivery_snapshot` / `def configure_delivery_policy` / `def delivery_policy` 各恰好一处
4. **S2 复现脚本转为回归测试**：新进程内先调 `EnvelopeBus.default()`，断言返回实例具备 `subscribe` 与 `mount_sink`，且一次 `publish` 使已 mount 的 sink 收到一条 `SpineEventRecord`
5. **空壳路径不可表达**：`EnvelopeBus` 无任何"只鉴权不投递"的公开入口
6. `pytest tests/lca_kernel/events/ tests/architecture/test_event_bus_invariants.py tests/architecture/test_fold_no_io.py tests/architecture/test_assistant_routes_invariants.py --no-cov` 的失败集不超出 §基线失败协议 记录的既有失败（本计划触及的四个守护文件基线为 1 failed / 43 passed / 1 skipped，唯一失败是 `TestIFwBus2::test_i_fw_bus_2_subscribe_outside_framework_blocked`）；`pytest tests/architecture/ --no-cov` 失败数不超过基线 52
7. `python scripts/check_protocol_impl.py` 的 issue 数不超过基线 42（`PublishContext.bus` 类型变更后 Protocol↔impl 配对不新增缺口）
8. `bus.py` 内 §S8 列出的 25 处变更叙述按 `lca-trim-cot-leakage` 重述为 HEAD 可解析的当前状态；ADR 编号引用按 keep rule 保留。机械门：`grep -cE '本 PR|原状迁移|推迟到|round-0|迁移窗口' lca_kernel/events/bus/bus.py` 返回 0（`PR-[0-9]` 与「收口」在 ADR 引用语境下属 keep rule，逐条人工判定）

**Delete-when**：无。`EventBus` 类与其两处 COMPAT 标记在本 PR 内删除，不留过渡别名（[AGENTS.md §4](../../../AGENTS.md)「引入兼容 shim 的同一 PR 必须同时删除它」）。

**证据集**（`lca-pre-push-checks`「`lca_kernel/`」+「Contracts / Protocol」）：`ruff check --fix` + `ruff format`；`lint-imports`；`mypy lca`；`python scripts/check_kernel_boundary.py`；`python scripts/check_protocol_impl.py`；`pytest tests/lca_kernel/ tests/architecture/ tests/plugins/events/ --no-cov`；`vulture lca_kernel --min-confidence 80`。

---

### PR-3 · 词表收敛 + 关闭 G6 / O4 delete-when

**动机**：PR-2 之后代码位已无 `EventBus`，但 103 处 prose 与一个同名 contracts Protocol 使 G6 / O4 的 grep 无法归零。本 PR 只做「让 grep 归零」这一件事。

**文件**：
- prose 收敛：`git grep -l '\bEventBus\b' -- 'lca/**/*.py' 'lca_kernel/**/*.py'` 的 33 个文件（约 103 处 docstring / 注释 / plugin `description=` 字符串）统一改为 `EnvelopeBus`。已确认低风险：[`test_event_bus_invariants.py`](../../../tests/architecture/test_event_bus_invariants.py) 的 I-FW-BUS-1/2 守护的是调用模式（`_spine.append(` / `event_spine.append(` / `.subscribe(`）与路径白名单，不依赖类名字面量，仅其 docstring 需同步
- contracts 同名 Protocol：删 [`contracts/mechanisms/__init__.py:86-112`](../../../lca/contracts/mechanisms/__init__.py) 的 `EventBus(Protocol)` 及 [`contracts/__init__.py:14`](../../../lca/contracts/__init__.py)、[`contracts/protocols/__init__.py:17,391`](../../../lca/contracts/protocols/__init__.py) 三处导出；同步改 [`contracts/mechanisms/__init__.py:4,9`](../../../lca/contracts/mechanisms/__init__.py) 的边界判定 prose
- [`docs/specs/glossary.md`](../../specs/glossary.md) · [`docs/specs/architecture.md`](../../specs/architecture.md) · [`lca_kernel/README.md:38`](../../../lca_kernel/README.md) — 术语条目对齐（`docs/adr/` 与 `docs/notes/archived/` 不动）

**验收**：
1. **G6 / O4 归零门**：`rg '\bEventBus\b' lca/ lca_kernel/ --glob '!**/harness/**' --glob '!**/tests/**' --glob '!**/bus/**'` 退出码 1（零命中）
2. `rg '\bEventBus\b' lca/ lca_kernel/` 剩余命中仅出现在 harness 白名单内或为零
3. contracts Protocol 删除前先跑门：`git grep -nE '(:|->|\[)\s*EventBus\b' -- 'lca/**'` 与 `git grep -n 'isinstance.*EventBus' -- 'lca/**' 'lca_kernel/**'` 均零命中。**若任一返回命中，本 PR 改为把该 Protocol 重命名为其实际形态（异步 emit / waterfall / serial 发射面）而非删除**——两条路径都满足验收 1
4. `pytest tests/contracts/test_protocols_package_contract.py --no-cov` 全绿（`__all__` 由 import 派生，删除导出后自动收敛）
5. 三个文档门禁的失败集不超出 §基线失败协议 记录值：`python scripts/verify_md_links.py`（基线 123 broken）、`python scripts/verify_doc_budgets.py`（基线 2 over budget）、`python scripts/check_doc_layering.py`（基线 exit 1）。三者当前均 exit 1，验收标准是「本 PR 不新增任何一条」，逐条对比输出而非看退出码
6. `git diff --check` 干净

**Delete-when**：无。本 PR 结束时 `lca_kernel/events/bus/` 不再存在任何兼容分支、并行名或迁移窗口。

**证据集**（`lca-pre-push-checks`「Contracts / Protocol / enum / registry」= 全量验证）：`ruff check --fix .` + `ruff format .`；`lint-imports`；`mypy lca`；`pytest`；`vulture lca --min-confidence 80`；`check_protocol_impl.py` / `check_no_any.py` / `check_kernel_boundary.py` / `check_package_contracts.py`；上述文档三脚本。

## 基线失败协议

按 [AGENTS.md §6](../../../AGENTS.md)，以下失败在 2026-10-07 `raphy/arch-20261007-0930`（`9f731f034`）上**已存在**，三个 PR 均不得使其变差，也不得把「全量通过」写进报告：

| 命令 | 基线结果（2026-10-07 实测） |
|---|---|
| `pytest tests/lca_kernel/events/ --no-cov` | 252 passed（干净） |
| `pytest tests/plugins/events/publishers/model_visible/ --no-cov` | 16 passed（干净） |
| `pytest tests/architecture/test_event_bus_invariants.py tests/architecture/test_fold_no_io.py tests/architecture/test_assistant_routes_invariants.py tests/contracts/test_protocols_package_contract.py --no-cov` | 1 failed / 43 passed / 1 skipped；唯一失败 `TestIFwBus2::test_i_fw_bus_2_subscribe_outside_framework_blocked` |
| `pytest tests/architecture/ --no-cov` | 52 failed / 661 passed / 12 skipped |
| `lint-imports` | exit 1 |
| `python scripts/check_kernel_boundary.py` | exit 1，1/3 通过；`tests/lca_kernel/test_boot_events_emitted.py` 2 failed / 513 passed（`BootProfileResolved` 未发射）+ importlinter 循环依赖 |
| `python scripts/check_package_contracts.py` | exit 1，60 issues / 82 packages |
| `python scripts/check_protocol_impl.py` | exit 1，42 issues |
| `python scripts/check_no_any.py` | exit 1（无汇总计数，验收逐条 diff 输出） |
| `pytest tests/scenario/code/test_code_conventions.py::TestFileLineCountLimit --no-cov` | 1 failed（基线提交 `81221a945` 上即失败：`lca/infrastructure/observability/loop_cursor/projection/host.py` 258 行有效代码 > 阈值 250）。与本计划无关，不修 |
| `python scripts/verify_md_links.py` | exit 1，123 broken links |
| `python scripts/verify_doc_budgets.py` | exit 1，2 documents over budget |
| `python scripts/check_doc_layering.py` | exit 1 |
| `python scripts/check_notes_tree.py` | exit 1，23 errors |

`tests/architecture/` 与 `tests/contracts/test_protocols_package_contract.py` 是本计划三个守护点的所在套件，其既有失败必须在 PR-2 开工前逐条记录，验收只比对失败集增量。

每个 PR 的报告必须逐项区分「本次引入」与「既有失败」，只有退出码为 0 的命令才能写为「通过」。

## 复盘触发

每个 PR 落地后：

1. 跑 [`lca-audit-notes`](../../../.agents/skills/lca-audit-notes/SKILL.md)（`./scripts/lca-ops notes-audit`）；本计划触及 `contracts` 与 `lca_kernel/events/`，额外跑 `python scripts/audit_adr_health.py` 并复查入链
2. 复查两条已 Accepted 决策的退役项状态：[ADR-0194 §G6](../../adr/0194-cognitive-loop-architecture-convergence.md) 与 [ADR-0195 §O4](../../adr/0195-platform-architecture-convergence.md)。**老 ADR 正文不改**；PR-3 验收 1 通过后，在两处退役项的现有跟踪位置记录条件已达成
3. 用实际结果回填本文件的 PR 段（commit SHA、验收逐条实测输出、基线对比），然后把本文件收敛为 `docs/notes/implemented/seam/` 下的一条 Note，或按 [`lca-archive-notes`](../../../.agents/skills/lca-archive-notes/SKILL.md) 判定归档
4. [`docs/notes/implemented/runbook/2026-09-03-event-bus-pr-matrix.md`](../implemented/runbook/2026-09-03-event-bus-pr-matrix.md) 与 [`docs/notes/implemented/seam/2026-09-03-event-bus-chain-wired.md`](../implemented/seam/2026-09-03-event-bus-chain-wired.md) 描述的是当前真实状态，若其 `EventBus.*` 方法名引用随 PR-2 失效，在同一 PR 内更新（[AGENTS.md §5](../../../AGENTS.md) 变更闭环）

## 范围外（各自需要独立一轮）

**R1 · `EventRef` 6 字段回执收敛。** [`bus.py:101-113`](../../../lca_kernel/events/bus/bus.py) 的 `EventRef(EnvelopeRef)` docstring 自称「外部零引用」，`persisted` / `subscriber_count` 在生产代码中确无读取点（`git grep -n '\.persisted\b\|\.subscriber_count\b'` 的命中全部是无关的 `approval.persisted.v1` 事件名与 Session tail 订阅计数）。但 [`bind.py:75-85`](../../../lca/session/lifecycle/bind.py) `_event_ref_from_session` 在生产构造 6 字段 `EventRef`，[`run_session_writer.py:26,168`](../../../lca/runtime/session/run_session_writer.py) 跨模块导入该私有名。收敛会改 Session 桥的回执形态，属 ADR-0186 边界，不与本计划同 PR。

**R2 · `run_session_writer.py` 导入私有名 `_event_ref_from_session`。** 跨模块导入下划线名违反 [`lca-trim-cot-leakage`](../../../.agents/skills/lca-trim-cot-leakage/SKILL.md) 引用的 internal-seam 不外泄原则；应把该构造函数升为 `bind.py` 的公开面或迁到调用方。与 R1 同一轮处理。

**R3 · `configure_delivery_policy` 零生产调用点。** PR-1 去掉重复 body 后仍是一个只有测试使用的公开旋钮。按 [AGENTS.md §1.5 规则 6](../../../AGENTS.md)「每个新依赖/抽象/配置项必有 owner + delete-when」，需要 owner 与删除条件，或接入生产装配（[ADR-0184 PR-C](../../adr/0184-event-lifecycle-managed-delivery.md) 的 `strict=True` 翻转）。属行为决策，不是清理。

**R4 · [ADR-0195:222](../../adr/0195-platform-architecture-convergence.md) 的路径笔误。** O4 行写作 `lca_kernel/events/bus.py`，实际为 `lca_kernel/events/bus/bus.py`。老 ADR 不动，此条仅记录。
