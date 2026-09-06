# lca/harness/composition — 编译与装配

> **决策：** ADR-0061 · ADR-0115 · ADR-0195

## 职责

Profile / Bundle → `ResolvedProfile` → `CompiledRunPlan` 的**编译时**管道（与 run 热路径分离）。

| 组件 | 现状路径 |
|---|---|
| Profile 源 | `harness/profile/source.py` |
| Resolve / DAG | `harness/profile/resolve.py` · `lca_kernel/resolve.py` |
| Plan 编译 | `harness/profile/plan_compiler.py` · `lca_kernel/plan.py` |
| Boot products | `harness/profile/boot_products.py` |
| Graph 装配 | `declarative/compile/assembler.py` |

## 不负责

- Fiber 运行时 spawn（`lca_kernel/boot.py`）
- Phase 遍历执行（`harness/graph` + `lca/loop`）
- 插件业务 setup（各 plugin `plugin.py`）

## 与 kernel 边界

- **K1–K2** 公共 API 以 `lca_kernel`  re-export 为准
- harness 内保留 composition **数据类与 compile 纯函数**；避免双 boot 链

## 迁移

Wave P4：profile/compile 文件收拢至本目录；kernel 只保留薄 re-export。
