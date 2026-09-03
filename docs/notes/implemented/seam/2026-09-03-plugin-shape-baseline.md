# Agent Note: lca/plugins/ 单 Manifest 范式基线 —— Phase A 落定

Status: implemented(2026-09-03)

## Problem

`lca/plugins/` 下 plugin 形态不统一,违反"优雅、好维护、正规"目标。三类形态违例:

| 违例 | 数量 | 影响 |
|---|---|---|
| `@plugin(...)` 缺 `effects=` 关键字 | 49 | 副作用类无法静态推导,review 与 tripwire 失效 |
| events/{sinks,publishers,subscribers}/*/manifest.py 双形态残留(event_plugin_spec + plugin_spec: dict) | 17 | 鉴权 SSOT 实际由 yaml 接管,dict 是孤儿数据;Phase B 必清 |
| 同 id 镜像(`run_loop_driver_registry.py` 与 `loop_drivers/registry.py` 同 id) | 2 | 启动 DAG 行为漂移;Phase C 必合 |

合计 **70 个违例**,基线快照在 `docs/notes/baselines/plugin-shape.json`。

`codegen_plugin_metadata.py` 已经守住 ADR-0110 contract 面(`logic_address` / `relations` / `ownership` / `test_suite`),但**未覆盖形态面**。Phase A 的目标是把形态面也写进 CI,**不污染** ADR-0110 contract 校验。

## Decision

新增 `scripts/check_plugin_shape.py`,与 `codegen_plugin_metadata.py` 解耦:

- **三维独立扫描**:
  1. `missing_effects` —— 所有 `@plugin(...)` 缺 `effects=`
  2. `dual_form_residue` —— `lca/plugins/events/{sinks,publishers,subscribers}/*/manifest.py` 顶层有 `event_plugin_spec` 或 `plugin_spec` 赋值
  3. `duplicate_id` —— 同 `@plugin(id=...)` 出现在 ≥ 2 个文件
- **AST 独立实现**,不 import codegen;codegen 保持 ADR-0110 单职责
- **`--json` 模式** 给 agent;**`--baseline` 模式** 写 `docs/notes/baselines/plugin-shape.json`
- **`lca-ops audit-plugin-shape`** 包装;`lca/infrastructure/cli/guide.py:151` 加条目

不动:
- `@plugin(...)` 装饰器签名(契约稳定)
- `legacy_blacklist.txt`(本工具无豁免机制,违例目录/插件在后续 Phase B/C 中处理)
- `scripts/codegen_plugin_metadata.py` 的 contract 面

## 影响面

| 文件 | 改动 |
|---|---|
| `scripts/check_plugin_shape.py` | 新建,359 行;三维 AST 扫描 + 人类/JSON 双输出 + baseline 模式 |
| `lca/infrastructure/cli/commands/audit.py` | 新增 `audit_plugin_shape_cmd`(subprocess 调脚本,透传 exit code) |
| `lca/infrastructure/cli/guide.py:151` | 加一行 `audit-plugin-shape` 命令说明 |
| `docs/notes/baselines/plugin-shape.json` | 基线快照(70 个违例详情) |

不改:`@plugin` 签名、`legacy_blacklist.txt`、codegen 的 contract 面。

## 验收

| 检查 | 结果 |
|---|---|
| `python scripts/check_plugin_shape.py` | 70 violations (49 + 17 + 4);exit code 1 |
| `python scripts/check_plugin_shape.py --json` | 标准 JSON 输出 |
| `python scripts/check_plugin_shape.py --baseline` | 写 `docs/notes/baselines/plugin-shape.json` |
| `./scripts/lca-ops audit-plugin-shape` | 等价输出,exit code 1 |
| `./scripts/lca-ops audit-plugin-shape --json` | 等价 JSON |
| `python scripts/codegen_plugin_metadata.py --scan` | 230 plugins / 10 critical / 220 warning(与基线一致) |
| `python scripts/check_plugin_metadata.py --json` | 230 / 10 / 220(同) |
| `python scripts/check_plugin_shape.py --root lca/plugins/events/sinks` | 仅扫 sinks 子树,Phase B 用 |
| `python scripts/check_plugin_shape.py --root lca/plugins/observability` | 仅扫 observability 子树,Phase C 用 |

## delete-when / 后续债

| 路径 | 触发删除条件 |
|---|---|
| `scripts/check_plugin_shape.py` | missing_effects=0 AND dual_form_residue=0 AND duplicate_id=0 三类同时清空即可删本工具 + guide 条目 |
| Phase B:清双形态残留 | 17 个 events/*/manifest.py 全部加 `@plugin` + 删除 `event_plugin_spec` 与 `plugin_spec: dict` 后,`dual_form_residue=0` |
| Phase C:补 effects + 合镜像 | 49 个 plugin 全部补 `effects=` + 4 处同 id 镜像合并后,`missing_effects=0` AND `duplicate_id=0` |
| `docs/notes/baselines/plugin-shape.json` | 每次 Phase B/C 完成后跑 `--baseline` 刷新;最终态为空数组时归档 |
