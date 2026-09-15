# lca/harness/composition — 编译与装配

> **决策：** ADR-0061 · ADR-0115 · ADR-0195

## 1. 职责

Profile / Bundle → `ResolvedProfile` → `CompiledRunPlan` 的**编译时**管道（与 run 热路径分离）。

| 组件 | 公共入口 | 依赖的编译实现 |
|---|---|---|
| Profile boot 编译 | `boot_compile.compile_profile_boot_products` | `lca_kernel.plan.plan_compile.compile_plan` |
| Observability 编译 | `observability_compile.compile_observability_boot_plan` | `lca_kernel.events.compile.compiler.ObservabilityCompiler` |
| Resource 投影 | `resource_registry.project_resources` · `ResourceRegistry` | ADR-0199 §3.1 第四维度（只读、可分发内容） |

## 2. 不负责

- Fiber 运行时 spawn（`lca_kernel/boot.py`）
- Phase 遍历执行（`harness/graph` + `lca/loop`）
- 插件业务 setup（各 plugin `plugin.py`）

## 7. 副作用

无对外副作用：三个模块都是**编译期纯投影**，不读写文件、不开 socket、不写
Session/journal（`grep -n "read_text\|write_text\|open(\|mkdir\|rglob"
lca/harness/composition/*.py` 无命中）。可观察结果只有两类：

| 结果 | 形态 |
|---|---|
| 构造出的值 | `ProfileBootProducts`、`CompiledObservabilityPlan`、`ResourceRegistry` 条目 |
| 失败 | 类型化异常：`ObservabilityCompileError`（附 plan 校验码）、`ResourceProjectionError`（越界/非法资源引用） |

resource 投影刻意只读：按 I-HPC-6，资源内容不获得任何执行权限。

## 与 kernel 边界

- **K1–K2** 公共 API 以 `lca_kernel`  re-export 为准
- harness 内保留 composition **数据类与 compile 纯函数**；避免双 boot 链

## 迁移

Wave P4：profile/compile 文件收拢至本目录；kernel 只保留薄 re-export。
