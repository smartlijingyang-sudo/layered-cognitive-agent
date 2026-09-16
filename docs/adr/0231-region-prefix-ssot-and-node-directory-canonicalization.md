# ADR-0231 — Region prefix SSOT = `lca/nodes/<region>/` 目录名（无冒号）

**Status:** Accepted — 2026-09-16. 同 PR 落地。

> **一句话**：节点物理目录 `lca/nodes/<region>/` 即 region SSOT。plugin `@plugin(provides=...)` 前缀必须等于该目录名（无冒号前缀）；bundle YAML 的 `region:` 字段同样必须等于该目录名。把 ADR-0228 §节点形态明示的规则升为 contract + fail-loud 校验，并清理由 `phase:think::` / `region:intervene::` / `concept::(lca/nodes/act/*.py)` 三类错位导致的 4 处 `debug-factories missing` 根因。

**Refines / Fixes:**
- ADR-0228 §节点形态 — 已规定 `provides=("<region>::<id>",)` 无冒号前缀，但未 enforce；本 ADR 把"应等于物理目录名"补完。
- ADR-0210 §6.6 — `profile.regions.declare` 解析机制已存在但无 enforce；本 ADR 不扩展其 schema，仅在 `bundle region` / `plugin provides` 层 fail-loud（profile 顶层 declare 留待独立 follow-up）。
- ADR-0220 §3 三层图 schema — `concept.*` / `primitive.*` / `agent.*` 是 **bundle 路径前缀**（不是 plugin namespace prefix）；本 ADR 把这条区分明确写进契约。

## Problem

LCA 当前处于"lca/nodes 目录迁移中期"：物理目录已就位（`lca/nodes/{think,act,perceive,reflect,remember,stop,concept,primitive,intervene,delegate,plan,loop}/`），但 plugin `provides=` 字符串前缀与目录名不一致。`debug-factories` 报告的 4 处 missing 只是同一根因的 4 个实例。

### 现状（修复前实测）

| 物理目录 (`lca/nodes/<region>/`) | plugin `provides=` 前缀 | 一致性 |
|---|---|---|
| `think/` | `phase:think::` (12 个) | ❌ 带冒号 |
| `perceive/` | `phase:perceive::` (2 个) | ❌ 带冒号 |
| `reflect/` | `phase:reflect::` (2 个) | ❌ 带冒号 |
| `remember/` | `phase:remember::` (2 个) | ❌ 带冒号 |
| `intervene/` | `region:intervene::` (3 个) | ❌ 带冒号 |
| `plan/` | `region:plan::` (2 个) | ❌ 带冒号 |
| `delegate/` | `delegate::` (1) + `region:delegate::` (2) | ❌ 自身不一致 |
| `act/` | `concept::` (6 个) | ❌ **完全错位**（act 目录挂 concept 前缀） |
| `concept/` | `concept::` (27 个) | ✅ |
| `stop/` | （空） | — |
| `loop/` | 不走 provides=，用 GRAPH_NODE_EXECUTORS capability | ✅ |

`debug-factories` 报 missing 的 4 处：

```
✗ bundles/concept/history_assemble.yaml::history.derive
   region='concept' tried=['concept::history.derive', 'concept::history.derive.ref']
✗ bundles/concept/llm_dispatch.yaml::llm.call
   region='concept' tried=['concept::llm.call', 'concept::llm.call.ref']
✗ bundles/concept/decision_parse.yaml::decision.parse
   region='concept' tried=['concept::decision.parse', 'concept::decision.parse.ref']
✗ bundles/outer/phase_main.yaml::act.approve.gate
   region='phase:intervene' tried=['phase:intervene::act.approve.gate', 'phase:intervene::act.approve.gate.ref']
```

实际 plugin 提供 key：

```
phase:think::history.derive      (lca/nodes/think/history/assemble.py)
phase:think::llm.call            (lca/nodes/think/dispatch/llm.py)
phase:think::decision.parse      (lca/nodes/think/decision/parse.py)
region:intervene::act.approve.gate  (lca/nodes/intervene/approve_gate.py)
```

bundle 写 `region: concept` / `region: phase:intervene` 是**与 plugin 完全不存在的拼盘**。Production runtime 现在不出错，是因为 `resolve_node_executor_bindings` 只取 `key.rsplit("::", 1)[-1]`（factory 名），不看 region 前缀；但 debug / capability graph / SSOT 矩阵都会把这些 mismatch 暴露成 `missing`。

### 根因

ADR-0228 §节点形态明示：

```python
region: str = "<region>"  # 物理目录名（无冒号）
provides=("<region>::<sub-group>.<node>",)
```

但实施时**两层偏差**累积：
1. ADR-0210 P7 阶段标签机制遗留 `phase:<name>` 前缀（仍合法用于 region tag 标注），被人误复用为 plugin namespace prefix。
2. ADR-0220 §3 三层图 (`primitive.*` / `concept.*` / `agent.*`) 是 **bundle 路径分类**（不是 plugin namespace），但 act/ 目录下 6 个 plugin 被错挂到 `concept::` prefix（物理 act，namespace concept）。

**ADR-0228 §节点形态是契约**，本 ADR 把"按物理目录名校验"升为 fail-loud，杜绝再次漂移。

## Decision

### D1 — Region SSOT

节点 region = `lca/nodes/<region>/` 顶层目录名（无冒号、无 `phase:` / `region:` 前缀）。region 集合由**文件系统的当前实际目录**决定（而非写死 enum），新增 region = 新建目录 + 在 `lca/nodes/README.md` 说明。

当前 region 集合（2026-09-16 快照）：`{think, act, perceive, reflect, remember, stop, concept, primitive, intervene, delegate, plan, loop}`。

### D2 — RegionPrefix enum 是视图，不是 SSOT

`lca/contracts/atoms/enums/region_prefix.py::RegionPrefix` 是对 `lca/nodes/` 目录的**只读视图**。`RegionPrefix.parse(s)` 接受字符串返回 enum，未知字符串抛 `UnknownRegionPrefixError`（Pydantic-style fail-loud）。**该 enum 不替代文件系统**，但提供：

- 类型化校验（debug-factories 区分 `unrecognized_region` 与 `factory_missing`）。
- 静态扫描脚本的查表。

### D3 — plugin `provides=` 必须等于 `<region>::<id>`，region == 物理目录名

`scripts/check_plugin_region_prefix.py` 扫所有 `lca/nodes/**/*.py` 的 `@plugin(provides=(...))`：

- 每条 `provides` 字符串 split `::` 第一段必须 ∈ `RegionPrefix.values()`。
- 第一段必须等于文件相对 `lca/nodes/` 的**第一层目录名**。
- 任何偏差 → fail-loud（CI exit 1）。

### D4 — bundle YAML `region:` 字段必须 ∈ RegionPrefix

`debug-factories` 改造：当前 `walk_bundle` 取 node.region + node.factory 拼 candidates 查 `factory_index`。改造后：先把 `node.region` 走 `RegionPrefix.parse`，未识别 → 报 `unrecognized_region`（不再悄悄报 `factory_missing`）。

### D5 — region 命名禁用 `:` 前缀

`phase:think` / `region:intervene` 这种冒号写法在 plugin `provides=` 与 bundle `region:` 字段里**禁用**（已在 D3 / D4 enforce）。`phase:` 仅在 ADR-0210 §6 定义的 `region tag 标注`（不参与 namespace）用途保留，与本 ADR 正交。

### D6 — 生产 runtime 不变

`lca/plugins/composer/runtime/runtime/capabilities.py::resolve_node_executor_bindings` 仍按 `key.rsplit("::", 1)[-1]` 拿 factory name——**只看 factory 名，不看 region 前缀**。本 ADR 不改 runtime lookup 路径，只改 namespace 字符串字面量本身。

## Mechanism

### 落地步骤（同 PR 闭环）

1. **新增 `RegionPrefix` enum**（contracts/atoms/enums/region_prefix.py）—— 从 `lca/nodes/` 目录静态收集。
2. **新增 `scripts/check_plugin_region_prefix.py`** —— 扫描 `lca/nodes/**/*.py`，校验 provides prefix 与目录名一致（fail-loud）。
3. **修 plugin `provides=` 前缀**：
   - 12 个 `phase:think::` → `think::`
   - 6 个 `region:intervene::` / `region:plan::` / `region:delegate::*` → `intervene::` / `plan::` / `delegate::`
   - 2 个 `phase:perceive::` / `phase:reflect::` / `phase:remember::` → `perceive::` / `reflect::` / `remember::`
   - **6 个 `lca/nodes/act/*.py` 的 `concept::` → `act::`**（核心 fix：act 目录从 concept prefix 迁回 act prefix）
4. **修 bundle YAML**：
   - `bundles/concept/history_assemble.yaml` / `llm_dispatch.yaml` / `decision_parse.yaml`：`region: concept` → `region: think`
   - `bundles/outer/phase_main.yaml::act.approve.gate`：`region: phase:intervene` → `region: intervene`
   - 全部 `concept/` 目录下 bundle yaml 若引用了被迁走的 plugin，同步更新 region 字段。
5. **debug-factories 集成 `RegionPrefix.parse`** —— 区分 `unrecognized_region` vs `factory_missing`。
6. **测试**：4 missing 回归 + 新增 region 不一致检测 + check 脚本测试。

### ADR-0228 §节点形态修订（in-place 注释）

`docs/adr/0228-plan-intervene-delegate-subgraphs.md` §节点形态段落加一行："`provides=` 前缀必须等于文件相对 `lca/nodes/` 的第一层目录名（ADR-0231 D3）"——**不修改既有 ADR 主体**，仅在文档加 cross-reference 注（AGENTS.md §5 闭环：契约改动必须同步加 cross-ref）。

### 删除条件

- `RegionPrefix.parse` 与文件系统脱节 → 删除 enum，回到字符串 prefix（极不可能，文件系统是 SSOT）。
- `lca/nodes/` 目录结构退役 → enum 与脚本同步退役（待 0194 §6 真正落地 `lca_kernel/plugins/<region>/`）。

## Why

按 AGENTS.md §1.5 第 2 条："找根因，不在表面包装；同一根因第二次出现 = 上次没修对"。`debug-factories` 的 4 missing 是**同一根因（namespace prefix 字符串与物理目录漂移）的 4 个实例**——只修 4 处，下次第 5 个又会出现。

按 ADR-0228 §节点形态约定，**契约本来就是这样**，只是没 enforce；本 ADR 不发明新规则，只把已有规则升为 fail-loud。

按 ADR-0210 §6.6 `regions.declare` 已有解析但无 enforce —— 本 ADR 不扩展其 schema，而是在 plugin / bundle 层 fail-loud（`regions.declare` 的 enforce 留 follow-up：profile-level 白名单校验独立 ADR）。

## Invariants upheld

- **C1 认知闭集** — region 集合由文件系统决定，新增 region 不进闭集，闭集不变。
- **C4 Reducer 单写** — 不涉及。
- **C5 能力单调** — `provides=` 字符串改写不改 capability 维度，capability grant 不变。
- **C13 信息血统闭合** — 每个 provides 字符串可静态回答 D1（SSOT = 物理目录）/ D3（plugin shape lint）/ D4（debug-factories 区分）。
- **AGENTS.md §1.5 第 6 条 不做临时代码** — 不留 compat shim；plugin prefix 改动同 PR 落地；bundle region 改动同 PR 落地；不存在跨 PR 后门。

## What changed

- `lca/contracts/atoms/enums/region_prefix.py` 新增：`RegionPrefix` enum + `UnknownRegionPrefixError` + `RegionPrefix.parse(raw: str) -> RegionPrefix` + `RegionPrefix.values()`。
- `lca/contracts/atoms/enums/enums.py` 不直接 re-export `RegionPrefix`（避免破坏 LCA `contracts/__init__.py` 既有导入路径）；RegionPrefix 自成模块，从 `lca.contracts.atoms.enums.region_prefix` 导入。
- `scripts/check_plugin_region_prefix.py` 新增：扫 `lca/nodes/**/*.py`，exit 1 on mismatch。
- `lca/infrastructure/cli/commands/runs/driver_debug.py::cmd_debug_factories` 改造：node.region 走 `RegionPrefix.parse`，未识别 → 报 `unrecognized_region`（status 区别于 `missing`）。
- ~30 个 plugin 的 `provides=` 字符串前缀改写（详见 Mechanism §6）。
- ~4 个 bundle YAML 的 `region:` 字段改写（详见 Mechanism §4）。
- `tests/contracts/test_region_prefix.py` 新增：覆盖 enum parse / unknown / values。
- `tests/runtime/test_debug_factories_region_status.py` 新增：覆盖 `unrecognized_region` 区分。
- `tests/architecture/test_check_plugin_region_prefix.py` 新增：覆盖 lint 脚本 fail-loud 路径。

## Risks

- **Bundle reference 不全** — 改了 plugin prefix 后，bundles 里 `factory:` 字段若仍指向老 plugin name，bundle validate 可能失败。Mitigation：改 plugin 时同步 grep 所有 bundle 引用，全量更新。
- **`RegionPrefix.parse` 与运行时漂移** — 新建 `lca/nodes/<region>/` 目录但未在 enum 收集路径上跑 → enum 漏掉。Mitigation：enum 从文件系统动态收集（每次导入都扫一次），不存在漂移窗口。
- **debug-factories 区分状态破坏既有消费者** — 若有外部脚本消费 `factory_index` 字段假设 `status in {ok, missing, delegate}`，新增 `unrecognized_region` 需同步更新。Mitigation：状态字段仍是 str，新值不影响 str 消费者；只在 status=='unrecognized_region' 时多一条 `tried_keys` 字段。
