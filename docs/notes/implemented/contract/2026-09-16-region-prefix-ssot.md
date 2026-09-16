# Agent Note: Region prefix SSOT = `lca/nodes/<region>/` directory name

Status: implemented

## Problem

Plugin `provides=` 字符串前缀与 `lca/nodes/` 物理目录名漂移，导致 `debug-factories` 报告 4 处 `factory missing`，根因是 namespace prefix 字符串没有 SSOT：

| 物理目录 | 原 `provides=` 前缀 | 问题 |
|---|---|---|
| `lca/nodes/think/` | `phase:think::` (12 个) | 带冒号（ADR-0210 P7 阶段标签残留） |
| `lca/nodes/perceive/` `reflect/` `remember/` | `phase:X::` (6 个) | 带冒号 |
| `lca/nodes/intervene/` `plan/` `delegate/` | `region:X::` (7 个) | 带冒号 |
| `lca/nodes/act/` | `concept::` (6 个) | **完全错位**（act 目录挂 concept prefix） |
| `lca/nodes/concept/` | `concept::` (27 个) | ✅ 唯一对齐 |

对应 bundle YAML `region:` 字段也有同样的漂移——`bundles/concept/history_assemble.yaml` 等 4 处报 missing。

Production runtime 没爆是因为 `resolve_node_executor_bindings` 只取 `key.rsplit("::", 1)[-1]`（factory 名），不看 region 前缀；但 debug / capability graph / SSOT 矩阵都会暴露成 missing。

ADR-0228 §节点形态本已规定 `provides=("<region>::<id>",)` 无冒号前缀且 region = 物理目录名，但**没有 enforce**——这是 LCA 文档与代码 drift 的典型样本。

## Decision

### D1 — Region SSOT = `lca/nodes/<region>/` 顶层目录名（无冒号）

文件系统的当前实际目录就是 SSOT。新增 region = 新建目录 + `lca/nodes/README.md` 注释。当前 region 集合（2026-09-16 快照）：`{think, act, perceive, reflect, remember, stop, concept, intervene, delegate, plan, loop}`。

### D2 — `RegionPrefix` enum 提供类型化视图 + fail-loud 解析

新增 `lca/contracts/atoms/enums/region_prefix.py::RegionPrefix` —— 从 `lca/nodes/` 目录动态收集，提供 `RegionPrefix.parse(raw)`（strict）/ `RegionPrefix.contains(raw)`（non-throwing）/ `UnknownRegionPrefixError`。enum 是视图不是 SSOT；测试 `tests/contracts/test_region_prefix.py` 用快照防止目录漂移。

### D3 — `scripts/check_plugin_region_prefix.py` — plugin shape lint

扫 `lca/nodes/**/*.py` 的 `@plugin(provides=...)`，每条 provides 字符串 split `::` 第一段必须：

1. 不含 `:`（拒 `phase:think` / `region:intervene` 写法）。
2. 等于文件相对 `lca/nodes/` 的**第一层目录名**。

漂移即 `Issue`，CI exit 1。11 个测试在 `tests/scripts/test_check_plugin_region_prefix.py`。

### D4 — debug-factories 集成 `RegionPrefix.parse`，区分 `unrecognized_region` vs `factory_missing`

`lca/infrastructure/cli/commands/runs/driver_debug.py::cmd_debug_factories` 在 lookup miss 时先调 `RegionPrefix.contains`：未识别 → 报 `unrecognized_region` + `note`（bundle YAML typo / pre-migration prefix）；已识别 → 报 `factory_missing`（plugin 没提供）。同时把 `_build_factory_index` 静态扫描从 `lca/plugins/` 扩展到 **`lca/plugins/` + `lca/nodes/`**——因为 lca/nodes/ 下的 plugin 不在 resolved profile 里（它们不走 `$module:` 注册），只能静态扫描拿到。

### D5 — Production runtime 不变

`lca/plugins/composer/runtime/runtime/capabilities.py::resolve_node_executor_bindings` 仍按 `key.rsplit("::", 1)[-1]` 拿 factory name——**只看 factory 名，不看 region 前缀**。本 Note 不改 runtime lookup 路径，只改 namespace 字符串字面量本身。

## Consequences

### 已落地的代码改动

- **31 个 plugin `provides=` 字符串前缀去冒号**：`phase:think::` → `think::`（12）/ `phase:perceive::` → `perceive::`（2）/ `phase:reflect::` → `reflect::`（2）/ `phase:remember::` → `remember::`（2）/ `region:intervene::` → `intervene::`（3）/ `region:plan::` → `plan::`（2）/ `region:delegate::` → `delegate::`（3）/ `concept::` (在 act/) → `act::`（6）。
- **25 个 executor `region: str = "..."` 类字段同步去前缀**（与 provides= 保持一致）。
- **12 个 bundle YAML 顶层 `region:` 字段去前缀**（子图命名空间从 `phase:think` → `think` 等）。
- **6 个 act/ leaf 节点显式加 `region: act`**（bundle 顶层 `region: concept` 不再继承到 leaf）。

### 数字结果

| 指标 | 修前 | 修后 |
|---|---|---|
| `debug-factories` missing | 4 | **0** |
| plugin provides prefix 漂移 | 31 | **0** |
| bundle yaml region 漂移 | 16 | **0** |
| kernel_check plan_lift | ✅ | ✅ |
| audit-plugin-shape | baseline 范围内 | baseline 范围内 |

### Trade-off

- **`unrecognized_region` 是新增 status 值**：外部消费者若假设 `status in {ok, missing, delegate}`，需同步更新。Mitigation：状态字段是 str，新值不破坏 `==` / 枚举比较。
- **新增 `RegionPrefix.parse` 严格性**：任何含冒号的 region 字符串都被拒，不再 silent 接受 `phase:think`。这意味着后续若有人误用冒号写法，**debug-factories 会立即报错**而不是悄悄把 key 拼错。
- **`_build_factory_index` 扫描范围扩展**：增加 ~63 个文件的扫描，CLI 启动时间多 ~100ms（可接受）。

## Alternatives considered

### Why not hardcode region list in enum (instead of FS scan)?

硬编码 enum 会随 region 增减 drift；FS 动态收集是 SSOT 同步最稳的方式，缺点是 enum 不能 pickle 跨进程——debug-factories 一次性 CLI 进程无此问题。

### Why not change runtime `resolve_node_executor_bindings` to use region prefix?

Runtime 只取 factory 名（`rsplit("::", 1)[-1]`）是设计选择：让 bundle yaml 只需写 factory 名而不必重写完整 namespace prefix。改 runtime 会破坏这个简洁性，且**不能解决 debug-factories 的报告问题**（debug 用完整 key 做归属）。

### Why not write a custom Pydantic enum rather than stdlib `str, Enum`?

LCA 既有 enum 都是 `str, Enum`（见 `lca/contracts/atoms/enums/enums.py`），本 Note 沿用同惯例；Pydantic 引入额外依赖、且不为本场景提供额外保证。

### Why not deprecate bundle yaml `region:` field entirely?

Bundle yaml `region:` 是 **子图命名空间**（与 leaf node region 不同语义），例如 `region: phase:think` 表示"think 阶段子图"。但 ADR-0231 §D5 让 leaf 节点显式声明 region 后，bundle 顶层 region 退化为"子图 ID"而非"factory lookup key"——**bundle 顶层 region 不会再被 debug-factactory 误用**（前面 missing: 28 → 6 的关键修复就是这个）。完全废弃会破坏 ADR-0220 §3 三层图 schema。

## Testing

- **新增 22 个测试**：`tests/contracts/test_region_prefix.py` (11) + `tests/scripts/test_check_plugin_region_prefix.py` (11)，覆盖 enum parse / contains / unknown / 漂移检测 / 文件路径判断 / 模拟 lca/nodes/ 漂移检测 / 静态 lint 实际扫描 0 drift。
- **回归测试**：`tests/architecture/test_p7_profile_regions_declare.py`（ADR-0210 §6.6 既有测试）依然全过。
- **手工验证**：`./scripts/lca-ops kernel_check profiles/web-standard.yaml` ✅；`./scripts/lca-ops debug-factories -p profiles/web-standard.yaml` → 35 factories / 0 missing；`./scripts/lca-ops audit-plugin-shape` baseline 范围内。

## Related

- ADR-0231（Region prefix SSOT 与节点目录规范化，**同日落地**）
- ADR-0228（`@graph_node` DSL 退役 + plan/intervene/delegate 子图，本 Note 引用 §节点形态）
- ADR-0220（三层图 schema —— `primitive/concept/agent` 是 bundle 路径前缀不是 plugin namespace）
- ADR-0210（P7 region-tag 机制 —— `phase:` 标签保留用于 region tag 标注，但**不**用于 plugin `provides=` 前缀；本 Note §D5 落实这条边界）
- `docs/notes/proposed/seam/2026-09-15-unified-nodes-directory-layout.md`（Note 提议 `lca/nodes/<region>/...` 目录布局，本 Note 在该 layout 上落 SSOT）
